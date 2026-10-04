# Agent Guidance, NEPA Categorical Exclusions (CATEX) Catalogue

The `contract` asset is the ODCS v3.1.0 YAML that governs this dataset.
Read it before querying. It names the two entities, `ExclusionsVersion`
and `Exclusion`, and the quality rules each field carries.

`table:columns` below describes the `Exclusion` entity from that
contract. This collection ships no Parquet asset yet, so there is no
table to query in place. The columns are the contract's schema, and
they will describe the data asset unchanged once one is published.

## Quirks

- The upstream is one 4 MB JSON payload with no per-record URL. Fetch it
  whole and filter locally, or use the mesh-gateway endpoint registered
  in `endpoints-config.yaml`.
- Agency units are finer than agencies. 78 units publish into one
  catalogue, so grouping by agency name alone merges records that
  different units authored.
- Refresh is ad hoc per contributing agency. The `updated` stamp on this
  collection is the last sync, not an upstream publication date.
- An extraordinary-circumstances clause narrows the exclusion it
  attaches to. Treat the clause as part of the exclusion, not as a
  footnote.
