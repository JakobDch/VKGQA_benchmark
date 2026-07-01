# GTFS — attribution & license

- **Source:** [oeg-upm/gtfs-bench](https://github.com/oeg-upm/gtfs-bench) (Madrid metro GTFS).
- **License:** **Apache License 2.0** — redistribution allowed with attribution.
- **Vocabulary:** official GTFS terms http://vocab.gtfs.org/terms# (repaired for OWL2QL).
- Redistributable on Zenodo.

## Rebuild from the original source (optional)

- **Original data:** https://github.com/oeg-upm/gtfs-bench (Apache 2.0) — ships a MySQL dump.
- **What we did:** converted the MySQL dump to PostgreSQL via `data/mysql2pg.py`, producing
  `data/gtfs_postgres.sql` (the form the R2RML mapping expects).
- **Convenience:** the ready-to-load `gtfs_data.zip` on Zenodo is exactly this dump.
