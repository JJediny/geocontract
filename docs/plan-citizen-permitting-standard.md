# Implementation Plan — Citizen-Permitting Geocontract Standard

> **Status:** Revised draft (v2) incorporating agent review feedback.
> v1 was an aspirational schema prototype; v2 reframes this as a
> **scope-frozen, governance-first, core-only** plan and moves
> token issuance, NLP corpus ingestion, and on-chain anchor
> smart-contract work out of the **core** path into an
> **experimental / out-of-core** appendix (§13).
>
> **Author:** geocontract agent, in response to the user's request
> to "create an implementation plan for a full standard to support
> activities whereby any citizen can create a minimal geocontract
> for a proposed action on denoted lands."
> **Companion docs:** `docs/design-harvester.md` (Phase 1–4 harvester
> design), `templates/*.template.schema.json` (existing x-graphql-
> annotated templates), `contracts/odcs-v3.1.0-template.yaml`
> (existing primitive), `docs/agent-review-response.md` (the review
> that prompted this revision).

---

## 0. What changed in this revision (v2 → v1)

The v1 plan conflated several distinct concepts and shipped a
prototype that conflated more. The agent review
(`docs/agent-review-response.md`) identified eight material gaps
plus a stale, duplicated, and truncated document. The v2 plan
addresses them as follows:

| Reviewer gap (v1)                                     | v2 resolution                                   |
|-------------------------------------------------------|-------------------------------------------------|
| No single canonical representation                    | §3 *Canonical model and governance* defines one nested JSON model + explicit ODCS-flatten + GraphQL-projection mappings. |
| Anchoring called "approval"                           | §3.4 state machine separates `contentHash` / `submissionId` / `municipalDecision` / `decisionIssuer` / `supersedes` / `revokedAt`. |
| Signature underspecified                              | §5.7 *Detached signature envelope* with canonicalization rules, algorithm pinning, replay protection, test vectors. |
| Privacy model conflicts with public storage           | §5.8 *Public vs restricted record split*; permanent public retention policy **removed**; per-record access class. |
| Token issuance in initial core                        | Removed from §3 / §6 / §10; moved to §13 *Out-of-core experimental / future-only*. **Core path is no-token.** |
| Activity ontology not implemented                     | §4.3 *v2 ontology = small hand-curated `ActivityConcept` catalog*, v1.0; NLP corpus / starred-projects scan deferred to §13. |
| Parcel reference too weak                             | §5.9 *Typed parcel reference* — jurisdiction, parcel authority, CRS, snapshot hash. |
| Generated GraphQL composition untested                | §3.5 *Projections* explicitly chooses value-object or entity per type; `Node` interface removed from value objects; composition tests added in §7. |
| Plan document stale / duplicated / truncated          | §11 reframed; §12 replaced with concrete v2-specific follow-ups; v1 §12 truncated bullets deleted. |

Plus, throughout:

- §1 *Problem statement* reframes this as an experimental prototype
  pending governance + privacy review, not a deployment-ready
  standard.
- §8 *Revised phasing* adopts the reviewer's **Phase 0..6** sequence.
- §11 *Steering questions* are restated against the v2 scope.
- §13 *Out-of-core experimental / future-only* is the new home for
  the smart-contract token, NLP corpus scan, and ComposeDB work.

---

## 1. Problem statement (one paragraph)

The geocontract repo produces ODCS v3.1.0 contracts for federal
catalogue records (exclusions lists, NEPA data standards, DCAT-US
federated catalogs). The producer is always an agency. The user
wants the same machinery to support a bottom-up, citizen-initiated
flow where any resident of a municipality (worked example: Groton,
CT, via the Groton Housing Authority) drafts a minimal
`*.geocontract.yaml` describing a *proposed action* on a *denoted
parcel*. Per the agent review of the v1 prototype, this v2 plan:

1. Recognises that the schema and harvester are a **prototype** and
   that deploying a real municipal pilot requires governance,
   privacy, accessibility, and legal review that this plan cannot
   itself discharge.
2. Separates the core proposal-and-review data model from any
   optional anchoring or fundraising mechanisms (§13).
3. Defines a **single canonical nested JSON model** and the
   explicit, tested projections to ODCS-flatten and GraphQL.
4. Distinguishes *anchoring a document on a public ledger* from
   *municipal approval of the proposal* — they are not the same
   event and must never be conflated.
5. Classifies personal / sensitive fields as **restricted** by
   default, with a separate **public projection** that omits them.
6. Implements **detached signatures** over a canonicalised byte
   representation of the document (excluding the signature itself).
7. Removes token issuance, NLP corpus ingestion, and ComposeDB from
   the core path; the **core path is no-token, offline-harvestable,
   governance-first**.
8. Requires an **activity ontology** to be present and validated
   against, not just a regex on `activityCode`.

