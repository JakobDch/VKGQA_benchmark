# dina-ambiguity — Ambiguity-emitting Text-to-SPARQL

> This repository is a headless fork of the agentic Text-to-SPARQL pipeline.
> Instead of resolving ambiguity interactively (clarification questions, data
> feedback, the variable gate), the system makes ambiguity **explicit**.

## What it does

The LLM agent does not write a finished SPARQL query and does not guess. It
writes a single **ambiguous query** in a CHOICE-DSL that leaves a *choice node*
at every ambiguous spot — using only vocabulary from the schema. A deterministic
**expander** then unfolds that query into the set of unambiguous, valid SPARQL
queries (the full set of admissible interpretations), executes each against the
Ontop endpoint, and returns the union of admissible answers with provenance.

Division of labour (the whole point): the uncertain part — mapping language to
schema — is the LLM's job, and it makes its uncertainty explicit; the structural
part — producing valid queries and running them — is deterministic and correct,
so it needs no LLM. This makes it possible to evaluate how well KGQA/VKGQA
systems *detect* ambiguity in NL queries.

### Components

| Module | Role |
| --- | --- |
| [src/ambiguity/dsl.py](src/ambiguity/dsl.py) | CHOICE-DSL grammar + parser → AND-OR tree |
| [src/ambiguity/expander.py](src/ambiguity/expander.py) | expand → execute → admissible answer set |
| [src/agents/generation/ambiguity_agent.py](src/agents/generation/ambiguity_agent.py) | LLM agent that emits the ambiguous query |
| [src/agents/ambiguity_pipeline.py](src/agents/ambiguity_pipeline.py) | HITL-free pipeline (retrieval → ambiguity gen) |
| [scripts/run_ambiguity.py](scripts/run_ambiguity.py) | CLI: one NL query → ambiguous query → answer set |

### CHOICE-DSL in one glance

```
SELECT ?wellbore WHERE {
  CHOICE wellClass {                                  # structural choice
    borehole:    { ?wellbore a eno:Borehole . }
    exploration: { ?wellbore a eno:ExplorationWellbore . }
  }
  ?wellbore <<depthProp: eno:totalDrillDepth | eno:finalVerticalDrillDepth>> ?d .  # term choice
  FILTER(?d > 3000)
}
```

`<< name: a | b >>` is an inline term choice; `CHOICE name { opt: { ... } }` is a
structural choice over whole graph patterns. Choices nest.

### Usage

```bash
pip install -e .                       # into a dedicated venv (avoids the
                                       # src/ + data/ package shadowing across
                                       # the sibling dina projects)

# one query, generate + expand + execute against Ontop
python scripts/run_ambiguity.py --query "Which wells reach below 3 kilometers?" --execute

# from the evaluation corpus, write a JSON report
python scripts/run_ambiguity.py --query-id SYN18 --execute --out reports/syn18.json

# generate + expand only, no execution
python scripts/run_ambiguity.py --query "Show top products." --no-execute
```

Execution routes endpoints from each query's PREFIXes and requires the
slot-based Ontop containers reachable over the SSH tunnel (the CLI runs the
tunnel preflight unless `--no-tunnel`).

### Tests

```bash
pytest tests/            # DSL parser + expander unit tests (no network)
```

---

## Inherited pipeline (upstream context)

The sections below describe the upstream agentic Text-to-SPARQL pipeline this
fork is built on. The HITL study UI (backend/frontend), the study modules, and
the CHESS Text-to-SQL tool have been removed; the core retrieval/generation
pipeline and the five datasets remain and are reused by the ambiguity mode.

The codebase implements three pipelines that are compared on the same
natural-language query corpus:

1. **Agentic-Grep** — a tool-using agent that retrieves schema fragments
   via lexical/grep search over OBDA mappings.
2. **Agentic-Semantic** — a tool-using agent that retrieves schema
   fragments via dense embedding search.
3. **Text2SQL (CHESS)** — Stanford's CHESS pipeline (vendored under
   [tools/chess/](tools/chess/)) used as a Text-to-SQL reference
   baseline.

The five evaluation datasets are EDU (LUBM), TRN (GTFS), NRG (Norwegian
Petroleum Directorate), BSBM (Berlin SPARQL Benchmark) and LCA, plus a
heterogeneous combined configuration.

## Repository layout

```
.
|-- src/                       # Source for the agentic SPARQL pipeline
|   |-- agents/                # Orchestrator + retrieval/generation agents
|   |-- baseline/              # Shared LLM/metric helpers used by the runner
|   |-- concurrency/           # Slot manager for parallel container access
|   |-- endpoints/             # OnTop SPARQL endpoint client
|   |-- evaluation/            # Tiered ESSENTIAL/PREFERRED metrics + runner
|   |-- models/                # Pydantic data models
|   |-- tools/                 # SPARQL/mapping tools called by agents
|   |-- tracing/               # Trace collection and rendering
|   |-- utils/                 # Query validators and OnTop hints
|   `-- validation/            # Schema graph + semantic validator
|-- scripts/                   # Experiment runner, dataset converters, dashboards
|-- mappings/                  # OnTop OBDA mappings (Turtle) per dataset
|-- data/queries/              # NL query corpus and tiered ground truth
|-- config/mysql/              # MySQL configuration used by the OnTop containers
|-- docker-compose.yml         # Base services (MySQL + one OnTop per dataset)
|-- docker-compose.slots.yml   # Slot overlay (parallel OnTop containers)
|-- Dockerfile.ontop           # Image for the OnTop endpoints
|-- tools/chess/               # Vendored CHESS Text-to-SQL pipeline (Apache 2.0)
`-- pyproject.toml
```

