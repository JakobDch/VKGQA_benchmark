#!/usr/bin/env python3
"""Align the cwd insurance TBox with the locally-loaded data so Ontop boots the VKG.

The cwd data ships as CSV (all values are text) and is loaded into Postgres with every
column typed `text`. The insurance ontology declares 6 date properties with
`rdfs:range xsd:dateTime`:
  claimCloseDate, claimOpenDate, policyCoverageEffectiveDate,
  policyCoverageExpirationDate, policyEffectiveDate, policyExpirationDate
Ontop reads the underlying text columns as xsd:string and rejects the dateTime range
(MappingOntologyMismatchException). Since the source representation of these values is a
plain string (CSV) and this dataset is federated noise (no query targets it), we relax the
6 ranges to xsd:string — the values are preserved verbatim. Idempotent; edits insurance.ttl
in place.
"""
import pathlib, re

TTL = pathlib.Path(__file__).with_name("insurance.ttl")
text = TTL.read_text(encoding="utf-8")
new, n = re.subn(r"rdfs:range\s+xsd:dateTime",
                 "rdfs:range xsd:string", text)
TTL.write_text(new, encoding="utf-8")
print(f"relaxed {n} xsd:dateTime ranges to xsd:string (CSV string source, noise dataset)")