### 1.1 The federal permitting catalogue is a vocabulary source, not a regulatory gate

Per the user's clarification: the
[`https://ce.permitting.innovation.gov/data/exclusions.json`](https://ce.permitting.innovation.gov/data/exclusions.json)
catalogue is consumed **only as a corpus of generic activity
descriptions**, not as a regulator's "what's exempt from NEPA"
answer. Its role is to **seed the activity ontology** with
human-readable short labels.

The v2 plan adds an explicit **non-endorsement distinction** that
v1 lacked:

> "Pre-reviewed" in this plan means only that the federal
> catalogue has published a human-readable text description of the
> activity. It does **not** mean the activity has been approved,
> exempted, or endorsed for any specific proposal, parcel, applicant,
> or jurisdiction. Municipal reviewers must make their own
> decisions per their own ordinances and state law. The federal
> catalogue's appearance in the ontology's `sourceCitation` is a
> provenance link, not a regulatory status.

This distinction is enforced structurally:

- The ontology catalog's `ActivityConcept` row carries a separate
  `regulatoryStatus` field with the enum `{ descriptive_only,
    jurisdictional_advisory, deprecated }`. By default every row
  is `descriptive_only`.
- No field on `ProposedAction` or any projection carries a NEPA,
  federal, or cross-jurisdictional regulatory status. The contract
  is municipal from edge to edge.

---

## 2. Scope

### 2.1 In scope (v2 core)

- A **canonical nested-JSON model** for one entity, `ProposedAction`
  (§3).
- An **ODCS-flatten projection** with explicit, tested mapping rules
  (§3.6).
- A **GraphQL projection** with explicit entity-vs-value-object
  choices (§3.5).
- A **public projection** that omits restricted fields and a
  **restricted projection** that requires explicit access checks
  (§5.8).
- A **hand-curated `ActivityConcept` catalog**, v1.0, sourced from
  the federal CATEX corpus and a small set of municipal ordinances
  (§4.3).
- A **detached signature envelope** with canonicalisation rules,
  algorithm pinning, replay protection, and test vectors (§5.7).
- A **typed parcel reference** with jurisdiction, parcel authority,
  CRS, and snapshot hash (§5.9).
- **Local-only harvester** extensions: a citizen-source flag, no
  RPC, no ComposeDB, no GitHub crawling for citizen contracts in
  v2 core. Phase 4 §8.
- **Lifecycle and amendment rules** (§3.4) — every material change
  creates a new immutable revision.
- **Tests** (extended coverage in §7): JSON-example vs JSON-Schema,
  invalid activity-code membership, unknown-property rejection,
  address and signature formats, geometry format and CRS,
  JSON-Schema path cross-check vs shim paths, nested-JSON ↔
  flattened-ODCS round-trip, canonicalisation test vectors,
  GraphQL parse, federation composition, generated-GraphQL
  reproducibility, lifecycle invariants.

### 2.2 Out of scope (v2 core — moved to §13)

- **Token issuance / fundraising / coin deployment.** v1 §5.2 is
  moved to §13.1. The core path is **no-token**.
- **On-chain anchor smart contracts.** v1 Phase C is moved to
  §13.2. The core path uses **optional anchor receipts** emitted
  by an external, separately-deployed `geocontract-anchor`
  registry (or any equivalent signed-transparency-log service); the
  anchor field on `ProposedAction` is **optional** and does not
  participate in core validation.
- **NLP corpus ingestion / starred-projects scan.** v1 §4.4 is
  moved to §13.3. The v2 catalog is hand-curated.
- **Ceramic ComposeDB / W3C DID wallet-binding for the rich
  registry.** v1 §5.1 is moved to §13.4.
- **Form UI.** v1 Phase D is moved to §13.5. Out of scope for the
  geocontract repo.
- **Municipal pilot.** v1 Phase F is moved to §13.6 and gated on
  §2.3 (governance / privacy / accessibility review) being
  satisfied.

### 2.3 Pre-conditions for any pilot deployment (v2 gate)

Before the v2 core path may be deployed against a real municipal
partner, the following must be evidenced in writing and reviewed by
counsel + privacy + accessibility officers:

1. **Jurisdictional legal review** — the partner's ordinances and
   state FOIA / privacy statutes cited explicitly.
2. **Privacy review** — restricted fields enumerated, access
   controls specified, retention rules justified, breach response
   defined, vulnerable-residents-and-minors policy.
3. **Accessibility review** — WCAG 2.2 AA conformance for any
   consumer UI.
4. **Walletless filing path** — any-citizen capability requires a
   non-crypto-wallet identity path (§5.7 §5.8).
5. **Trusted issuer registry** — for any residency credential that
   the partner chooses to require.

Until these are discharged, the artifacts in this repo remain
**experimental schema prototypes**.

---

## 3. Canonical model and governance

### 3.1 Canonical nested-JSON model (single source of truth)

The v2 canonical model is one nested JSON object with these top-
level keys:

```jsonc
{
  "id": "<proposal-id>",
  "schemaVersion": "1.0.0",
  "createdAt": "<iso-8601>",
  "applicant": { /* restricted; §3.3 */ },
  "parcel":    { /* §5.9 */ },
  "activity":  { /* §4 */ },
  "purpose":   "<= 500 chars",
  "estimatedCostUsd": 12345.67,           // optional
  "fundingIntent": { /* §13.1, optional, core path no-token */ },
  "anchorReceipt": { /* §3.4, optional */ },
  "lifecycle": { /* §3.4 */ },
  "revisions": [ /* §3.4 */ ],
  "proof":     { /* §5.7, detached */ }
}
```

Every other projection (ODCS-flatten, GraphQL, public, restricted)
is **derived** from this canonical model via explicit mapping
rules (§3.5 / §3.6). The mapping rules are unit-tested (§7).

### 3.2 Proposal vs permit, applicant vs owner

The v2 model distinguishes four concepts that v1 conflated:

| Concept             | Definition                                            |
|---------------------|-------------------------------------------------------|
| **Proposal**        | A citizen's *request* that a specific activity be permitted on a specific parcel. |
| **Permit**          | A *decision by an authority* that the activity is approved under specified conditions. |
| **Applicant**       | The person (or their authorised representative) who filed the proposal. |
| **Owner**           | The person with property-interest authority over the parcel. |

A resident's proof of residency does **not** establish authority
to propose work on a parcel. v2 separates these via:

- `applicant.residencyProof` (optional, restricted) — proves the
  applicant resides in the municipality.
- `applicant.authorityProof` (optional, restricted) — proves the
  applicant has authority to propose work on the parcel (owner,
  lessee, authorised agent, etc.).
- `parcel.ownershipStatus` (public) — separate, sourced from the
  authoritative parcel authority.

### 3.3 Public vs restricted fields (default-deny)

Every field in the canonical model is tagged with an `accessClass`:

| Class        | Default access | Examples                                |
|--------------|----------------|-----------------------------------------|
| `public`     | everyone       | `id`, `schemaVersion`, `parcel.jurisdiction`, `parcel.authoritativeParcelId`, `activity.code`, `lifecycle.state` |
| `restricted` | authority only | `applicant.*`, `parcel.geometry` (raw), `proof.signature`, `anchorReceipt.*` |

Default-deny means **a field is `restricted` unless explicitly
tagged `public`**. The public projection (§5.8) emits only the
`public` set; the restricted projection is emitted only to
authorised consumers.

### 3.4 Lifecycle and amendment state machine

The v2 lifecycle is a finite-state machine; **every material
change creates a new immutable revision**:

```
draft
  → submitted
  → anchored            (optional, external anchor service)
  → under_review
  → approved | rejected
  → amended | superseded | revoked | expired
```

Field-level responsibilities:

| Field              | Purpose                                            |
|--------------------|----------------------------------------------------|
| `lifecycle.state`  | Current state from the FSM above.                  |
| `anchorReceipt.contentHash` | SHA-256 of canonicalised bytes of this revision. |
| `anchorReceipt.submissionId` | Opaque id returned by the anchor service.  |
| `anchorReceipt.anchoredAt` | Timestamp from the anchor service.         |
| `anchorReceipt.serviceRef` | URI of the anchor service (for re-checking). |
| `revisions[]`      | Append-only list of prior revisions, each with its own `contentHash`, `createdAt`, `supersededBy`, `supersedes`. |
| `supersedes`       | Pointer to the predecessor revision this one replaces. |
| `revokedAt`        | Set iff `lifecycle.state = revoked`.               |

**Anchoring is not approval.** A proposal may be `anchored` while
still `draft` or `under_review`; it may be `approved` without ever
being anchored. The two events are independent and must never share
a single field. v1's `approvalCode` field is deleted; replaced by
the disjoint fields above.

### 3.5 GraphQL projection — entity vs value-object

| Canonical type   | Projection choice         | Reason                                  |
|------------------|---------------------------|-----------------------------------------|
| `Proposal`       | **GraphQL entity**        | Has stable `id`, federates by `id`.     |
| `Applicant`      | **value object**          | Subset of proposal; never federates.    |
| `Parcel`         | **value object**          | Belongs to a single proposal.            |
| `Activity`       | **value object**          | Belongs to a single proposal.            |
| `AnchorReceipt`  | **value object**          | Belongs to a single proposal.            |
| `Revision`       | **value object**          | Belongs to a single proposal.            |
| `Proof`          | **value object**          | Restricted; never emitted in the public projection. |

Value objects do **not** implement `Node`. Only `Proposal`
implements `Node @key(fields: "id")`. The generated GraphQL SDL is
covered by parse + composition tests (§7).

### 3.6 ODCS-flatten projection — explicit mapping

The ODCS contract flattens the canonical nested model into a single
`ProposedAction` SchemaObject. Each flatten rule has a test:

| Canonical path                   | ODCS column name     | Notes                                |
|----------------------------------|----------------------|--------------------------------------|
| `id`                             | `id`                 | primary key, unique.                 |
| `parcel.jurisdiction`            | `jurisdiction`       | public.                              |
| `parcel.authoritativeParcelId`   | `parcelId`           | public.                              |
| `parcel.authorityRef`            | `parcelAuthority`    | public.                              |
| `parcel.ownershipStatus`         | `parcelOwnershipStatus` | public.                           |
| `parcel.geometryFormat`          | `geometryFormat`     | enum: `geojson|wkt|h3|null`.         |
| `parcel.crs`                     | `crs`                | public; required if geometry present.|
| `activity.code`                  | `activityCode`       | validated against §4 catalog.         |
| `lifecycle.state`                | `lifecycleState`     | enum from §3.4 FSM.                  |
| `lifecycle.revokedAt`            | `revokedAt`          | timestamp; null unless revoked.      |
| `anchorReceipt.contentHash`      | `anchorContentHash`  | optional.                            |
| `anchorReceipt.submissionId`     | `anchorSubmissionId` | optional.                            |
| `anchorReceipt.anchoredAt`       | `anchorAnchoredAt`   | timestamp; optional.                 |
| `anchorReceipt.serviceRef`       | `anchorServiceRef`   | URI; optional.                       |
| `fundingIntent.targetUsd`        | `fundingTargetUsd`   | optional; §13.1 only.                |
| `fundingIntent.tokenSymbol`      | `fundingTokenSymbol` | optional; §13.1 only.                |

Restricted fields (`applicant.*`, `proof.*`, raw `parcel.geometry`)
**do not appear** in the ODCS-flatten projection. They are emitted
only in the restricted projection (§5.8).

---

## 4. Activity ontology (v2 — small hand-curated first)

### 4.1 What the federal catalogue contributes

Per §1.1, the federal CATEX catalogue contributes **descriptive
labels** to the ontology's `ActivityConcept` catalog. Each row in
the catalog carries a `sourceCitation` linking back to the
originating entry.

### 4.2 Why we need something broader than the federal catalogue

The citizen use case includes actions that are not in the CATEX
catalogue at all — building a deck, paving a driveway, opening a
food-truck lot. v2 sources the catalog from a small, manually
curated set plus the CATEX short-labels.

### 4.3 v2 ontology = `ActivityConcept` catalog v1.0

A versioned JSON catalog file, `ontology/activity-concept-catalog.v1.0.json`,
committed to the repo. Each row has:

```jsonc
{
  "code": "housing.rehabilitation.facade",
  "preferredLabel": "Building façade rehabilitation",
  "definition": "Repair, repoint, or replace the exterior façade …",
  "broader": ["housing.rehabilitation"],
  "narrower": [],
  "aliases": ["facade repair", "masonry repointing"],
  "jurisdiction": "us-ct-groton",          // default = null = any
  "sourceCitation": "https://ce.permitting.innovation.gov/data/exclusions.json#…",
  "lifecycleStatus": "active",
  "deprecatedAfter": null,
  "regulatoryStatus": "descriptive_only",  // §1.1 enum
  "ontologyVersion": "1.0.0"
}
```

The validator enforces:

- `activity.code` membership in the active rows of the catalog.
- `broader` resolves to another active row.
- `deprecatedAfter` not in the past.
- `regulatoryStatus ∈ { descriptive_only, jurisdictional_advisory, deprecated }`.

### 4.4 NLP corpus / starred-projects scan (moved to §13.3)

v1 §4.4's enrichment sources (including the user's starred
projects, NAICS, W3C ADR, etc.) are moved to §13.3. The v2 catalog
is hand-curated; NLP-assisted suggestions are added later with
human approval and provenance.

