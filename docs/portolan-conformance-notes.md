# Portolan conformance notes

This file records what `rashid` 0.1.8 enforces on a geocontract catalog.
Every finding below came from a real probe run on 3 October 2026.
The probes live in a scratch tree under `.tools/` and are not published.

The Portolan specification is ground truth.
`rashid` implements it.
See `portolan-spec/specs/portolan/requirements.yaml` for the requirement
ids that each rule cites.

---

## Why this file exists

The geocontract catalog carries data contracts, not geospatial data.
The contracts are small YAML files.
Most collections will describe a table with no geometry.
That shape is unusual for a Portolan catalog.
So the team ran probes before it wrote the generator.
The answers below shape `scripts/build_catalog.py`.

---

## Probe method

Round 1 built three collections that differed in one variable each.
Round 2 built four collections, including two negative controls.
A negative control plants a known violation.
It proves the validator fires, so a clean result means something.

Command used for both rounds:

```bash
uvx --from 'rashid>=0.1.8,<0.2.0' rashid check .tools/probe5-catalog \
  --schema --no-data --all --json
```

`--schema` runs the bundled Portolan profile schema.
`--no-data` skips the asset byte checks, because the probes carry no real data.
`--all` lists every finding instead of the first 50.

Calibration run first, to prove the toolchain works:

```bash
uvx --from 'rashid>=0.1.8,<0.2.0' rashid check \
  portolan-spec/examples/catalog/portolan-reference --summary
```

Output:

```text
0 error(s), 0 warning(s), 16 info(s) across 28 files.
```

The 16 info findings all cite `PTL-PRO-002`.
They ask mirror collections to add a `canonical` link.
The reference catalog omits those links on purpose, so info is the ceiling
for a conformant catalog.

---

## Findings

### F1. A metadata-only collection passes

Probe: `probe-a-meta-only` carried one asset.
That asset had `roles: ["metadata"]` and pointed at an ODCS YAML file.
The collection had no `data`-role asset.

Result: no error about a missing data asset.

Conclusion: **a collection may publish only its contract YAML.**
Portolan does not require a `data`-role asset on every collection.
This unblocks Phase 1, because the first three collections describe
contracts whose bulk data is not yet converted.

### F2. Custom `geocontract:*` properties pass the schema

Probe: `probe-b-custom-props` was identical to `probe-a-meta-only`, plus
three custom properties:

```json
"geocontract:version": "0.1.0",
"geocontract:status": "active",
"geocontract:lifecycle_state": "draft"
```

Result: the finding list was byte-identical to `probe-a-meta-only`.

Conclusion: **the profile schema tolerates prefixed custom properties.**
The generator may carry contract version, status, and citizen lifecycle
state on the collection itself.
No fallback into README prose is needed.

### F3. `rashid` derives mirror status from `providers`

Probe: `probe-f-mirror-no-via` listed two providers.
`Permitting Innovation Center` held `producer`.
`geocontract` held `host`.

Result:

```text
[error] PTL-PRO-001: mirror collection has no rel:'via' link to its original source
```

Probe: `probe-d-official` listed one provider that held `producer`,
`licensor`, and `host` together.

Result: **clean. Zero findings.**

Conclusion: **producer and host decide the kind.**
When the same organisation holds both roles, the collection is official.
When they differ, the collection is a mirror, and `via` becomes an error,
not a suggestion.

This matches the reference manifest, which states the rule in prose:

> If the sole producer org differs from the host, the collection is a
> mirror and MUST carry provenance.via and provenance.updated
> (build.py errors otherwise).

See `portolan-spec/examples/manifests/portolan-reference.yaml`.

Design consequence for geocontract:

| Collection | Producer | Host | Kind | Needs `via` |
| --- | --- | --- | --- | --- |
| `standards/pic-standards` | geocontract | geocontract | official | no |
| `citizen/groton-rhine-001` | geocontract | geocontract | official | no |
| `federal/nepa-exclusions` | Permitting Innovation Center | geocontract | mirror | **yes** |
| `mirror/<harvested>` | upstream agency | geocontract | mirror | **yes** |

The federal CATEX catalogue is upstream data that geocontract republishes.
So it is a mirror, even though the producer is also a federal body.
Naming the producer as host would be false.

### F4. The `via` link must be `text/html`

Probe: `probe-e-mirror-via` carried a `via` link with
`"type": "application/json"`, pointing at the raw upstream JSON endpoint.

Result:

```text
[error] PTL-PRO-001: rel:'via' link has type 'application/json', expected 'text/html'
```

