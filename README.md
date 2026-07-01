# Ambiguity VKGQA Benchmark

A benchmark for evaluating (Virtual) Knowledge-Graph Question-Answering systems on
**ambiguous natural-language queries** — questions that have more than one legitimate
interpretation, each with its own correct answer set.

The core idea: a system should not silently *guess* one reading of an ambiguous
question. It should **detect** the ambiguity and account for *all* admissible
interpretations. This benchmark provides the data, the ambiguous questions, and a
machine-checkable ground truth to measure exactly that.

---

## Getting started

Everything runs in **Docker** — nothing is installed on the host. One command brings a
part (or all) of the benchmark up as live SPARQL endpoints:

```bash
cd setup
./start_benchmark.sh noise      # 6 noise datasets    (~3 GB disk, minutes)
./start_benchmark.sh ambrosia   # 846 AMBROSIA DBs    (~0.5 GB disk)
./start_benchmark.sh webqsp     # WebQSP 668M (VKG dump preferred, else RDF) ⚠️ large
./start_benchmark.sh            # all of the above
# force one WebQSP form:  ./start_benchmark.sh webqsp-vkg   |   webqsp-rdf
```
Windows: use `setup\start_benchmark.ps1`.

**Requirements at a glance** — the only hard dependency is Docker (+ Compose). Disk and
RAM depend on which parts you start; the parts are independent, so you need **only what
you run**:

| If you start… | Disk | RAM |
|---|---|---|
| noise + AMBROSIA | ~3–4 GB | ~4–8 GB |
| WebQSP as **VKG** (PG dump) | ~5.2 GB download → ~85 GB restored PostgreSQL | 8 GB+ |
| WebQSP as **native RDF** (graph) | 5.7 GB `.nt.gz` → ~83 GB unzipped → ~30–40 GB triplestore | 8 GB min, 16 GB+ rec. |

See **[setup/README.md](setup/README.md)** for the full requirements table, ports,
per-dataset details, tear-down, and the optional *materialize* mode.

### Getting the data

This repository contains only small, license-clean artefacts (mappings, ontologies,
questions, ground truth, scripts). The **data** is fetched separately:

```bash
cd setup
./download_data.sh all     # open datasets + WebQSP (PG dump + RDF graph), from Zenodo
```
The restricted dataset (AMBROSIA) is **not** downloadable — obtain it yourself per
`datasets/ambrosia/DATA_ACCESS.md`. Full breakdown of every dataset's source, license,
and distribution channel: **[DATASET_LICENSES.md](DATASET_LICENSES.md)**.

> Licensing: our artefacts are **CC BY 4.0** ([LICENSE](LICENSE)); each dataset's
> underlying data keeps its own license — you must comply with both.

---

## Folder structure

```
benchmark/
├── datasets/                     # the federated data layer (as VKGs via R2RML)
│   ├── ambrosia/                 #   16 domains, synthetic DBs (ambiguity-by-design)
│   │   ├── mappings/  <Domain>/*.r2rml.ttl
│   │   ├── ontology/  <domain>.ttl
│   │   └── DATA_ACCESS.md        #   AMBROSIA source data is NOT redistributed (see file)
│   ├── webqsp/                   #   Freebase (real user questions)
│   │   ├── mappings/  webqsp_big.r2rml.ttl
│   │   └── DATA_ACCESS.md        #   Freebase/VKG is external (see file)
│   └── <noise>/                  #   bsbm, cwd, cwe_secutable, gtfs, lubm, npd —
│       ├── mapping/              #   extra federated domains that
│       ├── ontology/             #   act as distractors ("noise"); no GT of their own
│       └── data.zip              #   the raw data (dumps/CSV) for that dataset
│
├── queries/
│   ├── nl_queries/               # the natural-language questions
│   │   ├── webqsp_nl.json        #   236 real, schema-naive user questions
│   │   └── ambrosia_nl.json      #   1444 ambiguity-targeted questions
│   └── choice_dsl_gt/            # the ground truth: ambiguity as CHOICE-DSL + readings
│       ├── webqsp/webqsp_ambiguity_gt.json
│       └── ambrosia/<Domain>/*.json
│
├── dsl_choice_expander/          # the deterministic CHOICE-DSL → SPARQL expander
│   ├── src/ambiguity/            #   dsl.py (parser) · expander.py · feedback.py
│   └── DINA_AMBIGUITY_README.md  #   full expander documentation
└── README.md                     # this file
```

> **Note.** Per-class semantic models (CSMs) are intentionally *not* part of this
> benchmark folder — how a system explores/represents the VKG schema (labels,
> retrieval, etc.) is left to each user. The benchmark fixes only the data, the
> questions, and the answer-verified ground truth.

---

## The two question sources

