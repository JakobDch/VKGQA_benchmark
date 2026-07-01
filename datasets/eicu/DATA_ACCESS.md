# eICU data — restricted (PhysioNet credentialed), NOT bundled

The eICU Collaborative Research Database is distributed under the **PhysioNet
Credentialed Health Data License**. Its redistribution is **prohibited** — the data
is therefore **not** included in this benchmark (neither in this repo nor on Zenodo).

To use this dataset you must obtain eICU yourself:

1. Create a PhysioNet account and complete the required CITI "Data or Specimens Only
   Research" training.
2. Sign the eICU-CRD Data Use Agreement.
3. Download eICU from https://physionet.org/content/eicu-crd/ .
4. Build a local SQLite (or Postgres) and place it where the benchmark loader expects it
   (see `setup/README.md`); then the R2RML mapping + CHOICE-DSL ground truth here apply.

This folder ships only OUR derived artefacts (R2RML `mapping/`, `ontology/`) — never the
clinical data itself.

> Do not upload eICU (or anything derived that could reconstruct it) to any public
> location, API, or online service. This is a strict license requirement.
