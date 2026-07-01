#!/usr/bin/env bash
# Fetch the benchmark data that is NOT stored in git.
#
#   - Open datasets + the WebQSP 668M RDF graph  -> downloaded from Zenodo
#   - Restricted datasets (eICU, MIMIC-III, AMBROSIA) -> you must obtain them yourself
#
# Usage: ./download_data.sh [all|webqsp|noise]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DATASETS="$(cd "$HERE/.." && pwd)/datasets"
TARGET="${1:-all}"

# ---- SET THIS after you publish the Zenodo record --------------------------
# Zenodo gives every record a stable DOI + direct file URLs of the form:
#   https://zenodo.org/records/<RECORD_ID>/files/<filename>?download=1
ZENODO_RECORD="REPLACE_WITH_ZENODO_RECORD_ID"
ZBASE="https://zenodo.org/records/${ZENODO_RECORD}/files"
# ---------------------------------------------------------------------------

OPEN_NOISE=(bsbm cwd cwe_secutable gtfs lubm npd)   # eICU + mimic_iii are NOT here (restricted)

log(){ echo -e "\033[1;32m[download]\033[0m $*"; }

check_zenodo(){
  if [ "$ZENODO_RECORD" = "REPLACE_WITH_ZENODO_RECORD_ID" ]; then
    echo "ERROR: set ZENODO_RECORD in this script to the published Zenodo record id first." >&2
    echo "       (Until then, the open data can be rebuilt from each dataset's original source —" >&2
    echo "        see datasets/<ds>/ATTRIBUTION.md.)" >&2
    exit 2
  fi
}

get(){  # get <filename> <dest>
  local url="$ZBASE/$1?download=1" dest="$2"
  log "fetching $1 ..."
  curl -fL --retry 3 -o "$dest" "$url"
}

download_webqsp(){
  check_zenodo
  mkdir -p "$DATASETS/webqsp/graph"
  get "webqsp_vkg_graph.nt.gz" "$DATASETS/webqsp/graph/webqsp_vkg_graph.nt.gz"
  log "WebQSP graph ready."
}

download_noise(){
  check_zenodo
  for ds in "${OPEN_NOISE[@]}"; do
    get "${ds}_data.zip" "$DATASETS/$ds/data.zip"
  done
  log "open noise datasets ready."
}

case "$TARGET" in
  all)    download_webqsp; download_noise ;;
  webqsp) download_webqsp ;;
  noise)  download_noise ;;
  *) echo "usage: $0 [all|webqsp|noise]"; exit 1 ;;
esac

cat <<'NOTE'

------------------------------------------------------------------------------
Restricted datasets are NOT downloaded here (license) — obtain them yourself:
  - eICU       -> datasets/eicu/DATA_ACCESS.md       (PhysioNet credentialed)
  - MIMIC-III  -> datasets/mimic_iii/DATA_ACCESS.md  (PhysioNet credentialed)
  - AMBROSIA   -> datasets/ambrosia/DATA_ACCESS.md   (authors' request)
------------------------------------------------------------------------------
NOTE
