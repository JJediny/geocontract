# Agent Review Response — Citizen-Permitting Plan v1

> **Source:** Review of PRs #5 (plan v1) and #6 (Phase B implementation).
> **Author:** External reviewer.
> **Status:** Addressed in `docs/plan-citizen-permitting-standard.md` v2.
> **Companion:** `docs/plan-citizen-permitting-standard.md` §0 *"What
> changed in this revision"* maps each reviewer gap to the v2
> resolution.

This file preserves the reviewer's verbatim text so future readers
can verify the v2 deltas trace back to specific findings.

---

## 1. Overall assessment (verbatim)

> The direction is promising, but this is not yet an implementation-
> ready standard. It is currently a **schema prototype plus an
> aspirational blockchain/harvester design**. I would not proceed to
> Phase C or a real municipal pilot until the data model, authority
> model, privacy posture, and validation strategy are tightened.

## 2. Highest-priority gaps (verbatim, condensed)

### 2.1 No single canonical `ProposedAction` representation

> The artifacts currently describe different shapes:
> - `templates/proposed-action.template.schema.json` uses nested objects
> - `examples/groton-rhine-001.example.data.json` follows that nested shape
> - `contracts/groton-rhine-001.datacontract.yaml` flattens those fields
> - The shim refers to `#/$defs/ProposedAction`, but the JSON Schema does
>   not define `ProposedAction` under `$defs`; it is inline under
>   `properties.proposedAction`.

**v2 resolution:** §3 *Canonical model and governance* defines one
nested JSON model + explicit ODCS-flatten + GraphQL-projection mappings,
all unit-tested (§7).

### 2.2 Anchoring is being called approval

> The plan's `AnchorRegistry.submit(...)` appears to record that a
> document was submitted or anchored. That is not the same as
> municipal approval.
>
> There are at least four distinct events:
> 1. A proposal was authored.
> 2. A proposal was submitted/anchored.
> 3. A municipality reviewed and approved or rejected it.
> 4. A later revision superseded or amended it.
>
> These must not be represented by one `approvalCode` and one
> mutable `status`.

**v2 resolution:** §3.4 state machine separates
`contentHash` / `submissionId` / `municipalDecision` /
`decisionIssuer` / `supersedes` / `revokedAt`. `approvalCode` is
deleted.

### 2.3 The signature and identity model is underspecified

> The plan says the citizen signs `sha256(canonical_yaml_bytes)`
> but the signature is stored inside the document being hashed.
> The plan needs to specify whether the signature field is excluded
> from the signed payload.
>
> The current model also lacks: signature algorithm, public key or
> DID, key identifier, issuer, signed digest, domain/audience,
> nonce or replay protection, VC issuer and credential type,
> credential validity interval, revocation/status mechanism,
> binding between the VC subject and wallet address.
> `residencyProofUri` is optional, and the schema accepts arbitrary
> strings for both the wallet address and signature.

**v2 resolution:** §5.7 detached proof envelope with
canonicalisation rules, algorithm pinning, replay protection, test
vectors. Walletless path supported.

### 2.4 The privacy model conflicts with public, permanent storage

> The implementation classifies identity-related fields as public
> while also proposing GitHub/IPFS publication and permanent
> retention.
>
> A wallet address may be pseudonymous in isolation but becomes
> personal data when linked to residency and property activity.

**v2 resolution:** §5.8 public vs restricted split with default-deny
access class. Permanent retention only for the public projection's
audit-relevant subset. The permanent-retention policy for restricted
projection is removed.

### 2.5 Token issuance should not be in the initial core model

> Q2 remains unresolved, yet Phase B introduces `raiseTarget`,
> `tokenSymbol`, `acceptChainIds`, `tokenAddress`, Base chain id
> `8453`, and ERC-20/SUI language.

**v2 resolution:** Token issuance removed from core (§3, §6, §10).
Moved to §13.1 *Out-of-core experimental / future-only*. The core
path is no-token.

### 2.6 The activity ontology is not implemented

> The current schema only validates that `activityCode` is a string.
> Any value such as `not-ontology` can pass the JSON Schema.

**v2 resolution:** §4.3 hand-curated `ActivityConcept` catalog v1.0
committed to `ontology/activity-concept-catalog.v1.0.json`. The
validator enforces membership, not just regex.

### 2.7 Parcel and geometry references are too weak for permitting

> The current parcel fields are strings. Geometry can be GeoJSON,
> WKT, or H3 with no format discriminator, CRS, source, timestamp,
> or authoritative parcel authority.

**v2 resolution:** §5.9 typed parcel reference with jurisdiction,
parcel authority, CRS, snapshot hash, ownership-status enum.
Cross-check that parcel id, address, geometry agree.

### 2.8 The generated GraphQL needs a composition contract

> `Parcel`, `FundingGoal`, and `CitizenClaim` are generated with
> `implements Node`, but they do not have an `id` field.

**v2 resolution:** §3.5 entity-vs-value-object choice per type.
Value objects do not implement `Node`; only `Proposal` does.
Generated GraphQL is parse + composition tested (§7.2).

## 3. Validation findings (verbatim, condensed)

> The existing test suite does not include the new citizen contract
> and shim in its parametrized lists. The shell glob in `mise run
> validate-odcs` catches them, but the Python regression tests do
> not. The new `examples/groton-rhine-001.example.data.json` is
> also not validated against `templates/proposed-action.template.schema.json`.

**v2 resolution:** §7.2 lists the new tests added to the suite.
Including JSON-example-vs-JSON-Schema, ontology membership,
detached-proof envelope fields, CRS validation, address-geometry
cross-check, public-vs-restricted projection, JSON-Schema path
cross-check vs shim paths, nested-JSON ↔ flattened-ODCS round-trip,
canonicalisation test vectors, GraphQL parse, federation
composition, generated-GraphQL reproducibility, anchor-receipt
lifecycle invariants.

## 4. Recommended revised sequence (verbatim, condensed)

> ### Phase 0 — Reframe and freeze scope
> Before further implementation:
> - Treat the current work as an experimental schema prototype.
> - Remove token issuance from the core path.
> - Decide whether the blockchain is actually necessary.
> - Add a conventional alternative: municipal registry plus signed
>   transparency log.
> - Clean up the plan status, duplicated §12, and truncated bullet.
>
> ### Phase 1 — Canonical model and governance
> ### Phase 2 — Schema projections
> ### Phase 3 — Ontology
> ### Phase 4 — Offline validation and local harvester
> ### Phase 5 — Anchor registry
> ### Phase 6 — Pilot

**v2 resolution:** §8 *Revised phasing — Phase 0..6* adopts this
sequence.

## 5. Bottom line (verbatim)

> I would support continuing the work, but I would request changes
> before merging Phase B as a standard:
>
> 1. Resolve the canonical-shape mismatch.
> 2. Separate anchoring from municipal approval.
> 3. Define detached signatures and canonicalization.
> 4. Redesign public/private identity handling.
> 5. Remove or isolate token fields.
> 6. Add a real versioned ontology artifact.
> 7. Fix GraphQL entity/value-object annotations.
> 8. Expand tests to validate the new artifacts semantically.
> 9. Correct the plan's stale, duplicated, and incomplete sections.

**v2 resolution:** §0 maps each numbered item to its v2 section.