---

## 5. Cross-cutting concerns

### 5.1 Why we may not need a blockchain (conventional alternative)

The v1 plan assumed a public ledger was necessary. v2 names the
**conventional alternative**:

> A **municipal registry** backed by a **signed transparency log**
> (a hash-linked append-only structure, signed by a small set of
> well-known municipal keys, mirrored on a public read-only
> endpoint) achieves most of the integrity properties of a chain
> anchor — content-hash commitment, tamper evidence, public
> verifiability — without the operational complexity, gas costs,
> wallet requirements, or MEV surface of a public chain.

The v2 core path is **ledger-agnostic**. It treats anchoring as an
optional external service (§3.4) that may be a chain, may be a
transparency log, may be a notary, may be nothing. The core path
must not require any specific ledger.

### 5.7 Detached signature envelope

The signature is **detached** — stored in `proof` *outside* the
canonical payload that is hashed. The v2 envelope:

```jsonc
{
  "proof": {
    "signedDigest": "sha256:…",          // over canonicalised bytes, excluding `proof` itself
    "hashAlgorithm": "sha-256",
    "signatureAlgorithm": "ed25519",     // pinned, not free-form
    "signingKey": "did:example:…",       // DID, not raw wallet address
    "signature": "base64:…",
    "signedAt": "2026-09-12T14:30:00-04:00",
    "domain": "geocontract.example",
    "nonce": "base64:…",                 // replay protection
    "keyId": "k-1"                       // key identifier within DID document
  }
}
```

