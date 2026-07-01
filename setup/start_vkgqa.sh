#!/usr/bin/env bash
# ============================================================================
#  VKGQA MODE — query the data VIRTUALLY via Ontop (no materialization).
#  Loads the relational data into Postgres/MySQL and exposes each dataset as a
#  live Ontop SPARQL endpoint over its R2RML mapping + ontology.
#  (For KGQA over materialized native RDF instead, use start_kgqa.sh.)
# ============================================================================
#
#   ./start_vkgqa.sh              # everything: backends + load data + start endpoints
#   ./start_vkgqa.sh noise        # only the 6 noise datasets
#   ./start_vkgqa.sh ambrosia     # only AMBROSIA (loads 846 MySQL schemas)
#   ./start_vkgqa.sh webqsp       # only WebQSP (VKG dump preferred, else RDF graph)
#   ./start_vkgqa.sh webqsp-vkg   # force WebQSP as VKG (pg_restore + Ontop)
#   ./start_vkgqa.sh webqsp-rdf   # force WebQSP as native RDF (Virtuoso)
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
NOISE_SETS=(bsbm cwd cwe_secutable gtfs lubm npd)
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

# ---------------------------------------------------------------- webqsp
# WebQSP can be served two ways (both come from Zenodo — see download_data.sh):
#   (a) VKG mode  : restore the PostgreSQL dump -> query virtually via Ontop (like the
#                   other datasets). This is the "VKG" that the benchmark is about.
#   (b) native RDF: bulk-load the prebuilt 668M-triple RDF graph into Virtuoso — a
#                   convenience so you don't have to materialize, and the native-KG
#                   comparison partner.
# We do whichever data file is present (prefer the graph if both, unless mode=vkg).
load_webqsp(){ # optional arg: "vkg" | "rdf" (default: auto)
  local mode="${1:-auto}"
  local dump; dump=$(ls "$DATASETS/webqsp/data/"*.dump 2>/dev/null | head -1)
  local gz;   gz=$(ls "$DATASETS/webqsp/graph/"*.nt.gz 2>/dev/null | head -1)

  if { [ "$mode" = "vkg" ] || [ "$mode" = "auto" ]; } && [ -n "${dump:-}" ]; then
    load_webqsp_vkg "$dump"; [ "$mode" = "vkg" ] && return
  fi
  if [ -n "${gz:-}" ]; then
    load_webqsp_rdf "$gz"
  elif [ -z "${dump:-}" ]; then
    log "   no WebQSP data found (run setup/download_data.sh webqsp) — see DATA_ACCESS.md"
  fi
}

load_webqsp_vkg(){  # PostgreSQL dump -> restore -> Ontop endpoint (like noise, but big)
  local dump="$1"
  log "== WebQSP (VKG): restoring PostgreSQL dump (13084 tables, ~85 GB restored) =="
  docker exec bench_noise_pg psql -U noise -d postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname='freebase_vkg_big'" | grep -q 1 || \
    docker exec bench_noise_pg createdb -U noise freebase_vkg_big
  docker cp "$dump" bench_noise_pg:/webqsp.dump
  log "   pg_restore -j4 (this takes a while) ..."
  docker exec bench_noise_pg pg_restore -U noise -d freebase_vkg_big --no-owner -j4 /webqsp.dump >/dev/null 2>&1 \
    || log "   (some restore warnings — usually harmless)"
  docker exec bench_noise_pg rm -f /webqsp.dump
  start_ontop_pg_named freebase_vkg_big "$DATASETS/webqsp" 13010
  log "   WebQSP VKG SPARQL -> http://localhost:13010/sparql"
}

load_webqsp_rdf(){  # prebuilt RDF graph -> Virtuoso bulk load
  local gz="$1"
  log "== WebQSP (native RDF): bulk-loading $(basename "$gz") into Virtuoso (668M triples) =="
  docker exec bench_webqsp_store bash -lc '
    cd /graph && for f in *.nt.gz; do [ -f "${f%.gz}" ] || gunzip -k "$f"; done'
  docker exec bench_webqsp_store isql 1111 dba dba exec="ld_dir('/graph', '*.nt', 'http://rdf.freebase.com/');" 2>/dev/null || true
  docker exec bench_webqsp_store isql 1111 dba dba exec="rdf_loader_run();" 2>/dev/null || true
  docker exec bench_webqsp_store isql 1111 dba dba exec="checkpoint;" 2>/dev/null || true
  log "   WebQSP RDF SPARQL -> http://localhost:8890/sparql"
}

# start an Ontop endpoint against an explicitly-named PG database (used by WebQSP VKG)
start_ontop_pg_named(){
  local db="$1" dir="$2" port="$3"
  local mapping; mapping=$(ls "$dir"/mappings/*.r2rml.ttl "$dir"/mapping/*.r2rml.ttl 2>/dev/null | head -1)
  [ -n "${mapping:-}" ] || { log "   (no mapping for $db)"; return; }
  local work="$HERE/.ontop/$db"; rm -rf "$work"; mkdir -p "$work"
  cat > "$work/ontop.properties" <<EOF
jdbc.url=jdbc:postgresql://bench_noise_pg:5432/$db
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
EOF
  cp "$mapping" "$work/mapping.ttl"
  docker rm -f "bench_ontop_$db" >/dev/null 2>&1 || true
  docker run -d --name "bench_ontop_$db" --network "$NET" \
    -p "127.0.0.1:$port:8080" \
    -v "$(hostpath "$work"):/opt/ontop/input:ro" \
    -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
    "$ONTOP_IMAGE" ontop endpoint \
      -m /opt/ontop/input/mapping.ttl -p /opt/ontop/input/ontop.properties >/dev/null
}

# ---------------------------------------------------------------- main
start_backends
case "$TARGET" in
  all)         load_noise; load_ambrosia; load_webqsp ;;
  noise)       load_noise ;;
  ambrosia)    load_ambrosia ;;
  webqsp)      load_webqsp ;;
  webqsp-vkg)  load_webqsp vkg ;;
  webqsp-rdf)  load_webqsp rdf ;;
  *) echo "usage: $0 [all|noise|ambrosia|webqsp|webqsp-vkg|webqsp-rdf]"; exit 1 ;;
esac
log "done. See 'docker ps' for running endpoints."
