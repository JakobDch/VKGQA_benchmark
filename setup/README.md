# Benchmark setup — one command

Bring the whole benchmark up as live SPARQL endpoints with a single script. Two modes:

- **VKG mode (default)** — start the backing databases, load the data, and expose each
  dataset through an **Ontop** SPARQL endpoint (query the relational data virtually).
- **Materialize mode (optional)** — turn each VKG into a real RDF graph on disk.

WebQSP is special: its 668M-triple RDF graph **ships pre-built** in
`../datasets/webqsp/graph/webqsp_vkg_graph.nt.gz`, so you never have to materialize it.
The setup bulk-loads it into a Virtuoso triplestore.

## Requirements

**Software (all platforms):**
- **Docker + Docker Compose** (Docker Desktop on Windows/macOS). This is the only hard
  dependency — Postgres, MySQL, Virtuoso and Ontop all run as containers, nothing is
  installed on the host.
- `unzip` (or PowerShell `Expand-Archive` on Windows — the `.ps1` uses it automatically).
- **Only for AMBROSIA**: `python` + `pip install mysql-connector-python` (to load the 846 DBs).
- On **Windows**, run `start_benchmark.ps1` (PowerShell), not the `.sh`. In Docker Desktop,
  make sure the drive holding this folder is enabled under *Settings → Resources → File sharing*.

**Disk — you do NOT need it all; each part is independent.** Pick what you start:

| Part | What it needs on disk | Notes |
|---|---|---|
| **noise** (8 datasets) | ~1–2 GB | small dumps → Postgres |
| **AMBROSIA** (846 DBs) | ~0.5 GB | tiny DBs → MySQL |
| **WebQSP** | **~130 GB total** ⚠️ | 5.7 GB shipped `.nt.gz` → **~83 GB** unzipped `.nt` + **~30–40 GB** Virtuoso DB. This is by far the heaviest part. |
| **materialize mode** (optional) | +a few GB per noise dataset | writes `<ds>.nt` files |

So: **noise + AMBROSIA alone need only ~3–4 GB**. The big cost is WebQSP's 668M-triple
graph. If you don't need WebQSP, just run `start_benchmark.sh noise` / `ambrosia`.

**RAM:**
- noise + AMBROSIA endpoints: ~1–2 GB each Ontop JVM; a few running at once → 4–8 GB is fine.
- **WebQSP / Virtuoso: give it real memory** — 8 GB minimum, 16 GB+ recommended for
  668M triples (the compose file sets Virtuoso's buffer count accordingly).

**Time (first run):** noise ~2–5 min; AMBROSIA load ~10–20 min (846 schemas); WebQSP
Virtuoso bulk-load of 668M triples **can take 30–90 min** and is disk-heavy. Subsequent
starts are fast (data persists in Docker volumes).

## Quick start (Linux/macOS/WSL)

```bash
cd benchmark/setup
./start_benchmark.sh            # backends + load all + start endpoints
# or a single group:
./start_benchmark.sh noise      # the 8 noise datasets  (Postgres + Ontop)
./start_benchmark.sh webqsp     # WebQSP 668M RDF -> Virtuoso
./start_benchmark.sh ambrosia   # AMBROSIA schemas -> MySQL
```

Windows (PowerShell): use `start_benchmark.ps1` with the same arguments.

## What comes up

| Service | Port (localhost) | What |
|---|---|---|
| Postgres (noise) | 55432 | 8 noise datasets, one db each |
| MySQL (ambrosia) | 3307 | 846 AMBROSIA schemas |
| Virtuoso (webqsp) | 8890 | WebQSP 668M RDF; SPARQL at `/sparql` |
| Ontop per noise ds | 13001… | one SPARQL endpoint per noise dataset |
| Ontop per AMBROSIA db | 14080 (on demand) | started individually, see below |

After startup, `docker ps` lists every running endpoint with its port.

## AMBROSIA (846 databases)

AMBROSIA has 846 tiny databases. Running 846 Ontop endpoints at once is wasteful, so:

1. `start_benchmark.sh ambrosia` creates the MySQL schemas and (via `load/load_ambrosia.py`)
   loads the data from your local AMBROSIA source.
2. Start an endpoint for **one** case when you need it:
   ```bash
   ./run_ontop_ambrosia.sh scope_agricultural_machinery_stores_brands 14080
   # -> http://localhost:14080/sparql
   ```

> AMBROSIA source DBs are **not** bundled (license). Obtain them and place under
> `sources/AMBROSIA/data/` — see `../datasets/ambrosia/DATA_ACCESS.md`.

## Materialize mode (optional)

```bash
./materialize_all.sh    # each noise VKG -> datasets/<ds>/materialized/<ds>.nt
```
WebQSP is skipped (already RDF). Run `start_benchmark.sh` first so the DBs are loaded.

## Querying the ground truth

The CHOICE-DSL ground truth in `../queries/choice_dsl_gt/` is expanded to concrete
SPARQL by `../dsl_choice_expander/`. Point the expander's endpoint at the relevant
service above (e.g. WebQSP → `http://localhost:8890/sparql`, a noise dataset → its
Ontop port). See the top-level `../README.md` for the evaluation protocol.

## Tear down

```bash
docker rm -f $(docker ps -aq --filter "name=bench_ontop_")   # all Ontop endpoints
docker compose -f docker-compose.yml down                    # backends (add -v to wipe data)
```
