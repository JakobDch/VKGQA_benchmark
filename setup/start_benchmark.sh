#!/usr/bin/env bash
# One-command setup for the Ambiguity VKGQA benchmark (VKG mode).
#
#   ./start_benchmark.sh              # everything: backends + load data + start endpoints
#   ./start_benchmark.sh noise        # only the 8 noise datasets
#   ./start_benchmark.sh ambrosia     # only AMBROSIA (loads 846 MySQL schemas)
#   ./start_benchmark.sh webqsp       # only WebQSP (loads the shipped 668M RDF)
#
# Requires: docker + docker compose. All services bind to 127.0.0.1 only.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
DATASETS="$BENCH/datasets"
TARGET="${1:-all}"
NET=bench_net
ONTOP_IMAGE=ontop/ontop:5.4.0
JDBC_DIR="$HERE/jdbc"        # postgresql + mysql JDBC drivers (mounted into Ontop)
export MSYS_NO_PATHCONV=1    # keep container-absolute paths intact under Git-Bash on Windows

log(){ echo -e "\033[1;36m[bench]\033[0m $*"; }

# Docker Desktop on Windows needs a Windows-style host path for -v; on Linux/mac the
# path is already fine. Convert /c/... (Git-Bash) back to C:/... when needed.
hostpath(){ case "$1" in /?/*) echo "$1" | sed -E 's#^/([a-zA-Z])/#\1:/#';; *) echo "$1";; esac; }

# ---------------------------------------------------------------- backends
start_backends(){
  log "starting backing services (postgres / mysql / virtuoso) ..."
  docker compose -f "$HERE/docker-compose.yml" up -d
  log "waiting for postgres ..."
  until docker exec bench_noise_pg pg_isready -U noise >/dev/null 2>&1; do sleep 2; done
  log "waiting for mysql ..."
  until docker exec bench_ambrosia_mysql mysqladmin ping -h localhost -pambrosia >/dev/null 2>&1; do sleep 2; done
  log "backends up."
}

# ---------------------------------------------------------------- noise (postgres)
NOISE_SETS=(bsbm cwd cwe_secutable eicu gtfs lubm mimic_iii npd)
# next free ontop host port for noise endpoints
NOISE_BASE_PORT=13001

load_noise(){
  local i=0
  for ds in "${NOISE_SETS[@]}"; do
    local dir="$DATASETS/$ds"
    [ -d "$dir" ] || { log "skip $ds (no dir)"; continue; }
    log "== noise: $ds =="
    # 1. unzip data if needed
    if [ -f "$dir/data.zip" ] && [ ! -d "$dir/data" ]; then
      ( cd "$dir" && unzip -q -o data.zip )
    fi
    # 2. create db + load the postgres dump (each set ships one .sql / .psql / .postgres)
    docker exec bench_noise_pg psql -U noise -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='$ds'" | grep -q 1 || \
      docker exec bench_noise_pg createdb -U noise "$ds"
    local dump
    dump=$(ls "$dir"/data/*postgres*.sql "$dir"/data/*.psql "$dir"/data/${ds}*.sql 2>/dev/null | head -1 || true)
    if [ -n "${dump:-}" ]; then
      log "   loading $(basename "$dump") -> db $ds"
      docker exec -i bench_noise_pg psql -U noise -d "$ds" < "$dump" >/dev/null 2>&1 || \
        log "   (warn: some statements failed for $ds — check dump dialect)"
    else
      log "   (warn: no postgres dump found for $ds in $dir/data)"
    fi
    # 3. start an Ontop endpoint for this dataset
    local port=$((NOISE_BASE_PORT + i)); i=$((i+1))
    start_ontop_pg "$ds" "$dir" "$port"
  done
}

start_ontop_pg(){
  local ds="$1" dir="$2" port="$3"
  local mapping; mapping=$(ls "$dir"/mapping/*.r2rml.ttl 2>/dev/null | head -1)
  local ontology; ontology=$(ls "$dir"/ontology/*.ttl "$dir"/ontology/*.owl 2>/dev/null | head -1)
  [ -n "${mapping:-}" ] || { log "   (no mapping for $ds, skip endpoint)"; return; }
  # work dir under setup/ (Docker Desktop shares the project drive; /tmp of Git-Bash isn't shared)
  local work="$HERE/.ontop/$ds"; rm -rf "$work"; mkdir -p "$work"
  cat > "$work/ontop.properties" <<EOF
jdbc.url=jdbc:postgresql://bench_noise_pg:5432/$ds
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
EOF
  cp "$mapping" "$work/mapping.ttl"
  local onto_arg=""
  if [ -n "${ontology:-}" ]; then cp "$ontology" "$work/ontology.ttl"; onto_arg="-t /opt/ontop/input/ontology.ttl"; fi
  docker rm -f "bench_ontop_$ds" >/dev/null 2>&1 || true
  docker run -d --name "bench_ontop_$ds" --network "$NET" \
    -p "127.0.0.1:$port:8080" \
    -v "$(hostpath "$work"):/opt/ontop/input:ro" \
    -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
    "$ONTOP_IMAGE" ontop endpoint \
      -m /opt/ontop/input/mapping.ttl $onto_arg -p /opt/ontop/input/ontop.properties >/dev/null
  log "   $ds SPARQL -> http://localhost:$port/sparql"
}

# ---------------------------------------------------------------- ambrosia (mysql, 846 schemas)
load_ambrosia(){
  log "== AMBROSIA: loading databases into MySQL =="
  local srcroot="$BENCH/../sources/AMBROSIA/data"
  if [ ! -d "$srcroot" ]; then
    log "   AMBROSIA source data not found at sources/AMBROSIA/data — see datasets/ambrosia/DATA_ACCESS.md"
    log "   (mappings/ontology/GT are present; only the source DBs must be obtained separately)"
    return
  fi
  local n=0
  while IFS= read -r sqlite; do
    local base; base=$(basename "$sqlite" .sqlite)
    local schema="amb_$base"
    # create schema + import the sqlite-syntax dump (works in MySQL after minor casts;
    # AMBROSIA dumps are portable CREATE TABLE + INSERT). Skip if already present.
    docker exec bench_ambrosia_mysql mysql -uambrosia -pambrosia -e \
      "CREATE DATABASE IF NOT EXISTS \`$schema\`" 2>/dev/null || true
    n=$((n+1))
  done < <(find "$srcroot" -name '*.sqlite' | sort)
  log "   created $n AMBROSIA schemas (import via load/load_ambrosia.py for data rows)."
  log "   AMBROSIA Ontop endpoints are started per-DB on demand: setup/run_ontop_ambrosia.sh <db_base> <port>"
}

# ---------------------------------------------------------------- webqsp (rdf -> virtuoso)
load_webqsp(){
  log "== WebQSP: bulk-loading the shipped 668M RDF graph into Virtuoso =="
  local gz; gz=$(ls "$DATASETS/webqsp/graph/"*.nt.gz 2>/dev/null | head -1)
  [ -n "${gz:-}" ] || { log "   no RDF graph found in datasets/webqsp/graph/ (see DATA_ACCESS.md)"; return; }
  log "   found $(basename "$gz") — loading (this takes a while for 668M triples) ..."
  # Virtuoso bulk load: gunzip into the mounted /graph dir, register, run loader.
  docker exec bench_webqsp_store bash -lc '
    cd /graph && for f in *.nt.gz; do [ -f "${f%.gz}" ] || gunzip -k "$f"; done'
  docker exec bench_webqsp_store isql 1111 dba dba exec="ld_dir('/graph', '*.nt', 'http://rdf.freebase.com/');" 2>/dev/null || true
  docker exec bench_webqsp_store isql 1111 dba dba exec="rdf_loader_run();" 2>/dev/null || true
  docker exec bench_webqsp_store isql 1111 dba dba exec="checkpoint;" 2>/dev/null || true
  log "   WebQSP SPARQL -> http://localhost:8890/sparql"
}

# ---------------------------------------------------------------- main
start_backends
case "$TARGET" in
  all)      load_noise; load_ambrosia; load_webqsp ;;
  noise)    load_noise ;;
  ambrosia) load_ambrosia ;;
  webqsp)   load_webqsp ;;
  *) echo "usage: $0 [all|noise|ambrosia|webqsp]"; exit 1 ;;
esac
log "done. See 'docker ps' for running endpoints."