Conclusion: **`via` points at a human-readable landing page, not at the
raw data URL.**
The rule description states it plainly:

> a mirror must include a rel:'via' link (type text/html) to the original source

For `federal/nepa-exclusions` this splits two URLs that the ODCS contract
carries as one `servers[].location`:

| Purpose | URL | Link |
| --- | --- | --- |
| Human landing page | `https://ce.permitting.innovation.gov/` | `rel: via`, `text/html` |
| Raw data endpoint | `https://ce.permitting.innovation.gov/data/exclusions.json` | `source`-role asset, or `rel: canonical` when upstream publishes STAC |

The generator cannot derive the landing page from `servers[].location`.
So the catalog manifest must state it. See F7.

### F5. `table:columns` settles whether a collection is geospatial

Probe: `probe-g-no-tablecols` was official and otherwise clean, but
declared no `table:columns`.

Result:

```text
[warning] PTL-VIZ-001: collection has no asset with the 'thumbnail' role, and
whether it is geospatial cannot be decided from metadata: no item supplies a
geometry, neither it nor its assets declare table:columns, and no asset
carries an inherently spatial media type (PMTiles, COG, or COPC)
```

Probe: `probe-d-official` declared `table:columns` and was clean.

Conclusion: **declaring `table:columns` removes the ambiguity.**
Without it the validator cannot tell a table from a spatial layer, so it
asks for a thumbnail.
The generator emits `table:columns` for every non-spatial collection,
derived from the contract `schema[].properties`.

### F6. Asset size and checksum are warnings, and cheap to satisfy

Probe: round 1 collections omitted `file:size` and `file:checksum`.

Result:

```text
[warning] PTL-AST-003: asset 'contract' has no file:checksum
[warning] PTL-AST-003: asset 'contract' has no file:size
```

Round 2 supplied both, and the warnings disappeared.

Conclusion: **the generator computes them at build time.**
The checksum is a multihash: the prefix `1220` means sha2-256 with a
32-byte digest, followed by the hex digest.

```python
"file:checksum": "1220" + hashlib.sha256(data).hexdigest()
```

Because the contract YAML is the asset, every contract edit changes the
checksum. That is correct. It makes the published catalog a verifiable
record of which contract version shipped.

### F7. ODCS cannot carry the catalog facts

Probe: read the pinned ODCS v3.1.0 schema.

```text
additionalProperties: False
top-level props: apiVersion, authoritativeDefinitions, contractCreatedTs,
customProperties, dataProduct, description, domain, id, kind, name, price,
roles, schema, servers, slaDefaultElement, slaProperties, status, support,
tags, team, tenant, version
has license: False
```

Conclusion: **ODCS has no `license` field and rejects unknown keys.**
Adding `license` to a contract YAML would break `mise run validate-odcs`.

Portolan requires `license` on every collection, and also needs facts that
ODCS has no slot for: the area-of-interest `bbox`, the host provider, and
the `via` landing page from F4.

Decision: **a catalog manifest carries the catalog-only facts.**
The generator reads two inputs:

| Input | Carries |
| --- | --- |
| `contracts/*.datacontract.yaml` | semantics: id, name, description, schema, tags, tenant, servers |
| `catalog/manifests/geocontract.yaml` | catalog facts: license, bbox, host, via, keywords, nested-catalog titles |

This follows the reference implementation. Its manifest states:

> Everything catalog-specific lives here, not in the generator.

`customProperties` stays available for contract-level extensions, because
ODCS sanctions it. The manifest is preferred for catalog facts, so each
fact has one home.

### F8. README must mention provenance and license

Probe: round 1 README files were two sentences long.

Result:

```text
[warning] PTL-FIL-005: README.md does not appear to mention the data's provenance
[warning] PTL-FIL-005: README.md does not appear to mention the license
```

Round 2 added a `## Provenance` section and a `## License` section, and the
warnings disappeared.

Conclusion: **the generator seeds both sections into every README.**
Provenance names the producer and the upstream URL.
License names the SPDX id and links the license text.
Human authors then extend the prose; the generator does not overwrite it.

---

## The validated clean template

`probe-d-official` produced zero findings. It is the template the
generator targets. Its shape:

