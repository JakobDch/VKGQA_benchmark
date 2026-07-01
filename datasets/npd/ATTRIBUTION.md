# NPD — attribution & license

- **Source:** Norwegian Offshore Directorate (Sodir/NPD) FactPages, via the
  [ontop/npd-benchmark](https://github.com/ontop/npd-benchmark) modelling.
- **Data license:** Norwegian Licence for Open Government Data (**NLOD 2.0**) — free to
  use/redistribute **with attribution**. https://data.norge.no/nlod/en/2.0
- **Attribution:** "Contains data from the Norwegian Offshore Directorate (Sodir)."
- Redistributable on Zenodo. Third-party rights may apply to some report/log content.

## Rebuild from the original source (optional)

You do not have to use our Zenodo dump — you can rebuild from the original data:
- **Original data:** NPD/Sodir FactPages CSV/dumps, as modelled by
  https://github.com/ontop/npd-benchmark (Apache 2.0).
- **What we did:** loaded the NPD tables into PostgreSQL, producing `data/npd.psql`
  (the form the R2RML mapping in `../mapping/` expects).
- **Convenience:** the ready-to-load `npd_data.zip` on Zenodo is exactly this dump.
