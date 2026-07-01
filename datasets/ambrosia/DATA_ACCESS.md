# AMBROSIA source data — NOT redistributed here

The AMBROSIA databases (SQLite) are NOT included in this benchmark folder.
The AMBROSIA authors (Saparina & Lapata, Edinburgh) explicitly ask that the data
NOT be re-uploaded/redistributed (anti-LLM-training). Obtain it directly:

- Project page: https://ambrosia-benchmark.github.io
- Paper: https://arxiv.org/abs/2406.19073
- License: CC BY 4.0

This folder provides only OUR derived artefacts: the per-DB R2RML `mappings/` and
per-domain `ontology/` that turn the AMBROSIA DBs into a VKG, plus the CHOICE-DSL
ground truth under `queries/`. Point the mappings at your local AMBROSIA SQLite.