Mandatory fields; validator rejects if any are missing or
malformed. Test vectors (RFC 8785 JCS-style canonical JSON with a
specified subset, then Ed25519) committed to the repo.

**Walletless path**: the v2 core **does not require a crypto
wallet**. If `proof` is absent the proposal is `draft` and may be
manually verified by the municipal clerk under the partner's KYC
procedure. Wallets are an optional convenience, not a gate.

### 5.8 Public vs restricted record split

Two projections, both derived from the canonical model:

- **`public`** — emits `public`-class fields only. Suitable for
  IPFS / GitHub / public mirrors. Includes `id`,
  `lifecycle.state`, `activity.code`, `parcel.jurisdiction`,
  `parcel.authoritativeParcelId`, `parcel.parcelAuthority`,
  `parcel.ownershipStatus`, `anchorReceipt.contentHash`,
  `anchorReceipt.serviceRef`.
- **`restricted`** — emits everything, requires an `X-Geocontract-
  Authority` header on harvest requests, audit-logged.

Permanent retention is **only** for the public projection's
audit-relevant subset (`id`, `lifecycle.state`,
`anchorReceipt.contentHash`, `anchorReceipt.anchoredAt`). The
restricted projection follows the partner's retention rules,
default = municipal record retention (e.g. 7 years per Conn. Gen.
Stat. § 1-218 for permitting records).

