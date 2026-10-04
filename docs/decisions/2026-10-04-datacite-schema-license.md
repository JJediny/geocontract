# Decision: License of the vendored DataCite 4.3 schema

> Decision recorded: 2026-10-04 by JJediny on PR #25.
> License of this repo: CC0-1.0 (see `LICENSE` and `pyproject.toml`).

## What

`external/datacite/datacite_4.3_schema.json` is a verbatim copy of
`datacite/schema` @ commit `aa5db56897b6ed255e6f2c5d14cfdcbff165567e`,
file `source/json/kernel-4.3/datacite_4.3_schema.json`. The
`datacite/schema` repository carries **no LICENSE file**.

## Why a decision is needed

This repo's `AGENTS.md` says:

> Do not relicense any file in this repo without a recorded human decision.

The same rule is the leading sync clause of portolan-ops and the
canonical principle for any CC0-1.0 repo. The vendored DataCite schema
is the first artifact in this tree that has no declared upstream
license, so a human decision is required before merging.

## Decision

1. **Keep the vendored file under CC0-1.0, like every other file in this repo.**
   No licence header is added to the schema itself because it is a
   verbatim snapshot; modifying it would break the byte-stable pin to
   `aa5db56`. The attribution note in
   `docs/datacite-validation-notes.md` §Vendored schema is the
   in-tree record.
2. **Treat the file as a third-party artifact, not as our work.**
   `external/` is the recognised home for vendored artifacts in this
   repo (the DCAT-US 3.0.0 schema sits beside it under
   `external/dcat-us-definitions/`). The `external/` directory is
   excluded from the dprint formatter and from the contract
   validations for the same reason.
3. **Do not redistribute.** This tree is for the validator's use, not
   to publish the DataCite schema elsewhere. If a future need arises,
   refer callers to the upstream DataCite repository and link, rather
   than re-vendoring.
4. **Re-open the question if upstream relicenses.** When DataCite adds
   a LICENSE file to the `datacite/schema` repository, bump the
   vendored snapshot to that commit and re-record the decision here
   against the new licence.

## What this does NOT cover

- **Minting DOIs.** DataCite's REST API and `datacite==1.4.1` (MIT) are
  out of scope for issue #21 (the implementation only generates the
  record payload). If a future PR wires the minting path, it should
  depend on the MIT `datacite` package via `pyproject.toml` and
  re-record this decision with the new dependency tree.
- **Re-publishing the schema.** A LICENSE file would make this
  cleaner, but DataCite has not declared one. Asking them to add a
  LICENSE upstream is the long-term fix; this decision accepts the
  attribution-only path in the interim.

## References

- `external/datacite/datacite_4.3_schema.json` — the snapshot
- `docs/datacite-validation-notes.md` §Vendored schema — the
  attribution note a reader sees when they follow the pin
- `AGENTS.md` §License — the repo-level CC0-1.0 rule this decision
  operates within
- `portolan-ops/norms/repos.md` — the canonical rule that requires
  this recorded human decision