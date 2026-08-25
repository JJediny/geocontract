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
- **No PII handling.** All current geocontract sources are public
  federal records.

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

Phase 1 — **local-only** (no network). Iterate on the validator,
normaliser, and JSONL emitter using the bundled `contracts/`.

Phase 2 — **HTTPS + Git**. Add `httpx` and a shallow `git clone`
subprocess. The CLI surface stays the same.

Phase 3 — **S3 + index file**. Add `boto3` (or `aioboto3`) and a
polled-index mode where the harvester reads a YAML manifest from a
known URL.

Phase 4 — **streaming JSONL**. Emit records as they are produced
(rather than buffering) so the pipeline can be wired into long-running
consumers without re-runs.

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