```jsonc
{
  "type": "Collection",
  "stac_version": "1.1.0",
  "stac_extensions": [
    "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json",
    "https://stac-extensions.github.io/file/v2.1.0/schema.json",
    "https://stac-extensions.github.io/table/v1.2.0/schema.json"
  ],
  "id": "<sub-catalog>/<slug>",
  "title": "<human-readable, from contract name>",
  "description": "<from contract description.purpose>",
  "license": "CC0-1.0",
  "keywords": ["<from contract tags>"],
  "providers": [
    { "name": "geocontract", "url": "...", "email": "...",
      "roles": ["producer", "licensor", "host"] }
  ],
  "extent": {
    "spatial": { "bbox": [[-125.0, 24.0, -66.0, 50.0]] },
    "temporal": { "interval": [["<contractCreatedTs>", null]] }
  },
  "table:columns": [ { "name": "...", "type": "...", "description": "..." } ],
  "assets": {
    "contract": {
      "href": "./<slug>.datacontract.yaml",
      "type": "application/yaml",
      "title": "ODCS v3.1.0 data contract",
      "roles": ["metadata"],
      "file:size": 1234,
      "file:checksum": "1220<sha256 hex>"
    }
  },
  "links": [
    { "rel": "root",  "href": "../catalog.json", "type": "application/json" },
    { "rel": "parent", "href": "../catalog.json", "type": "application/json" },
    { "rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "hreflang": "en" },
    { "rel": "describedby", "href": "./README.md", "type": "text/markdown", "hreflang": "en" }
  ],
  "updated": "<RFC 3339>"
}
```

A mirror collection adds one link and a differing producer:

```jsonc
{ "rel": "via", "href": "https://<landing-page>/", "type": "text/html",
  "title": "Original source" }
```

---

## Decisions this file settles

| # | Question from the plan | Answer | Evidence |
| --- | --- | --- | --- |
| P0-1 | Does a metadata-only collection pass? | Yes | F1 |
| P0-2 | Are `geocontract:*` properties tolerated? | Yes | F2 |
| P0-3 | Where does the license live? | Catalog manifest | F7 |
| — | How is a mirror expressed? | Differing producer and host, plus `via` as `text/html` | F3, F4 |
| — | How is a non-spatial collection expressed? | `table:columns` plus an area-of-interest bbox | F5, `core.md` |

## Submodule pin state

Recorded on 3 October 2026, so a later reader can tell what was validated.

| Submodule | Commit | Nearest tag |
| --- | --- | --- |
| `portolan-spec` | `0143bb6d0ad0dbeab695d2cabff78c99e6e547db` | past `v0.2.0` (`6c6943b`) |
| `portolan-skills` | `021fa95a1e23bb5b4e3e2c1f4dd4494e937efd19` | `v0.2.0-23` |

`git tag --contains HEAD` returns nothing for `portolan-spec`, so the pinned
commit is ahead of the `v0.2.0` release rather than on it.
`portolan-skills/pins.toml` pins the spec by tag:

```toml
[portolan-spec]
tag = "v0.2.0"
```

So this repo reads a spec revision the skills do not describe. That is a drift
risk, not a defect today. Two facts bound it:

1. The submodule carries `stac/json-schema/v0.2.0/schema.json`, which is the
   schema `PORTOLAN_SCHEMA_URI` in `mise.toml` names. Released schemas are
   immutable, so the URI still resolves to the same document.
2. `mise run portolan-calibrate` passes at this commit. The reference catalog
   in the submodule reports zero errors and zero warnings under rashid 0.1.8.
   That proves the pinned triple (spec commit, rashid, schema URI) agrees.

Moving the submodule back onto the `v0.2.0` tag would remove the drift. That is
a human decision, because the staged commit came from the repository owner.
See the open items below.

---

## Open items

1. **License per collection.** This file proposes `CC0-1.0` for federal
   sources, to match the repo license in `pyproject.toml`. United States
   government works are public domain by statute rather than by CC0
   dedication. A human should confirm the choice, or choose `other` with a
   `license_url` that cites 17 U.S.C. § 105.
2. **Citizen proposal license.** Proposals arrive from residents. The
   default needs a policy decision before Phase 4 publishes any of them.
3. **Area-of-interest bbox per collection.** CONUS
   `[-125.0, 24.0, -66.0, 50.0]` suits federal sources. A citizen proposal
   on one parcel needs that parcel bbox, not CONUS. The manifest states it
   per collection.
4. **`dcat-us-catalog.datacontract.yaml` is not a collection.** It
   describes the catalog envelope, not a dataset. Phase 5 regenerates it
   from the tree instead of cataloging it.
5. **Submodule pin drift.** `portolan-spec` sits ahead of the `v0.2.0` tag
   that `portolan-skills/pins.toml` names. Decide whether to move the
   submodule onto the tag, or to accept the drift and re-run
   `mise run portolan-calibrate` after every submodule bump.
