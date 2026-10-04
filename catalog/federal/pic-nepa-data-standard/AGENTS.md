# Agent Guidance, PIC NEPA Data Standard v1.2

The `contract` asset is the ODCS v3.1.0 YAML for all 13 entities of the
PIC NEPA Data Standard. Read it before modeling anything against the
standard.

`table:columns` below describes the `Project` entity only, because one
collection cannot carry 13 column sets. The other 12 entities are in the
contract's `schema[]` list. `GisData` and `GisDataElement` are the two
that carry spatial payload; a geospatial collection built from them
would be a separate collection with its own geometry and bbox.

## Quirks

- The standard prescribes no wire format. Do not assume JSON. The
  contract's `servers[]` lists both a local JSON sample set and a
  Postgres deployment.
- Top-level container keys use the standard's spelling.
  `processe_instances` is not a typo to correct; it is the key.
- Provenance properties travel on every record: `data_record_version`,
  `data_source_agency`, `data_source_system`, `last_updated`, and
  `record_owner`. The contract's `customProperties` lists them under
  `pic-standards.v1.2ProvenanceProperties`. Preserve them through any
  transform.
- `Project` is the entity the other 12 reference. Joining without it
  loses the review context that gives a document or comment meaning.
