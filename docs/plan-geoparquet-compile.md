# Plan — Compile geocontracts into GeoParquet (generated / harvester)

Status: DRAFT — October 2026
Depends on: PR #25–#29 merged (main at 8892eee), Portolan spec v0.2.0

## 1. Goal

Every published geocontract becomes one queryable row in a single
STAC-GeoParquet file. A client downloads one Parquet object from the
bucket and filters the whole contract portfolio with HTTP range reads —
no API, no server, no STAC walking. This mirrors the pattern proven at
scale by [s2-stac-geoparquet](https://github.com/taylor-geospatial/s2-stac-geoparquet)
(30M Sentinel-2 scenes, one row per scene), applied at contract scale:
one row per geocontract.

Two compile paths, one file format:

| Path | Input | Trigger | Output |
| --- | --- | --- | --- |
| **Generated** | `catalog/**/collection.json` (already built by `catalog-build`) | `mise run geoparquet-build`, CI-gated | `examples/geocontracts.geoparquet` (tracked) |
| **Harvester** | harvested mirror contracts (`.harvest/`, external sources) | `scripts/harvest.py --sink geoparquet` | same file + harvested rows, published only |

The generated path is the source of truth for first-party rows. The
harvester path appends rows for third-party contracts the federated
harvester collects. Both read from STAC collections, never from raw
contract YAML.

## 2. Hard constraint — bbox provenance

Rows carry the **bbox as emitted in the generated STAC**, never a
re-derived one from the contract or manifest. The manifest deliberately
coarsens citizen-contract bboxes (`groton-rhine-001` is parcel-precise in
its ODCS schema; the manifest comment says re-deriving would re-expose
what the projection removed). The generator already applies the right
coarsening. Re-deriving in the Parquet step would leak precise parcels.

This is the same trust boundary DCAT and DataCite generation already
respect: they read `catalog/**/collection.json` and treat it as the only
permitted view. GeoParquet joins that pattern.

Track the bbox-coarsen extraction (issue #39) as a prerequisite — the
Parquet builder should import the same helper once it exists, so any
future coarsening change lands in all three outputs at once.

## 3. Row schema (v1)

One row per generated or harvested collection. Field names follow the
STAC fields the collections already carry.

| Column | Type | Source (collection.json) |
| --- | --- | --- |
| `geometry` | binary (WKB polygon, EPSG:4326) | `extent.spatial.bbox[0]` → 5-point polygon |
| `bbox` | struct{xmin, ymin, xmax, ymax} double | same bbox, as the declared `covering` column |
| `id` | string | `id` |
| `title` | string | `title` |
| `description` | string | `description` |
| `license` | string | `license` |
| `keywords` | list\<string\> | `keywords` |
| `tenant` | string | `geocontract:tenant` |
| `domain` | string | `geocontract:domain` |
| `status` | string | `geocontract:status` |
| `contract_version` | string | `geocontract:contract_version` |
| `primary_entity` | string | `geocontract:primary_entity` |
| `is_mirror` | bool | `geocontract:mirror` |
| `updated` | string (ISO date) | `updated` (manifest-authored, deterministic) |
| `via_url` | string, nullable | `links[]` where `rel == "via"` |
| `canonical_url` | string, nullable | `links[]` where `rel == "canonical"` |
| `self_url` | string | `links[]` where `rel == "self"` |
| `table_columns` | string (JSON) | `table:columns` |
| `assets` | string (JSON) | `assets` |
| `stac_extensions` | list\<string\> | `stac_extensions` |
| `collection_url` | string | path of the source collection.json (relative) |

Notes:

- `table_columns` and `assets` stay JSON strings in v1. Issue #40 (STAC
  search extension for `table:columns`) may promote them to Parquet
  list types in v2; JSON strings keep the v1 schema stable and lossless.
- JSON strings are canonical (sorted keys) via `canonicaljson`, which is
  already a dependency. Row order: sorted by `id`. No write timestamps —
  `updated` comes from the manifest, so rebuilds are byte-stable.

## 4. GeoParquet conformance — written against the real consumer

The QGIS plugin (`portolan-registry-qgis`, the registry's own client) is the
reference consumer. Its reader (`core/geoparquet.py`, `core/stac.py`)
defines what the file must carry:

- **`geo` metadata** (GeoParquet 1.1, version `"1.1.0"`) with
  `primary_column: "geometry"` and the CRS as WKT2 in
  `columns.geometry.crs` (EPSG:4326). The plugin picks the geometry column
  from `primary_column`, then from a `GEOMETRY`-typed column, then from a
  blob named `geometry`/`geom`/`wkb_geometry`/`the_geom`.
- **A `covering` declaration.** The plugin routes bbox filters through the
  GeoParquet 1.1 `covering` column *when the file declares one*, so DuckDB
  skips row groups via Parquet statistics instead of scanning the file.
  Therefore the row carries `bbox` as `STRUCT(xmin, ymin, xmax, ymax)`
  (double fields) and `geo.columns.geometry.covering.bbox` names the four
  field paths. The plugin's `_implicit_covering` fallback also accepts the
  struct without the declaration — declare it anyway.
- **http(s) href only.** The plugin's "Add to map" refuses object-store
  URIs. The published file must sit behind the catalog's public base URL.
- **Extension, not just media type.** The plugin detects `.parquet` /
  `.geoparquet` hrefs and loads them through DuckDB `COPY` into a
  GeoPackage. Assets with role `source` are excluded from "Add to map";
  the portfolio file is a `data`-role asset.

Writer: `pyarrow.parquet` (new dev dependency), zstd compression, rows
sorted by `id`, `write_statistics=True` on the `bbox` struct fields so
row-group pruning works with one row group per file at current scale.

## 5. Implementation steps

### PR A — `feat(catalog): GeoParquet compile of generated collections`

1. Add `pyarrow>=18` to dev extras (s2-stac-geoparquet pins 1.5.0 of
   geoparquet-io, but we only need the writer; pyarrow alone is
   sufficient and smaller).
2. New `scripts/build_geoparquet.py` + `src/geocontract_tools/build_geoparquet.py`
   following the build_dcat.py shape: read every
   `catalog/**/collection.json`, build one Arrow table, write
   `examples/geocontracts.geoparquet`.
3. Reject re-deriving bbox from contracts — read `extent.spatial.bbox`
   only (constraint §2). Fail the build if a collection lacks a bbox.
4. Determinism: sorted by id, canonical JSON strings, no wall-clock.
5. New validator flag `--geoparquet` on `scripts/validate_odcs.py`:
   reopen the file, assert the `geo` metadata version, assert every row
   geometry round-trips to the source bbox, assert row count equals
   collection count.
6. mise tasks: `build-geoparquet`, `validate-geoparquet`,
   `geoparquet-check = { depends = ["build-geoparquet",
   "validate-geoparquet", "datacite-check"] }` (reads `catalog/`, so it
   chains after the catalog-family gates), then add `geoparquet-check`
   to the `ci` depends list.
7. Tests: row-count parity, bbox round-trip for all six collections
   (including the coarsened `groton-rhine-001`), metadata assertions,
   byte-stable rebuild.

### PR B — `feat(harvest): --sink geoparquet`

1. Extend `scripts/harvest.py` with a `geoparquet` sink next to the
   existing `portolan` and JSONL sinks.
2. The harvester already emits STAC mirror collections
   (`update_mirror_catalog()`); the sink converts those to rows with the
   same builder from PR A (shared row-builder function).
3. Harvested rows carry `is_mirror = true` and the `via_url` the mirror
   pipeline already requires — no new provenance fields.
4. Output stays untracked (`.harvest/` is gitignored); publishing the
   combined file happens through the normal publish flow once issue #30
   unblocks the first publish.

### PR C — `docs: geoparquet row schema + consumer guide`

Short guide: where the file lands after publish, how to filter it with
duckdb/`httpfs` range reads (copy the s2-stac-geoparquet query pattern),
and the bbox-provenance warning for downstream users of
`groton-rhine-001`.

## 6. Relation to the open backlog

| Issue | Relation |
| --- | --- |
| #39 bbox-coarsen extraction | Prerequisite for sharing the helper; otherwise PR A reads generated bbox as-is |
| #40 table:columns search extension | v2 of the row schema may promote `table_columns` from JSON string to Parquet list |
| #30 first publish | Publishing the Parquet file needs the same `catalog.publish.yaml` destination |
| #34 Invenio harness | Independent — ingest validation, not file compilation |
| #31 helper dedupe | Touches the same shared-module seam; do #31 before PR A if convenient |

## 7. Codebase indexes (CocoIndex) — done 10 October 2026

Semantic code indexes back this plan and future work. Tool:
`cocoindex-code` 0.2.42 (`ccc`), installed with `[full]` extras
(sentence-transformers, local embedding, no API key). Model:
`Snowflake/snowflake-arctic-embed-xs` (384 dims), configured in
`~/.cocoindex_code/global_settings.yml`.

| Project | Chunks | Files | Query from |
| --- | --- | --- | --- |
| `portolan-spec` | 1,588 | 184 | `cd portolan-spec && ccc search "…"` |
| `portolan-skills` | 391 | 42 | `cd portolan-skills && ccc search "…"` |
| `s2-stac-geoparquet` | building | — | `cd s2-stac-geoparquet && ccc search "…"` |
| `portolan-registry-qgis` | building | — | `cd portolan-registry-qgis && ccc search "…"` |

Verified searches: "how must a catalog declare its license" → spec
philosophy + core; "harvest an external catalog and integrate citizen
proposals" → `skills/portolan-migrate/reference/tools/build_collection.py`.

Usage during implementation:

```bash
cd portolan-spec  && ccc index && ccc search "bbox coarsening rule"
cd portolan-skills && ccc index && ccc search "federated harvest sink"
ccc grep            # structural grep, no index needed
```

Housekeeping (proposed issue): add mise tasks `code-index-spec` /
`code-index-skills` (mise `dir` attribute per task) and a combined
`code-index` task; keep `.cocoindex_code/` untracked in each submodule
(do not commit the index DBs to the spec/skills repos). The daemon
idle-exits after 180 minutes and restarts on demand, so no service
management is needed.

## 8. Integration potentials — what each submodule contributes

Analysis grounded in the four submodules and the spec, 10 October 2026.

### 8.1 The spec names this exact construct as incubating

`portolan-spec/specs/incubating/stac-geoparquet.md` says:

> A complementary construct could index the collections in an entire
> catalog ... Such a file would let clients search every collection in a
> catalog with a single read ... The encoding is still unsettled.
> Collection extents are ranges rather than footprints, summaries have no
> standard representation, and no existing tooling reads such a file.

That is the portfolio file this plan builds. geocontract can be the first
working implementation and feed the encoding back upstream:

- extents-as-ranges → answered here by the WKB bbox polygon plus the
  `covering` struct (§3, §4);
- no standard summary representation → answered by typed columns for the
  per-collection facts and canonical-JSON strings for the leftovers
  (`table:columns`, `assets`), the same decision s2-stac-geoparquet made
  for `assets` at 30M-row scale.

Spec changes belong upstream (portolan-spec is ground truth). Once #44
lands, propose the encoding there with the file as evidence. Tracked as
an issue; a human decides when to open the upstream conversation.

### 8.2 s2-stac-geoparquet — the conventions to copy

| Convention | Evidence | geocontract action |
| --- | --- | --- |
| `table:columns` with full Parquet type strings (`STRUCT(...)[]`, `timestamp[us, tz=UTC]`) | `catalog/sentinel-2-c1-l2a/collection.json` | Issue #40 should adopt this syntax, not the current SQL-ish `varchar`/`bigint` |
| `partition:*` (incubating extension) + `table:row_count`, `table:primary_geometry` | same collection | Emit for the portfolio file once published; no partitioning at 6 rows |
| `assets` as verbatim JSON string in the table | same | Already the plan v1 choice — validated at scale |
| Query helpers (`_tile`, `_hilbert`) documented as non-STAC in a per-collection AGENTS.md | same | Skip at current scale; sort by `id` |
| A `stats` sibling collection of aggregates | `catalog/stats-c1/` | Defer; revisit if the portfolio grows past hundreds |
| Static sidecar page (hyparquet + PMTiles, `rel: preview`) | `links[]` in same collection | Deferred potential, gated on #30 |

### 8.3 portolan-registry-qgis — the consumer contract

The plugin is the payoff path for the whole catalog:

publish (#30) → register (register-catalog skill) → browse in QGIS →
"Add to map" loads the portfolio GeoParquet via DuckDB.

What it reads, in order: `rel: pmtiles` links first (web-map-links
extension, drawn with the collection's MapLibre style asset), then
`.parquet`/`.geoparquet` assets, then COG, FlatGeobuf, COPC. Everything
must be http(s). Three consequences:

1. **The portfolio file must be a `data`-role asset on an http(s) URL**
   (§4) or the plugin never offers it.
2. **A PMTiles footprint index** (one PMTiles of all contract bboxes,
   plus a web-map-links `pmtiles` link and a `style` asset) would become
   the plugin's *preferred* view — `preferred_href()` puts pmtiles first.
   Deferred potential, filed as an issue, gated on #30.
3. **The registry export is the discovery surface**: the plugin reads
   `portolan-registry`'s `exports/catalogs.json` and keeps
   `portolan_registry:*` fields. Registration (publish-checklist §5) is
   what puts geocontract in front of every plugin user.

### 8.4 The two GeoParquet constructs, sequenced

Portolan distinguishes two mirrors; geocontract needs both eventually:

| Construct | Spec status | Content | Sequencing |
| --- | --- | --- | --- |
| Portfolio index (this plan) | Incubating, encoding unsettled | one row per collection | Now — #44/#45, deterministic, CI-gated |
| Data item mirror | Ratified for raster; `stac-geoparquet` tooling exists | one row per data record (e.g. the 3,415 exclusion rows) | When data assets land in the bucket — repo plan already says "converted + spatially sorted via gpio"; gated on #30 |

Do not build the data mirrors before the data exists in the bucket. The
portfolio index needs only what main already generates.

## 9. Open questions

1. Should the generated file be **tracked in git** (`examples/`) like the
   DCAT and DataCite examples, or published-only? Default: tracked, for
   CI byte-stability checks — matches how `build-dcat` output is
   reviewed today.
2. Harvested rows in the tracked file would make rebuilds depend on
   network state. Default: the tracked file carries generated rows only;
   the harvester sink writes a separate file (or partition) that only
   publish sees. PR B takes this default unless a review argues
   otherwise.
3. Geometry for contracts whose bbox is the whole-CONUS default
   (`[-125.0, 24.0, -66.0, 50.0]`) is valid but low-information; no
   special-casing in v1. Revisit if a consumer complains.
