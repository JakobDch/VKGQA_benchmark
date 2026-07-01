# BSBM — attribution & license

- **Source:** data generated locally with the official **bsbmtools** generator
  (Berlin SPARQL Benchmark, bsbmtools-0.2). The rows are synthetic generator output.
- **Vocabulary:** BSBM `bsbm:` vocabulary
  (http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/).
- **License:** synthetic data produced by this project; freely redistributable.
  BSBM tools/spec: Bizer & Schultz, FU Berlin.
- Redistributable on Zenodo.

## Rebuild from the original source (optional)

- **Generator:** the official bsbmtools (Berlin SPARQL Benchmark), bsbmtools-0.2
  (http://wbsg.informatik.uni-mannheim.de/bizer/berlinsparqlbenchmark/).
- **What we did:** ran bsbmtools to generate the relational rows and loaded them into
  PostgreSQL, producing `data/bsbm.sql`. Because it is synthetic generator output, our
  dump is freely redistributable.
- **Convenience:** the ready-to-load `bsbm_data.zip` on Zenodo is exactly this dump.
