# NEPA Categorical Exclusions (CATEX) Catalogue

The federal Categorical Exclusion catalogue, 2,105 records across 78
agency units. A CATEX is a class of action that normally needs no
further NEPA review because it has no significant effect on the
environment, individually or cumulatively.

This collection publishes the data contract that governs the catalogue.
The contract is the asset. No bulk data asset ships yet, so the
`table:columns` list describes the contract's `Exclusion` entity rather
than a queryable table. When a Parquet conversion of the catalogue
lands, those columns describe it unchanged.

## Provenance

The Permitting Innovation Center produces the catalogue at
<https://ce.permitting.innovation.gov/>. geocontract hosts this copy and
did not produce the data, so this collection is a mirror. The raw
upstream payload is a single 4 MB JSON file with no per-record URL, so
consumers filter client-side or through the registered mesh-gateway
endpoint.

## License

CC0-1.0. See <https://spdx.org/licenses/CC0-1.0.html>. United States
government works are public domain by statute; CC0-1.0 is recorded here
as the machine-readable equivalent so the catalog carries a valid SPDX
identifier.

## Reading the catalogue

Query by agency unit to find the exclusions one agency relies on, or by
CFR citation to trace an exclusion back to its rule. Each record carries
the documented context and any extraordinary-circumstances clause that
limits it. Read the clause before treating an exclusion as applicable.
