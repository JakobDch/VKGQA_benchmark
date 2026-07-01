#!/usr/bin/env python3
"""Adapt the cwd data.world R2RML (cwd.r2rml.ttl) to the local Postgres tables.

The shipped mapping names tables as 3-part data.world identifiers, e.g.
  rr:tableName "myinsurancecompany.omg-pc-database.claim"
Our Postgres tables are bare lower-case (`claim`). Strip the
`myinsurancecompany.omg-pc-database.` prefix so rr:tableName resolves locally. The
`rr:sqlQuery` triples maps already use bare lower-case names, so they need no change.
Idempotent; edits cwd.r2rml.ttl in place.
"""
import pathlib, re

TTL = pathlib.Path(__file__).with_name("cwd.r2rml.ttl")
text = TTL.read_text(encoding="utf-8")

# strip the data.world db prefix inside rr:tableName "..."
new, n = re.subn(r'(rr:tableName\s+")myinsurancecompany\.omg-pc-database\.', r"\1", text)
TTL.write_text(new, encoding="utf-8")
print(f"stripped data.world prefix from {n} rr:tableName values")
