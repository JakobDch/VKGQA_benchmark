#!/usr/bin/env bash
# ============================================================================
#  KGQA MODE — materialize each dataset to a NATIVE RDF graph (N-Triples).
#  Produces datasets/<ds>/rdf/<ds>.nt files you load into the triplestore of
#  your choice. Nothing is served live here (that's VKGQA / start_vkgqa.sh).
#
#  WebQSP is the exception: its 668M-triple graph is NOT re-materialized (hours);
#  it ships prebuilt as datasets/webqsp/graph/webqsp_vkg_graph.nt.gz (from Zenodo)
#  and is simply unpacked into place.
# ============================================================================
#
#   ./start_kgqa.sh              # everything: noise + AMBROSIA + WebQSP graph
#   ./start_kgqa.sh noise        # only the 6 noise datasets
#   ./start_kgqa.sh ambrosia     # only AMBROSIA (846 DBs -> one merged .nt)
#   ./start_kgqa.sh webqsp       # only WebQSP (unpack the shipped graph)
#
# Requires: docker + docker compose (backends for materialization). Output is
# plain .nt files — load them into Virtuoso / Fuseki / Blazegraph / GraphDB / …
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
DATASETS="$BENCH/datasets"
TARGET="${1:-all}"
NET=bench_net
ONTOP_IMAGE=ontop/ontop:5.4.0
JDBC_DIR="$HERE/jdbc"
NOISE_SETS=(bsbm cwd cwe_secutable gtfs lubm npd)
export MSYS_NO_PATHCONV=1

