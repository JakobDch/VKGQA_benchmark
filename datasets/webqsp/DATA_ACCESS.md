# WebQSP / Freebase data — external (not bundled)

The underlying data is the full Freebase KG (~3.12B triples) and the large
domain-based VKG (~668M triples, 13084 Postgres tables). These are far too large
to bundle and live on the project server (Postgres `freebase_vkg_big` + Ontop
endpoint; a native-KG Virtuoso backup is kept offline).

This folder provides the R2RML `mappings/` that define the structured VKG.
- WebQSP questions: https://www.microsoft.com/en-us/download/details.aspx?id=52763
- Freebase dump: standard public Freebase RDF dump.
Rebuild the VKG from the mapping against a Freebase-loaded Postgres, or request
access to the prebuilt endpoint.
