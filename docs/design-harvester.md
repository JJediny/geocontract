# Future Planning — Federated Harvester

## Goal

The geocontract project produces **multiple ODCS v3.1.0 data contracts**
(`*.geocontract.yaml`) that can reside **anywhere** — in any Git repo, on
any HTTPS endpoint, in any object store. The eventual **federated
harvester** walks these locations, fetches each contract, validates it
against the canonical ODCS schema, normalises it into the canonical
`Exclusion` / `Project` / `ProcessInstance` / … record view, and emits
a unified JSON-Lines stream that downstream consumers (the mesh-gateway,
search index, dashboards) can ingest.

This document captures the **design intent** before we commit to a
specific implementation.

---

## Non-goals (today)

- **No persistent database.** The harvester is read-only and produces a
  transient snapshot. Caching/incremental refresh is a separate
  concern.
- **No write-back.** The harvester must not modify any source contract.
- **No remote PII handling.** The federated harvester does not yet
  fetch or manage restricted identity sources. Citizen-source harvesting
  has an explicit public projection and an opt-in restricted projection;
  real authority authentication and partner retention policy remain
  deployment gates.

---

## Sources we expect to harvest

| Source kind | Example                                                  | How it's fetched today     |
| ----------- | -------------------------------------------------------- | -------------------------- |
| Local file  | `../agency-x/contracts/foo.geocontract.yaml`             | Direct `pathlib.Path.read_text()` |
| Git repo    | `https://github.com/permits/pyper`                       | `git clone --depth 1`     |
| HTTPS       | `https://ce.permitting.innovation.gov/data/exclusions.json` (raw upstream) | `httpx`/`urllib`          |
| S3          | `s3://permits-pic-public/contracts/*.yaml`               | `boto3`                    |

Each source yields one or more `*.geocontract.yaml` files. The harvester
discovers them by:

1. **Explicit list** — `geocontract-harvest https://… …` (CLI)
2. **Index file** — a YAML/JSON manifest at a known URL listing all
   sources, refreshed by the PIC
3. **DNS-style discovery** — TXT records under
   `_geocontract.agency.gov` pointing to the contract URL (future)

---

## Pipeline

```
                         ┌──────────────────────────────────────┐
                         │   Source(s) — local / git / http     │
                         └──────────────────────┬───────────────┘
                                                │ fetch
                                                ▼
   ┌────────────────────────────────────────────────────────────┐
   │  1. Locate  *.geocontract.yaml inside the source           │
   │     (root, contracts/, .geocontract/, etc.)                │
   └──────────────────────────┬─────────────────────────────────┘
                              │ read
                              ▼
   ┌────────────────────────────────────────────────────────────┐
   │  2. Validate against ODCS v3.1.0 (external/odcs-json-schema │
   │     -v3.1.0.json) via Draft 2019-09 validator              │
   └──────────────────────────┬─────────────────────────────────┘
                              │ ok / fail
                              ▼
   ┌────────────────────────────────────────────────────────────┐
   │  3. Normalise                                               │
   │     - Convert snake_case physicalNames → camelCase keys     │
   │     - Resolve x-graphql-field-name / field-mapping entries  │
   │     - Flatten `schema[]` into one JSON object per entity    │
   └──────────────────────────┬─────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────┐
   │  4. Emit                                                    │
   │     - .harvest/manifest.json     (provenance + hashes)      │
   │     - .harvest/records.jsonl     (one line per record)      │
   │     - .harvest/contracts/*.yaml  (validated copies)         │
   └────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌──────────────────────┐
                  │  Downstream consumer │
                  │  (mesh-gateway, ES)  │
                  └──────────────────────┘
```

---

## Output schema (JSON Lines, one record per line)

Each line is a JSON object with:

```jsonc
{
  "source": "https://github.com/permits/pyper",
  "contract_id": "geocontract-pic-nepa-data-standard",
  "contract_version": "1.2.0",
  "fetched_at": "2026-08-24T12:34:56Z",
  "schema_hash": "sha256:…",
  "entity": "Project",
  "physical_name": "project",
  "properties": {
    "id":           { "logicalType": "integer", "physicalType": "BIGINT", "primaryKey": true, "required": true,  "criticalDataElement": true,  "classification": "public" },
    "leadAgency":   { "logicalType": "string",  "physicalType": "VARCHAR(255)", "physicalName": "lead_agency", "required": false, "classification": "public" },
    "currentStatus":{ "logicalType": "string",  "physicalType": "VARCHAR(32)",  "physicalName": "current_status", "required": false, "classification": "public" }
  },
  "quality": [ … ],
  "sla": [ … ],
  "lineage": { … },
  "tags": [ … ],
  "custom_properties": { … }
}
```

