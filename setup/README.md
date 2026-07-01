# Benchmark setup — choose your mode

First decide **how you want to query the data** — this benchmark supports two settings,
and you pick one:

| Mode | Script | What it does |
|---|---|---|
| **VKGQA** — Virtual KG | `start_vkgqa.sh` | Loads the relational data into Postgres/MySQL and serves each dataset as a live **Ontop** SPARQL endpoint over its R2RML mapping + ontology. Nothing is materialized; queries are answered virtually. |
| **KGQA** — native KG | `start_kgqa.sh` | **Materializes** each dataset to a real RDF graph (`datasets/<ds>/rdf/<ds>.nt`) that you load into the triplestore of your choice. |

**WebQSP is special in KGQA mode:** its 668M-triple graph is *not* re-materialized (that
takes hours). It ships pre-built as `datasets/webqsp/graph/webqsp_vkg_graph.nt.gz` (from
Zenodo); `start_kgqa.sh webqsp` just unpacks it into `datasets/webqsp/rdf/webqsp.nt`.
(In VKGQA mode, WebQSP is served from its PostgreSQL dump via Ontop like the others.)

Windows: use the `.ps1` equivalents.

## Requirements

**Software (all platforms):**
- **Docker + Docker Compose** (Docker Desktop on Windows/macOS). This is the only hard
  dependency — Postgres, MySQL, Virtuoso and Ontop all run as containers, nothing is
  installed on the host.
- `unzip` (or PowerShell `Expand-Archive` on Windows — the `.ps1` uses it automatically).
- **Only for AMBROSIA**: `python` + `pip install mysql-connector-python` (to load the 846 DBs).
- On **Windows**, run `start_vkgqa.ps1` (PowerShell), not the `.sh`. In Docker Desktop,
  make sure the drive holding this folder is enabled under *Settings → Resources → File sharing*.

**Disk — you do NOT need it all; each part is independent.** Pick what you start:

| Part | What it needs on disk | Notes |
|---|---|---|
| **noise** (6 datasets) | ~1–2 GB | small dumps → Postgres |
| **AMBROSIA** (846 DBs) | ~0.5 GB | tiny DBs → MySQL |
| **WebQSP (VKGQA)** | ~5.2 GB download → ~85 GB restored PostgreSQL | pg_restore + Ontop |
| **WebQSP (KGQA)** | 5.7 GB `.nt.gz` → **~83 GB** unzipped `.nt` | by far the heaviest part |
| **KGQA materialization** | +a few GB per noise dataset | writes `rdf/<ds>.nt` files |

So: **noise + AMBROSIA alone need only ~3–4 GB**. The big cost is WebQSP's 668M-triple
graph. If you don't need WebQSP, just run `start_vkgqa.sh noise` / `ambrosia`.

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
./start_vkgqa.sh            # backends + load all + start endpoints
# or a single group:
./start_vkgqa.sh noise      # the 6 noise datasets  (Postgres + Ontop)
./start_vkgqa.sh webqsp     # WebQSP 668M RDF -> Virtuoso
./start_vkgqa.sh ambrosia   # AMBROSIA schemas -> MySQL
```

Windows (PowerShell): use `start_vkgqa.ps1` with the same arguments.

## What comes up

| Service | Port (localhost) | What |
|---|---|---|
| Postgres (noise) | 55432 | 6 noise datasets, one db each |
| MySQL (ambrosia) | 3307 | 846 AMBROSIA schemas |
| Virtuoso (webqsp) | 8890 | WebQSP 668M RDF; SPARQL at `/sparql` |
| Ontop per noise ds | 13001… | one SPARQL endpoint per noise dataset |
| Ontop per AMBROSIA db | 14080 (on demand) | started individually, see below |

After startup, `docker ps` lists every running endpoint with its port.

## AMBROSIA (846 databases)

AMBROSIA has 846 tiny databases. Running 846 Ontop endpoints at once is wasteful, so:

1. `start_vkgqa.sh ambrosia` creates the MySQL schemas and (via `load/load_ambrosia.py`)
   loads the data from your local AMBROSIA source.
2. Start an endpoint for **one** case when you need it:
   ```bash
   ./run_ontop_ambrosia.sh scope_agricultural_machinery_stores_brands 14080
   # -> http://localhost:14080/sparql
   ```

> AMBROSIA source DBs are **not** bundled (license). Obtain them and place under
> `sources/AMBROSIA/data/` — see `../datasets/ambrosia/DATA_ACCESS.md`.

## KGQA mode (materialize to native RDF)

Instead of the virtual Ontop endpoints, produce real RDF graphs you load into your own
triplestore:

```bash
./start_kgqa.sh            # noise + AMBROSIA + WebQSP graph
./start_kgqa.sh noise      # each noise KG   -> datasets/<ds>/rdf/<ds>.nt
./start_kgqa.sh ambrosia   # all 846 AMBROSIA DBs -> datasets/ambrosia/rdf/ambrosia.nt
./start_kgqa.sh webqsp     # unpack the shipped 668M graph -> datasets/webqsp/rdf/webqsp.nt
```

`start_kgqa.sh` brings up the databases, materializes each mapping with `ontop
materialize`, and writes `.nt` files. **WebQSP is not materialized** (too large) — its
prebuilt graph is unpacked instead. Load the resulting `.nt` files into Virtuoso / Fuseki /
Blazegraph / GraphDB / … yourself.

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