## Setup

Requires Python 3.11+ and Docker (for the OnTop SPARQL endpoints).

```bash
pip install -e .
cp .env.example .env   # then fill in API keys for the providers you use
```

The `.env.example` file lists the supported LLM providers. You only need
keys for the providers you intend to evaluate.

### SPARQL endpoints

The agentic pipeline queries OnTop endpoints that expose relational
datasets as RDF via OBDA mappings. The deployment used in the paper
launches one OnTop container per dataset and replicates each container
across `N` *slots* so multiple agent runs can hit the database in
parallel without interfering with each other.

```bash
# 1. Initialise per-slot mapping copies (defaults to 5 slots)
python scripts/initialize_slot_mappings.py --slots 5 --clean

# 2. Bring up MySQL + the OnTop slot containers
docker compose -f docker-compose.yml -f docker-compose.slots.yml up -d

# 3. (Optional) Pre-build the embedding index used by the semantic agent
python scripts/preindex_embeddings.py
```

Endpoint URLs default to `http://localhost:8080..8084/sparql`, one per
dataset (EDU, TRN, NRG, BSBM, LCA); the slot variants listen on
neighbouring ports defined in [docker-compose.slots.yml](docker-compose.slots.yml).

### Datasets

The evaluation uses publicly available datasets:

| Code | Source |
|------|--------|
| EDU  | LUBM (Lehigh University Benchmark) |
| TRN  | GTFS public transport feeds |
| NRG  | Norwegian Petroleum Directorate "FactPages" / energy domain |
| BSBM | Berlin SPARQL Benchmark |
| LCA  | Life-cycle assessment data |

Each dataset must be downloaded from its upstream distribution channel.
The conversion scripts under [scripts/convert_*.py](scripts/) and
[scripts/csv_to_sql.py](scripts/csv_to_sql.py) turn the raw
distributions into the relational form expected by the OnTop mappings
in [mappings/](mappings/).

## Running the experiments

### Agentic pipelines

```bash
python scripts/run_full_experiment.py \
    --approach agentic_grep \
    --llm-model deepseek-chat \
    --query-set BASE
```

See `python scripts/run_full_experiment.py --help` for the full set of
flags (model, approach, query subset, output directory). Trace files
land in `results/experiments/<run-id>/`. Re-evaluation against the
tiered ground truth is done with
[scripts/reevaluate_tiered.py](scripts/reevaluate_tiered.py); a small
HTML dashboard is provided by
[scripts/tiered_dashboard.py](scripts/tiered_dashboard.py).

### CHESS (Text2SQL)

CHESS is vendored under [tools/chess/](tools/chess/) together with its
original Apache 2.0 licence. From the project root:

```bash
cd tools/chess
PYTHONUTF8=1 python -u src/main.py \
    --data_mode dev \
    --data_path data/dev/dev.json \
    --config run/configs/CHESS_deepseek.yaml \
    --num_workers 1 \
    --pick_final_sql True
```

Sample CHESS run outputs (with local paths stripped) are kept under
[tools/chess/results/](tools/chess/results/) for reference.

## Evaluation

The evaluation uses a tiered ESSENTIAL/PREFERRED ground-truth design
together with schema, result and path-coherence metrics. Evaluation
entry points live in [scripts/reevaluate_*.py](scripts/) and the
implementation is in [src/evaluation/](src/evaluation/).

## Citation

Citation information will be added once the paper is published.

## Licence

The code in this repository is released under the MIT licence (see
[LICENSE](LICENSE)). Vendored third-party components retain their
original licences:

* [tools/chess/](tools/chess/) is from
  <https://github.com/ShayanTalaei/CHESS> and remains under the Apache
  2.0 licence (see [tools/chess/LICENSE](tools/chess/LICENSE)).

## Study operations (HITL-Leiter-Studie, ESWC 2027)

Operational rules for running the participant study - violations can
silently corrupt the experiment:

1. **Never edit backend code while a run is active.** uvicorn --reload can
   leave a zombie worker holding port 8000 (kill via CIM Terminate).
2. **Back up data/study/study.db before every session** (copy the file; it
   is excluded from git on purpose - participant data never enters the repo).
3. **Config freeze before the pilot:** model (deepseek-chat) and approach
   (agentic_semantic) stay fixed for the whole study.
4. **Baseline/replay batches never run concurrently with participants**
   (the service refuses + waits, do not work around it).
5. **No silent fallbacks.** Study code fails loudly (strict key access,
   validation raises, persisted error markers like snapshot_error and
   eval_results.error). Watch researcher exports for those markers.
6. **Freeze the preregistration** (docs/preregistration.md) via
   `git tag prereg-v1` before the first real participant.

Design and implementation plan: docs/study_redesign_plan.md.
Run `pytest backend/tests -q` before deploying changes.