log(){ echo -e "\033[1;35m[kgqa]\033[0m $*"; }
hostpath(){ case "$1" in /?/*) echo "$1" | sed -E 's#^/([a-zA-Z])/#\1:/#';; *) echo "$1";; esac; }

# bring up backing DBs (needed to materialize from the relational data)
start_backends(){
  log "starting backing databases (for materialization) ..."
  docker compose -f "$HERE/docker-compose.yml" up -d noise_pg ambrosia_mysql
  until docker exec bench_noise_pg pg_isready -U noise >/dev/null 2>&1; do sleep 2; done
  until docker exec bench_ambrosia_mysql mysqladmin ping -h localhost -pambrosia >/dev/null 2>&1; do sleep 2; done
}

# --- noise: load PG dump (if not loaded) then ontop materialize -> .nt ---------
kgqa_noise(){
  for ds in "${NOISE_SETS[@]}"; do
    local dir="$DATASETS/$ds"
    [ -d "$dir" ] || { log "skip $ds"; continue; }
    log "== $ds =="
    # ensure data is loaded (idempotent)
    [ -d "$dir/data" ] || { [ -f "$dir/data.zip" ] && ( cd "$dir" && unzip -q -o data.zip ); }
    docker exec bench_noise_pg psql -U noise -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='$ds'" | grep -q 1 || \
      docker exec bench_noise_pg createdb -U noise "$ds"
    local dump; dump=$(ls "$dir"/data/*postgres*.sql "$dir"/data/*.psql "$dir"/data/${ds}*.sql 2>/dev/null | head -1 || true)
    if [ -n "${dump:-}" ]; then
      docker exec -i bench_noise_pg psql -U noise -d "$ds" < "$dump" >/dev/null 2>&1 || true
    fi
    materialize_pg "$ds" "$dir" "jdbc:postgresql://bench_noise_pg:5432/$ds"
  done
}

# generic: ontop materialize a mapping over a JDBC url -> <out>/<name>.nt
materialize_pg(){
  local name="$1" dir="$2" jdbc="$3"
  local mapping; mapping=$(ls "$dir"/mapping/*.r2rml.ttl "$dir"/mappings/*.r2rml.ttl 2>/dev/null | head -1)
  local ontology; ontology=$(ls "$dir"/ontology/*.ttl "$dir"/ontology/*.owl 2>/dev/null | head -1)
  [ -n "${mapping:-}" ] || { log "$name: no mapping, skip"; return; }
  local out="$dir/rdf"; mkdir -p "$out"
  local work="$HERE/.ontop/mat_$name"; rm -rf "$work"; mkdir -p "$work"
  cat > "$work/ontop.properties" <<EOF
jdbc.url=$jdbc
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
EOF
  cp "$mapping" "$work/mapping.ttl"
  local onto_arg=""
  if [ -n "${ontology:-}" ]; then cp "$ontology" "$work/ontology.ttl"; onto_arg="-t /in/ontology.ttl"; fi
  log "$name: materializing -> rdf/$name.nt"
  docker run --rm --network "$NET" \
    -v "$(hostpath "$work"):/in:ro" -v "$(hostpath "$out"):/out" \
    -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
    "$ONTOP_IMAGE" ontop materialize \
      -m /in/mapping.ttl $onto_arg -p /in/ontop.properties \
      -o "/out/$name.nt" -f ntriples >/dev/null 2>&1 \
    && log "$name: done ($(wc -l < "$out/$name.nt" 2>/dev/null || echo '?') triples)" \
    || log "$name: materialize FAILED (check mapping/db)"
}

# --- AMBROSIA: load 846 DBs into MySQL, materialize each, concat -> one .nt ----
kgqa_ambrosia(){
  local src="$BENCH/../sources/AMBROSIA/data"
  if [ ! -d "$src" ]; then
    log "AMBROSIA source not found ($src) — see datasets/ambrosia/DATA_ACCESS.md; skipping"
    return
  fi
  log "== AMBROSIA: loading 846 DBs into MySQL (via load/load_ambrosia.py) =="
  python "$HERE/load/load_ambrosia.py" || { log "load_ambrosia.py failed (need mysql-connector-python)"; return; }
  local out="$DATASETS/ambrosia/rdf"; mkdir -p "$out"; : > "$out/ambrosia.nt"
  local onto_dir="$DATASETS/ambrosia/ontology"
  local n=0
  while IFS= read -r mp; do
    local base; base=$(basename "$mp" .r2rml.ttl)
    local domain; domain=$(basename "$(dirname "$mp")")
    local schema="amb_${base}"
    local onto; onto=$(ls "$onto_dir/$(echo "$domain" | tr 'A-Z' 'a-z').ttl" 2>/dev/null | head -1)
    local work="$HERE/.ontop/mat_amb_$base"; rm -rf "$work"; mkdir -p "$work"
    cat > "$work/ontop.properties" <<EOF
jdbc.url=jdbc:mysql://bench_ambrosia_mysql:3306/${schema}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC
jdbc.user=ambrosia
jdbc.password=ambrosia
jdbc.driver=com.mysql.cj.jdbc.Driver
EOF
    cp "$mp" "$work/mapping.ttl"; local oarg=""
    [ -n "${onto:-}" ] && { cp "$onto" "$work/ontology.ttl"; oarg="-t /in/ontology.ttl"; }
    docker run --rm --network "$NET" \
      -v "$(hostpath "$work"):/in:ro" -v "$(hostpath "$work"):/out" \
      -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
      "$ONTOP_IMAGE" ontop materialize -m /in/mapping.ttl $oarg -p /in/ontop.properties \
        -o /out/part.nt -f ntriples >/dev/null 2>&1 && cat "$work/part.nt" >> "$out/ambrosia.nt"
    rm -rf "$work"; n=$((n+1))
    [ $((n % 50)) -eq 0 ] && log "   ...$n/846 AMBROSIA DBs materialized"
  done < <(find "$DATASETS/ambrosia/mappings" -name '*.r2rml.ttl' | sort)
  log "AMBROSIA: $n DBs -> rdf/ambrosia.nt ($(wc -l < "$out/ambrosia.nt" 2>/dev/null || echo '?') triples)"
}

# --- WebQSP: DO NOT materialize; unpack the shipped Zenodo graph ---------------
kgqa_webqsp(){
  local gz; gz=$(ls "$DATASETS/webqsp/graph/"*.nt.gz 2>/dev/null | head -1)
  if [ -z "${gz:-}" ]; then
    log "WebQSP graph not found — run setup/download_data.sh webqsp (it is NOT materialized; too large)"
    return
  fi
  local out="$DATASETS/webqsp/rdf"; mkdir -p "$out"
  log "== WebQSP: using the prebuilt graph (not materialized) =="
  if [ ! -f "$out/webqsp.nt" ]; then
    log "   unpacking $(basename "$gz") -> rdf/webqsp.nt (668M triples, ~83 GB) ..."
    gzip -dc "$gz" > "$out/webqsp.nt"
  fi
  log "WebQSP: rdf/webqsp.nt ready."
}

# ---------------------------------------------------------------- main
start_backends
case "$TARGET" in
  all)      kgqa_noise; kgqa_ambrosia; kgqa_webqsp ;;
  noise)    kgqa_noise ;;
  ambrosia) kgqa_ambrosia ;;
  webqsp)   kgqa_webqsp ;;
  *) echo "usage: $0 [all|noise|ambrosia|webqsp]"; exit 1 ;;
esac
log "done. RDF graphs are in datasets/<ds>/rdf/*.nt — load them into your triplestore."
