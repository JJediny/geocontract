# DataCite 4.3 validation — vendored schema and utility choices (issue #21)

Status: implemented on `feature/datacite-43-validation`.

## Vendored schema

`external/datacite/datacite_4.3_schema.json` is a pinned snapshot of
[`datacite/schema` @ `aa5db56`](https://github.com/datacite/schema/blob/aa5db56897b6ed255e6f2c5d14cfdcbff165567e/source/json/kernel-4.3/datacite_4.3_schema.json)
(file last touched 2020-05-08). The schema is self-contained draft-07:
all definitions live in the file, `additionalProperties: false`, and the
required top-level keys are `identifiers`, `creators`, `titles`,
`publisher`, `publicationYear`, `types`, `schemaVersion`.

Same rule as `external/dcat-us-catalog.json`: the upstream schema is the
source of truth. Update it only by replacing the snapshot with a newer
upstream release and re-recording the commit sha here.

**Licensing note.** The `datacite/schema` repository carries no LICENSE
file. The schema is pinned with full attribution to be helpful; at the
same time this repo is CC0-1.0 and the portolan norms require a recorded
human decision before vendoring code under another license or claiming a
license the source does not declare. Treat this file like other vendored
third-party artifacts: attribution here, and open a licensing question
with DataCite if the registry requires formal clearance.

## Reusable OSS utilities evaluated

| Tool | What it gives us | Chosen? |
| --- | --- | --- |
| [`datacite/schema`](https://github.com/datacite/schema) | The official JSON Schema (4.3 and later), self-contained, no extra deps | Yes — vendored, used by the validator |
| [`inveniosoftware/datacite`](https://github.com/inveniosoftware/datacite) (PyPI `datacite`, 1.4.1, MIT) | REST + MDS API wrapper (DOI minting), JSON↔XML generation against the DataCite XSD | Not needed yet; the only identified dependency need is minting via the REST API |
| [Invenio RDM](https://github.com/inveniosoftware/invenio-app-rdm) via docker-compose | Full local repository stack: record ingest validates against the community's metadata model end to end, not just the JSON Schema | Documented as an optional harness; needs Docker and is not wired into CI |
| DataCite REST API (`api.datacite.org`) | Harvest published remote records for round-trip checks | Harness only; any plain `httpx` call reaches it |

The validation path stays dependency-free: `jsonschema` (already a hard
dependency) plus the vendored schema. Minting or a Docker ingest harness
can adopt the `datacite` package or Invenio RDM later without touching
the validator.

## Issue #21 alignment

`fundingReferences` is emitted only when a contract carries funding
facts; no synthetic funders. The on-chain payment receipt schema in the
issue does not enter this repo: DataCite keeps award references
(`awardUri`/`awardNumber`) and on-chain evidence belongs in a separate
documented artifact (OpenFundingChain) reachable through
`relatedIdentifiers`. See the source-snapshot note in
`src/geocontract_tools/build_datacite.py`.