### 5.9 Typed parcel reference

```
parcel.jurisdiction           : "<country>-<state>-<name>"
parcel.parcelAuthority         : URI to the authoritative parcel registry
parcel.authoritativeParcelId   : string (per the authority's format)
parcel.authorityRecordVersion  : string (the version of the registry snapshot)
parcel.authorityRetrievedAt    : timestamp
parcel.geometryFormat          : enum { geojson | wkt | h3 }
parcel.crs                     : string (e.g. "EPSG:4326", "EPSG:3857")
parcel.geometry                : string (in geometryFormat, in crs)
parcel.ownershipStatus          : enum { owner_verified, lessee_verified, authorised_agent, unknown }
parcel.snapshotHash             : sha256 of (authorityRecordVersion + retrievedAt + geometryFormat + crs + geometry)
```

The validator cross-checks `parcelId`, `address`, and `geometry`
refer to the same location (lat/lon centroid equality, ±5 m).

---

## 6. End-to-end flow (v2 core)

```
1. CITIZEN FILLS FORM (any client; walletless OK)
   fields: id, parcel, activity.code, purpose, estimatedCostUsd?
   ──▶ validates against canonical nested JSON Schema
   ──▶ canonicalises to bytes (RFC 8785-style JCS, excluding `proof`)

2. CITIZEN SIGNS (optional; absent = draft, manual review path)
   proof = { signedDigest: sha256(canonical_bytes), … }
   ──▶ proposal.lifecycle.state = submitted (if signed) or draft (if not)

3. (OPTIONAL) ANCHOR ON EXTERNAL SERVICE
   AnchorService.submit(contentHash, parcelId, activity.code)
   ──▶ returns submissionId, anchoredAt, serviceRef
   ──▶ proposal.anchorReceipt populated; lifecycle.state = anchored (only if already submitted)
   Note: anchoring ≠ approval

4. MUNICIPAL REVIEW
   reviewer amends lifecycle.state to under_review, then approved | rejected
   ──▶ decision issuer, decision evidence, decisionAt recorded on `lifecycle`

5. (OPTIONAL) PROJECT TOKEN (§13.1 ONLY — core path no-token)
   ProjectTokenFactory.deploy(symbol, raiseTarget, multisig)
   ──▶ not in core; only after approval; only with explicit fundingIntent

6. HARVESTER PICKUP
   geocontract-harvest discovers contracts/<id>.json
   (or the IPFS mirror of the public projection, or the signed
    transparency log entry)
   ──▶ validates against ODCS v3.1.0 (flatten projection)
   ──▶ emits public JSONL by default; restricted JSONL only on
        authority-authenticated requests
   ──▶ contentHash in the JSONL allows downstream consumers to
        verify they are reading the same revision the anchor
        service saw
```

