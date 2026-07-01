# cwd (ACME Insurance) — attribution & license

- **Source:** [datadotworld/cwd-benchmark-data](https://github.com/datadotworld/cwd-benchmark-data)
  (`ACME_Insurance/`).
- **License:** **Apache License 2.0** — redistribution allowed with attribution + NOTICE.
- Redistributable on Zenodo (keep the Apache LICENSE + NOTICE alongside).

## Rebuild from the original source (optional)

- **Original data:** https://github.com/datadotworld/cwd-benchmark-data (`ACME_Insurance/`,
  Apache 2.0) — ships CSV + a DDL (`ACME_small.ddl`).
- **What we did:** loaded the CSVs into PostgreSQL via `data/csv_to_pg.py`, producing
  `data/cwd_postgres.sql` (the form the R2RML mapping expects).
- **Convenience:** the ready-to-load `cwd_data.zip` on Zenodo is exactly this dump.
