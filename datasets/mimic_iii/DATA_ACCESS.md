# MIMIC-III data — restricted (PhysioNet credentialed), NOT bundled

The MIMIC-III Clinical Database is distributed under the **PhysioNet Credentialed Health
Data License 1.4**. Its redistribution is **prohibited** — the data is therefore **not**
included in this benchmark (neither in this repo nor on Zenodo).

To use this dataset you must obtain MIMIC-III yourself:

1. Create a PhysioNet account and complete the required CITI "Data or Specimens Only
   Research" training.
2. Sign the MIMIC-III Data Use Agreement.
3. Download MIMIC-III from https://physionet.org/content/mimiciii/ .
4. Build a local SQLite (or Postgres) and place it where the benchmark loader expects it
   (see `setup/README.md`); then the R2RML mapping + CHOICE-DSL ground truth here apply.

This folder ships only OUR derived artefacts (R2RML `mapping/`, `ontology/`) — never the
clinical data itself.

> Do not upload MIMIC-III (or anything derived that could reconstruct it) to any public
> location, API, or online service. This is a strict license requirement.