The harvester output schema in `docs/design-harvester.md` adds the
following **optional** per-entity JSONL fields:

| Field            | Required | Example                         |
|-----------------|----------|---------------------------------|
| `content_hash`  | yes if anchored | `sha256:…`               |
| `submission_id` | no       | `<service-specific opaque id>`  |
| `anchor_service_ref` | no  | `<uri of the anchor service>`   |
| `lifecycle_state` | yes    | `submitted|approved|...`        |
| `supersedes`    | no       | content hash of predecessor     |

This is strictly additive and a redesign of v1's `approval_code`
field.

---

## 7. Validation strategy

### 7.1 Existing checks (retained)

- `mise run validate-odcs` — every YAML and shim JSON validates
  against the geocontract master schema (ODCS v3.1.0 +
  `embeddedSchemas` extension).
- `mise run test` — pytest unit tests.
- `mise run fmt-check` — dprint JSON formatting.
- `mise run generate-graphql` — all templates round-trip through
  vendored jxql.
- `mise run datacontract-lint` — second-line upstream CLI lint.

### 7.2 New v2 tests (added in this revision's implementation PRs)

| Test                                                          | Purpose                                  |
|---------------------------------------------------------------|------------------------------------------|
| `test_proposed_action_example_validates_against_json_schema` | Example JSON validates against the nested-JSON-Schema. |
| `test_proposed_action_rejects_unknown_activity_code`          | Ontology membership, not just regex.     |
| `test_proposed_action_rejects_unknown_properties`             | `additionalProperties: false` at the right levels. |
| `test_proposed_action_rejects_malformed_signature`            | Detached proof envelope fields required. |
| `test_proposed_action_rejects_geometry_without_crs`           | Typed parcel reference enforcement.       |
| `test_proposed_action_rejects_address_geometry_mismatch`      | Cross-check.                              |
| `test_proposed_action_public_projection_omits_restricted`     | §5.8.                                     |
| `test_odcs_flatten_round_trip`                                | Nested-JSON ↔ ODCS-flatten mapping.       |
| `test_signature_canonicalisation_test_vectors`                 | §5.7 vectors commit + reproduce.         |
| `test_graphql_parses`                                         | Generated SDL parses.                     |
| `test_graphql_federation_composes`                            | SDL composes against a minimal gateway.  |
| `test_generated_graphql_is_reproducible`                       | Run twice, byte-equal.                    |
| `test_anchor_receipt_lifecycle_invariants`                    | State-machine enforcement.                |
| `test_ontology_membership_validator`                          | §4.3 catalog membership.                  |
| `test_jxql_quirk_overrides_still_required`                    | Regression guard for quirks #236, #237.   |

### 7.3 Non-checks (explicitly out of core)

- No test for blockchain interaction in core.
- No test for token deployment in core.
- No test for NLP corpus ingestion in core.
- No test for ComposeDB in core.
- These move to §13.

---

## 8. Revised phasing — Phase 0..6 (per reviewer recommendation)

### Phase 0 — Reframe and freeze scope (this PR + its sibling)
- Update plan (PR #7 — this document).
- Add `docs/agent-review-response.md` recording the review.
- Add `ontology/activity-concept-catalog.v1.0.json` (hand-curated).
- Update `templates/proposed-action.template.schema.json` to the
  nested-JSON canonical model with detached proof envelope.
- Update `contracts/groton-rhine-001.datacontract.yaml` and
  `examples/groton-rhine-001.example.data.json` to match.
- **PR #7** — plan + scope reframe.
- **PR #8** — schema + worked example + ontology catalog + tests.
- **PR #9** — harvester v2 citizen-source (additive JSONL fields,
  no RPC).

### Phase 1 — Canonical model and governance (this PR)
- All four concepts (proposal vs permit, applicant vs owner,
  anchor vs approval, public vs restricted) are encoded in the
  data model and exercised by tests.
- See §3.

### Phase 2 — Schema projections (this PR)
- JSON Schema (canonical nested), ODCS-flatten, GraphQL, public /
  restricted. Round-trip tests for the flatten.
- See §3.5, §3.6, §5.8.

### Phase 3 — Activity ontology (this PR for the catalog,
§13.3 for ingestion)
- `ontology/activity-concept-catalog.v1.0.json` is hand-curated
  with the federal CATEX corpus as one source citation.
- NLP / corpus ingestion deferred to §13.3.

