# Dataset licenses & how the data is distributed

This benchmark bundles only **our own derived artefacts** (R2RML/OBDA mappings,
ontologies, natural-language questions, CHOICE-DSL ground truth, setup scripts). The
**underlying data** of each dataset keeps its original license and is distributed at the
level that license permits — summarised here.

## Distribution tiers

- **GitHub (this repo):** mappings, ontologies, queries, ground truth, expander, setup —
  all small, all license-clean.
- **Zenodo (DOI):** the large + openly-licensed data — the WebQSP 668M RDF graph and the
  6 open noise datasets. Fetched by `setup/download_data.sh`.
- **Bring-your-own (restricted):** datasets whose license forbids redistribution — you
  obtain them from the original source (see each `DATA_ACCESS.md`).

## Per-dataset

| Dataset | Underlying source | License | Distributed via |
|---|---|---|---|
| **AMBROSIA** | Saparina & Lapata (Edinburgh) | CC BY 4.0, **authors request no re-hosting** | bring-your-own → ambrosia-benchmark.github.io |
| **WebQSP graph** | Freebase slice (WebQSP over Freebase) | Freebase = CC BY 2.5/… ; large | **Zenodo** |
| **npd** | Norwegian Offshore Directorate FactPages | NLOD 2.0 (open gov, attribution) | **Zenodo** |
| **cwd** | datadotworld/cwd-benchmark-data (ACME) | Apache 2.0 | **Zenodo** |
| **gtfs** | oeg-upm/gtfs-bench (Madrid) | Apache 2.0 | **Zenodo** |
| **lubm** | ontop/ontop-examples (LUBM) | Apache 2.0 | **Zenodo** |
| **cwe_secutable** | SecuTable (HF) + SEPSES CWE | CC BY 4.0 | **Zenodo** |
| **bsbm** | locally generated (bsbmtools) | synthetic, free | **Zenodo** |

Each dataset folder carries an `ATTRIBUTION.md` (source + license + citation) or, for the
restricted ones, a `DATA_ACCESS.md` with obtain-it-yourself instructions.

### Two ways to get every open dataset

The Zenodo files for the open datasets are **our PostgreSQL dumps** — the exact form the
R2RML mappings expect. They are not the raw original files; we converted them (e.g. MySQL→PG,
CSV→PG). Because the source licenses (Apache 2.0 / CC BY / NLOD) permit adaptation and
redistribution *with attribution*, we may host these dumps. For full transparency each
`ATTRIBUTION.md` also documents:
- the **original source** link, and
- **what conversion we applied** (and the script, when one is bundled),

so you can either (a) download our ready-to-load dump from Zenodo (one command), or
(b) rebuild it yourself from the original source. Both yield the same VKG.

## Our artefacts

Everything authored by this project (mappings, ontologies, NL questions, CHOICE-DSL GT,
scripts) is released under **CC BY 4.0** (see `LICENSE`). When you use a dataset's data,
you must **also** comply with that dataset's own license above and cite its source.

## Citing

Please cite this benchmark (see repo README) **and** the original source of each dataset
you use (citations in each `ATTRIBUTION.md`).
