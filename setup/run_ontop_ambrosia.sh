#!/usr/bin/env bash
# Start an Ontop SPARQL endpoint for ONE AMBROSIA database (on demand).
# AMBROSIA has 846 tiny DBs — running all endpoints at once is wasteful, so each
# is started individually when needed.
#
# Usage: ./run_ontop_ambrosia.sh <db_base> [host_port]
#   db_base    e.g. scope_agricultural_machinery_stores_brands
#   host_port  default 14080
#
# Finds the matching mapping + domain ontology automatically.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
DB_BASE="${1:?usage: run_ontop_ambrosia.sh <db_base> [port]}"
PORT="${2:-14080}"
NET=bench_net
ONTOP_IMAGE=ontop/ontop:5.4.0
JDBC_DIR="$HERE/jdbc"
SCHEMA="amb_${DB_BASE}"
export MSYS_NO_PATHCONV=1
hostpath(){ case "$1" in /?/*) echo "$1" | sed -E 's#^/([a-zA-Z])/#\1:/#';; *) echo "$1";; esac; }

# locate mapping (per-DB) + ontology (per-domain) under benchmark/datasets/ambrosia
MAPPING=$(find "$BENCH/datasets/ambrosia/mappings" -name "${DB_BASE}.r2rml.ttl" | head -1)
[ -n "$MAPPING" ] || { echo "no mapping for $DB_BASE"; exit 1; }
DOMAIN=$(basename "$(dirname "$MAPPING")")                       # e.g. Agriculture
ONTO=$(ls "$BENCH/datasets/ambrosia/ontology/$(echo "$DOMAIN" | tr 'A-Z' 'a-z').ttl" 2>/dev/null | head -1)

WORK="$HERE/.ontop/amb_${DB_BASE}"; rm -rf "$WORK"; mkdir -p "$WORK"
cat > "$WORK/ontop.properties" <<EOF
jdbc.url=jdbc:mysql://bench_ambrosia_mysql:3306/${SCHEMA}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC
jdbc.user=ambrosia
jdbc.password=ambrosia
jdbc.driver=com.mysql.cj.jdbc.Driver
EOF
cp "$MAPPING" "$WORK/mapping.ttl"
ONTO_ARG=""
if [ -n "${ONTO:-}" ]; then cp "$ONTO" "$WORK/ontology.ttl"; ONTO_ARG="-t /opt/ontop/input/ontology.ttl"; fi

NAME="bench_ontop_amb_${PORT}"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --network "$NET" \
  -p "127.0.0.1:${PORT}:8080" \
  -v "$(hostpath "$WORK"):/opt/ontop/input:ro" \
  -v "$(hostpath "$JDBC_DIR"):/opt/ontop/jdbc:ro" \
  "$ONTOP_IMAGE" ontop endpoint \
    -m /opt/ontop/input/mapping.ttl $ONTO_ARG -p /opt/ontop/input/ontop.properties >/dev/null
echo "AMBROSIA $DB_BASE (schema $SCHEMA) SPARQL -> http://localhost:${PORT}/sparql"
