#!/usr/bin/env bash
# Optional: materialize every VKG dataset to a real RDF graph (N-Triples), instead of
# querying it live via Ontop. Uses `ontop materialize` over each dataset's mapping+DB.
#
# WebQSP is SKIPPED: its RDF graph (668M triples) already ships in
# datasets/webqsp/graph/webqsp_vkg_graph.nt.gz — no need to re-materialize (hours).
#
# Output: datasets/<ds>/materialized/<ds>.nt
# Prereq: run start_benchmark.sh first (backends up + data loaded).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
DATASETS="$BENCH/datasets"
NET=bench_net
ONTOP_IMAGE=ontop/ontop:5.4.0
JDBC_DIR="$HERE/jdbc"
NOISE_SETS=(bsbm cwd cwe_secutable eicu gtfs lubm mimic_iii npd)
export MSYS_NO_PATHCONV=1
hostpath(){ case "$1" in /?/*) echo "$1" | sed -E 's#^/([a-zA-Z])/#\1:/#';; *) echo "$1";; esac; }

log(){ echo -e "\033[1;35m[materialize]\033[0m $*"; }

materialize_pg(){
  local ds="$1" dir="$DATASETS/$1"
  local mapping; mapping=$(ls "$dir"/mapping/*.r2rml.ttl 2>/dev/null | head -1)
  local ontology; ontology=$(ls "$dir"/ontology/*.ttl "$dir"/ontology/*.owl 2>/dev/null | head -1)
  [ -n "${mapping:-}" ] || { log "$ds: no mapping, skip"; return; }
  local out="$dir/materialized"; mkdir -p "$out"
  local work="$HERE/.ontop/mat_$ds"; rm -rf "$work"; mkdir -p "$work"
  cat > "$work/ontop.properties" <<EOF
jdbc.url=jdbc:postgresql://bench_noise_pg:5432/$ds
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
EOF
  cp "$mapping" "$work/mapping.ttl"
  local onto_arg=""
  if [ -n "${ontology:-}" ]; then cp "$ontology" "$work/ontology.ttl"; onto_arg="-t /in/ontology.ttl"; fi
  log "$ds: materializing -> materialized/$ds.nt"
  docker run --rm --network "$NET" \
    -v "$(hostpath "$work"):/in:ro" -v "$(hostpath "$out"):/out" \
    -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
    "$ONTOP_IMAGE" ontop materialize \
      -m /in/mapping.ttl $onto_arg -p /in/ontop.properties \
      -o "/out/$ds.nt" -f ntriples >/dev/null 2>&1 \
    && log "$ds: done ($(wc -l < "$out/$ds.nt" 2>/dev/null || echo '?') triples)" \
    || log "$ds: materialize FAILED (check mapping/db)"
}

log "materializing noise VKGs (WebQSP skipped — ships as RDF already) ..."
for ds in "${NOISE_SETS[@]}"; do materialize_pg "$ds"; done
log "AMBROSIA: materialize per-DB is expensive (846 tiny DBs). Use run_ontop_ambrosia.sh"
log "         + 'ontop materialize' per case if you need RDF for a specific AMBROSIA db."
log "done."
