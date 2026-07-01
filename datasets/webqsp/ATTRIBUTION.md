# WebQSP / Freebase — attribution & license

- **Questions:** WebQuestionsSP (WebQSP), Microsoft Research — real Google-Suggest user
  questions. https://www.microsoft.com/en-us/download/details.aspx?id=52763
- **Data:** a domain-based slice of **Freebase** (668M triples), served two ways.
  Freebase RDF dump was released under CC BY 2.5 / CC BY.
- **Ambiguity types:** after AMBROSIA (Saparina & Lapata, NeurIPS 2024).

## Two forms (both on Zenodo, fetched by setup/download_data.sh)

| File | Use |
|---|---|
| `webqsp_vkg_postgres.dump` | the **VKG**: `pg_restore` into PostgreSQL (13084 tables), query virtually via Ontop with `mappings/webqsp_big.r2rml.ttl`. This is the primary VKG form, consistent with the other datasets. |
| `webqsp_vkg_graph.nt.gz`   | the **prebuilt RDF graph** (668M triples): load into a triplestore (Virtuoso) — a convenience so you don't have to materialize, and the native-KG comparison partner. |

`start_vkgqa.sh webqsp` uses whichever is present (VKG dump preferred);
`webqsp-vkg` / `webqsp-rdf` force one mode.

## Note on the ontology

Freebase has no OWL T-Box file; the schema is defined by the R2RML mapping (Freebase
`domain.type.property` naming). See `ontology/NOTE.md`.