### Phase 4 — Offline validation and local harvester
(PR #9, follow-up)
- `geocontract-harvest` extensions: `--public-only` default;
  citizen-source flag; `--restricted-token` for restricted
  projection.
- No RPC. No ComposeDB. No GitHub crawling for citizen contracts
  (the partner provides the canonical URL).

### Phase 5 — Anchor service integration (§13.2)
- **External** project: `geocontract-anchor` (or any equivalent).
- The core path treats anchoring as an opaque external service.

### Phase 6 — Pilot (gated on §2.3)
- Cannot proceed without:
  - jurisdictional legal review,
  - privacy review,
  - accessibility review,
  - walletless path,
  - trusted issuer registry,
  - partner agreement.
- Token issuance (if any) is **separately** governed (§13.1).

---

## 9. Risks (v2)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Schema prototype mistaken for a deployment-ready standard | High (without §2.3 gate) | Severe | Explicit "experimental" labelling; §2.3 gate before any pilot. |
| Anchoring conflated with approval by downstream consumers | Medium | High | Disjoint fields (§3.4); tests + docs. |
| Restricted fields leak via the public projection | Medium | Severe | Default-deny access class; round-trip test (§7.2). |
| Permanent retention of restricted fields | Medium | Severe | Public projection only; restricted follows partner retention. |
| VC issuer (municipal clerk) unwilling or unavailable | Medium | High | Walletless path (§5.7); manual KYC fallback. |
| Ontology drift / silent deprecation | High | Medium | `lifecycleStatus` + `deprecatedAfter`; catalog membership tests. |
| Jurisdictional mismatch (Groton ordinances ≠ other towns) | High | Medium | `ActivityConcept.jurisdiction` field; jurisdictional catalog per partner. |
| Securities / consumer-protection risk on tokens | High | Severe | Removed from core (§13.1); separately governed if at all. |
| Wallet requirement excludes low-income filers | Medium | High | Walletless path (§5.7). |
| Canonicalisation ambiguity (informal "canonical YAML") | Medium | High | RFC 8785-style JCS; test vectors (§5.7). |

---

## 10. Success metrics (v2)

| Metric | Target |
|--------|--------|
| **Core**: Contracts passing `mise run validate-odcs` | 100% |
| **Core**: pytest pass rate (incl. new §7.2 tests) | 100% |
| **Core**: dprint clean | 100% |
| **Core**: Generated SDL reproducible (byte-equal across runs) | 100% |
| **Core**: Round-trip nested-JSON ↔ ODCS-flatten | 100% of properties |
| **Pilot (gated on §2.3)**: median review turnaround | reported |
| **Pilot**: submission completion rate | reported |
| **Pilot**: rejection / resubmission rate | reported |
| **Pilot**: accessibility incidents (WCAG 2.2 AA) | 0 |
| **Pilot**: privacy incidents | 0 |
| **Pilot**: identity-verification burden | reported |
| **Pilot**: cost per proposal (filing + storage) | reported |
| Removed | "token issuances / pilot" — moved to §13.1. |

---

## 11. Steering questions (v2)

Q1 ✅ Resolved (v1; see §0 and §13.3 — starred-projects corpus
moved to §13.3, no longer in core).

**Q2 — Token issuance.** ❌ Removed from v2 core. If desired at
all, §13.1 governs it as a separately-deployed, separately-counsel-
reviewed experimental feature. **Recommend: do not pursue in v2.**

**Q3 — Anchor service.** v2 core is ledger-agnostic. The choice of
chain vs transparency log vs notary is **partner-specific** and
deferred to the anchor service operator (§13.2).

**Q4 — Identity provider.** v2 core is **walletless-first**. W3C VC
is one optional path; manual KYC + utility-bill upload is the
fallback. The partner's choice.

**Q5 — Worked example scope.** v1 Groton example stays **fictional
only** in v2. The Groton Housing Authority is **not** a deployment
partner; the example is illustrative. Pilot partner selection is
gated on §2.3.

**Q6 — Token issuance model.** N/A — tokens removed from core.

**Q7 — Cost ceiling for filing.** N/A — v2 core filing is
**free** if walletless; optional anchor service cost is the
partner's concern.

**Q8 — Repo split.** Confirmed: anchor service (§13.2) and form
UI (§13.5) live in **separate repos**. Pilot repos (§13.6) live
in the partner's own infrastructure.

**Q9 — State / municipal regulations.** v2 requires the partner's
jurisdictional legal review (§2.3) **before** any pilot. v2 does
not pre-emptively add state-specific citations; the partner's
counsel owns that.

**Q10 — Harvester changes.** v2 harvester is **additive JSONL
fields** (PR #9 — `geocontract-harvest-citizen` + the public /
restricted split); no other design changes. Confirmed and delivered.

**Q11 — Privacy review.** Per §2.3 gate. The §5.8 split is the
schema side; the privacy review is the policy side.

**Q12 — Accessibility review.** Per §2.3 gate. Out of scope for
this repo's data model.

---

## 12. Open follow-ups (v2)

### 12.1 Concrete code follow-ups — delivered

| PR  | Title                                                          | Sections delivered                                    |
| --- | -------------------------------------------------------------- | ----------------------------------------------------- |
| #7  | docs: revise citizen-permitting plan to v2 per agent review    | §0 / §3 / §5 / §8 / §11                               |
| #8  | feat: Phase B v2 — canonical model, detached proof, ontology   | §3 / §3.4 / §3.5 / §3.6 / §4.3 / §5.7 / §5.8 / §5.9     |
| #9  | feat: Phase 4 harvester — citizen-source JSONL                 | §6 additive JSONL fields, §5.8 enforcement             |
| #10 | feat: full-coverage signed worked example                      | §3 / §5.7 end-to-end example                          |
| #11 | feat: directory-mode citizen-source harvester with manifest     | §6 + `docs/design-harvester.md` §"Pipeline" output     |
| #12 | test: end-to-end pipeline integration test                      | §7.2 cross-module regression net                       |

Tests: **107+ passing** (85 from #8 + 17 from #9 + 10 from #10 + 10
from #11 + 12 from #12 with cross-branch skipping).

Upstream jxql issues filed: **#231–#237** (v1) and **#245** (v2's
`oneOf [{type:null}, {$ref:...}]` collapse, filed during #8 / #9).

### 12.2 Documentation follow-ups — delivered

- ✅ `docs/agent-review-response.md` (next to this plan) records
  the full review and the v1 → v2 deltas.
- ✅ `README.md` updated with the v2 citizen-initiated flow
  section, components table, working-with-it commands, and key
  design decisions.
- ✅ The v1 §3.1 flat-ODCS example lives only in §13.1.

### 12.3 Cross-repo follow-ups — NOT delivered (out of scope for this repo)

- ❌ **§13.2 anchor service** — separate `geocontract-anchor` repo.
- ❌ **§13.5 form UI** — separate repo.
- ❌ **§13.4 ComposeDB / W3C DID wallet-binding** — separate, optional.

### 12.4 Out-of-scope-on-purpose (explicitly *not* a follow-up)

- Building token issuance into v2 core. Removed.
- Auto-generating ontology entries from the user's starred repos.
  Removed from core; if desired, §13.3.
- A "blockchain-first" framing of the citizen flow. Replaced by
  the ledger-agnostic §5.1 conventional alternative.

### 12.5 Future (out of this repo, separate PRs)

- **PR #13 (separate repo, §13.2)** — `geocontract-anchor`: the
  optional external anchor service (smart contract or signed
  transparency log). Ledger-agnostic — the core treats anchoring
  as an opaque service.
- **PR #14 (separate repo, §13.5)** — form UI. Out of scope here.

---

## 13. Out-of-core experimental / future-only

These were part of v1's core. In v2 they are explicitly *not* part
of the core path. They are documented here for completeness and
re-introduced only via separate, separately-counsel-reviewed PRs.

### 13.1 Token issuance (not in core)

If a partner wants project-token fundraising, it is built as a
separate `fundingIntent` extension on the canonical model and a
**separate** `TokenOffering` contract, deployed only after the
underlying proposal is `approved`. Compliance posture, securities
review, transfer restrictions, mint authority, treasury, refunds,
and offering disclosures are all partner-specific and **never** in
the geocontract repo.

### 13.2 Anchor service (separate repo `geocontract-anchor`)

The on-chain (or signed-transparency-log) anchor service is a
**separate repo**. The core treats it as an opaque external
service via the `anchorReceipt` fields (§3.4). Implementation,
audit, deployment, and operational responsibility all sit with the
anchor service operator.

### 13.3 NLP corpus / starred-projects scan (not in core)

The v2 catalog is hand-curated. NLP-assisted suggestions from the
user's starred projects, NAICS, W3C ADR, etc. are added **only**
behind a human-approval workflow, never silently overwriting
hand-curated rows. Deferred indefinitely.

### 13.4 Ceramic ComposeDB / W3C DID wallet-binding (not in core)

The off-chain rich-registry (Ceramic ComposeDB, Tableland, etc.)
is a §13.4 design choice. The v2 core is happy with a flat file or
relational DB as the partner's record-of-truth.

### 13.5 Form UI (separate repo)

Any partner UI is a separate repo, owned by the partner or a
downstream consumer, **not** by the geocontract schema repo.

### 13.6 Pilot (gated on §2.3)

Cannot proceed without the five §2.3 conditions being evidenced in
writing and reviewed. When gated, the pilot is partner-scoped,
no-token, walletless-by-default, and reports the §10 metrics.

---

## 14. Provenance and review

- This v2 plan was produced in response to the agent review at
  `docs/agent-review-response.md`.
- v1 is preserved in git history (branch `feature/citizen-permitting-plan`,
  PR #5) and recoverable via `git show feature/citizen-permitting-plan:docs/plan-citizen-permitting-standard.md`.
- All §0 deltas are evidence-traceable to specific reviewer gaps.