This shape is designed so that downstream consumers (mesh-gateway,
search index, dashboards) can ingest one line per entity without
needing the parent contract context — but the `contract_id` /
`contract_version` / `schema_hash` triplet lets them reconstruct the
graph when needed.

### Citizen-initiated contract fields (additive; v2)

For contracts authored under the citizen-permitting flow
(`docs/plan-citizen-permitting-standard.md` §6), the per-entity
JSONL record carries the additive fields below. **All are optional
and only present when the source has the data.**

| Field                  | Type     | Notes                                                  |
| ---------------------- | -------- | ------------------------------------------------------ |
| `content_hash`         | string   | `sha256:…` over canonicalised bytes of the proposal (proof excluded). Required. |
| `submission_id`        | string   | Opaque id returned by the anchor service. Optional.    |
| `anchor_service_ref`   | string   | URI of the anchor service (for re-checking). Optional.  |
| `lifecycle_state`      | string   | FSM state (draft / submitted / anchored / under_review / approved / rejected / amended / superseded / revoked / expired). Required. |
| `supersedes`           | string   | Content hash of the predecessor revision. Optional.    |
| `projection`           | string   | `public` (default) or `restricted`. Required.          |

The fields are surfaced by `geocontract-harvest-citizen`
(`src/geocontract_tools/citizen_source.py`). The **restricted**
projection carries applicant / proof / raw geometry and requires
`--authority-token <token>`; without it, the CLI refuses. This
mirrors the plan §5.8 split.

---

## CLI surface (tentative)

```bash
geocontract-harvest \
    https://github.com/JJediny/geocontract \
    ../agency-x/contracts \
    https://example.gov/geocontract.yaml \
    --out .harvest \
    --concurrency 8 \
    --format jsonl
```

Flags:

| Flag              | Purpose                                                |
| ----------------- | ------------------------------------------------------ |
| `--out`           | Output directory (default: `./.harvest`)               |
| `--concurrency`   | Parallel source fetches (default: 4)                   |
| `--format`        | `jsonl` (default) \| `parquet` \| `csv`                |
| `--strict`        | Fail the harvest on any validation error (default: true)|
| `--cache-ttl`     | Re-fetch sources older than N seconds (default: 0)     |
| `--index`         | URL of a YAML manifest listing every source            |

---

## Implementation strategy

The v2 plan (`docs/plan-citizen-permitting-standard.md` §8) replaces
the original 4-phase roadmap with a **Phase 0..6** sequence. The
geocontract-repo implementation strategy for the harvester is now:

**Phase 0–4 (in this repo):**

- **Phase 0–3** — the canonical model, detached proof, ontology,
  ODCS-flatten projection, public projection (PR #8).
- **Phase 4** — the citizen-source harvester
  (`geocontract-harvest-citizen`) which emits JSONL records with
  the additive fields per §6 (PR #9).

**Out-of-repo (per §13):**

- **§13.2 anchor service** — separate `geocontract-anchor` repo.
- **§13.4 ComposeDB** — separate, optional, ledger-agnostic.
- **§13.5 form UI** — separate repo.
- **§13.6 pilot** — partner-scoped, no-token, gated on §2.3.

**Concrete Phase 4 deliverables in this repo (PR #9 + this doc):**

- `src/geocontract_tools/citizen_source.py` — emits one JSONL record
  per Proposal, public projection by default, restricted projection
  behind `--authority-token`.
- `docs/design-harvester.md` §"Pipeline" — declarative spec for the
  manifest + records.jsonl output layout.
- `docs/design-harvester.md` §"Citizen-initiated contract fields
  (additive; v2)" — additive JSONL fields spec, matches the
  implementation.

**Deferred (none of these are in the v2 core):**

- HTTPS / Git fetching (Phase 2 of the v1 plan).
- S3 / index-file support (Phase 3 of the v1 plan).
- Streaming JSONL (Phase 4 of the v1 plan, deferred; current
  implementation is buffer-then-emit).
- RPC, on-chain event reading, ComposeDB (all §13).

---

## Open questions

1. **Conflict resolution.** Two sources may publish overlapping
   contracts (e.g. both PIC and a sub-agency publish a `Project`
   schema). Should the harvester merge, fail, or pick the highest-
   priority source?
2. **Versioning.** A contract `version: 1.2.0` may have breaking
   changes. Should the harvester refuse to ingest a version it
   doesn't understand, or attempt a best-effort forward-compat?
3. **Schema evolution.** When a source adds a new entity type, do we
   re-emit the full JSONL or only the delta? (Forward-only diffing is
   simpler; full re-emission is safer.)

These questions don't block Phase 1; we'll answer them with concrete
usage once we have real downstream consumers.