| | **WebQSP** | **AMBROSIA** |
|---|---|---|
| Data | full Freebase (real KG) | synthetic per-domain DBs |
| Questions | **real** Google-Suggest user questions, schema-naive | ambiguity-targeted (template + human paraphrase) |
| Ambiguity | **discovered** data-drivenly (post-hoc) | **built in** by construction |
| # ambiguous | 236 | 1444 |

They are complementary: WebQSP shows whether a system copes with ambiguity that
occurs *naturally* in real questions; AMBROSIA gives controlled, per-type coverage
(scope / attachment / vagueness).

The other `datasets/` (bsbm, gtfs, npd, …) carry **no ground-truth queries**. They
are *federated noise*: additional domains loaded alongside, to test robustness at
scale (e.g. whether small/rare topics get lost in a large federated system).

---

## Ambiguity types (after AMBROSIA, Saparina & Lapata, NeurIPS 2024, §3.2)

- **scope** — quantifier/collective-vs-distributive ("brands available in *each* store"
  = per store, or common to all stores?).
- **attachment** — a modifier attaches to one operand or to several ("Boeing and Airbus
  models with 180 seats" — does "180 seats" apply to both?).
- **vagueness** — an underspecified term maps to more than one schema element
  ("aircraft family" = manufacturer name or model name?).

A question is treated as ambiguous when it admits ≥2 non-equivalent interpretations
that yield **different answer sets** over the data (AMBROSIA Def. 2).

---

## How the CHOICE-DSL ground truth works

Rather than storing "one question → one gold SPARQL", each ambiguous question is
stored as **one ambiguous query in a CHOICE-DSL** that marks *every* ambiguous spot
with a **choice node**, using only vocabulary from the schema. A deterministic
**expander** unfolds that single query into the full set of unambiguous, valid
SPARQL queries — one per interpretation — executes each against the endpoint, and
returns the union of admissible answers.

Two kinds of choice node:

```sparql
SELECT ?wellbore WHERE {
  CHOICE wellClass {                                   # structural choice (whole graph pattern)
    borehole:    { ?wellbore a eno:Borehole . }
    exploration: { ?wellbore a eno:ExplorationWellbore . }
  }
  ?wellbore <<depthProp: eno:totalDrillDepth | eno:finalVerticalDrillDepth>> ?d .  # term choice (one slot)
}
```

- **term choice** `<<name: A | B>>` — the same query shape, one slot filled by A or B.
- **structural choice** `CHOICE name { opt0 {…} opt1 {…} }` — whole alternative graph patterns.

Expanding this yields the Cartesian product of the choices = the set of readings.
Each reading is a plain, valid SPARQL query whose answers are the gold answer set
of that interpretation.

**Why this design.** The hard, uncertain part — mapping ambiguous language to schema
elements — is exactly what a QA system must get right, and the DSL makes that
uncertainty *explicit* (as choice nodes) instead of hidden behind a single guess.
The structural part — turning the choices into valid SPARQL and running them — is
deterministic and provably correct, so it needs no model. This cleanly separates
*"did the system detect the ambiguity and its readings?"* (what we evaluate) from
*"can it emit valid SPARQL?"* (mechanical).

---

## Evaluating a system

A system under test is given a natural-language question (from `nl_queries/`) and,
if it is ambiguity-aware, should produce its own CHOICE-DSL (or an equivalent set of
interpretations). Compare against the ground truth by:

1. **Ambiguity detection** — did it flag the question as ambiguous at all?
2. **Reading coverage** — do its interpretations match the GT readings
   (set-equality on the answer sets each reading yields, via the expander)?
3. **Type** (optional) — does it identify scope / attachment / vagueness correctly?

Because the GT is answer-verified against live KG **and** VKG endpoints, a candidate
reading counts as correct when its answer set equals a GT reading's answer set — not
by string-matching SPARQL.

### Using the expander

`dsl_choice_expander/src/ambiguity/` is the reference implementation:

- `parse_ambiguous_query(text)` → AND-OR tree
- `expand(tree)` → the list of unambiguous SPARQL queries (the readings)
- `execute_all(...)` / `answer_set(...)` → run against an Ontop/SPARQL endpoint and
  collect admissible answers
- `evaluate_ambiguous_query(...)` → convenience: parse → expand → execute → feedback

See `DINA_AMBIGUITY_README.md` for the full grammar and API.

---

## Provenance & licensing

- **AMBROSIA** source DBs: © Saparina & Lapata, CC BY 4.0, **not redistributed here**
  (see `datasets/ambrosia/DATA_ACCESS.md`). Only our R2RML/ontology/GT derivatives are included.
- **WebQSP** questions: Microsoft Research; **Freebase**: public RDF dump. Data is
  external (see `datasets/webqsp/DATA_ACCESS.md`).
- **Noise datasets** (bsbm, cwd, cwe_secutable, gtfs, lubm, npd): permissively licensed
  (Apache 2.0 / CC BY 4.0 / NLOD); see each dataset's `ATTRIBUTION.md` for source + license.
- **CHOICE-DSL expander**: from the `dina_ambiguity` project.
