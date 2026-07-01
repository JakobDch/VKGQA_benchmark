# CWE / SecuTable — attribution & license

- **Source:** SecuTable (SemTab 2025), HuggingFace
  [jiofidelus/SecuTable](https://huggingface.co/datasets/jiofidelus/SecuTable);
  CWE T-Box from SEPSES (https://sepses.ifs.tuwien.ac.at/).
- **License:** **CC BY 4.0** (SecuTable) — redistribution allowed with attribution.
  Underlying CWE is CC0/CC BY.
- Redistributable on Zenodo with attribution.

## Rebuild from the original source (optional)

- **Original data:** https://huggingface.co/datasets/jiofidelus/SecuTable (CC BY 4.0);
  CWE T-Box from SEPSES https://sepses.ifs.tuwien.ac.at/ .
- **What we did:** derived the R2RML from the SecuTable CTA/CPA annotations and loaded the
  tables into PostgreSQL, producing `data/cwe_secutable.sql`.
- **Convenience:** the ready-to-load `cwe_secutable_data.zip` on Zenodo is exactly this dump.
