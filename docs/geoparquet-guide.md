# Consumer guide — the GeoParquet portfolio file

`examples/geocontracts.geoparquet` is the whole contract portfolio in
one file: one row per generated collection, built by
`mise run geoparquet-check` from `catalog/**/collection.json`. After
publish, the same file sits in the bucket and a client reads it with
HTTP range requests — no API, no server, no STAC walking.

Resolves #46. The build side is docs/plan-geoparquet-compile.md.

## Where the file lives

| Stage | Path | Notes |
| --- | --- | --- |
| Tracked | `examples/geocontracts.geoparquet` | Rebuilt and validated by CI, byte-stable |
| Published | `<public_base>/geocontracts.geoparquet` | Blocked: publish syncs `catalog/` only today |

The published URL is an http(s) URL. The QGIS plugin refuses
object-store URIs such as `s3://` for "Add to map", so link the
published file, never the bucket URI.

Publishing needs two steps that both wait on issue #30: the
`catalog.publish.yaml` placeholders, and a one-line extension to
`tools/publish.py` that adds the portfolio file to the sync. Until
then, the tracked file is the artifact to read.

## Read it with DuckDB

DuckDB 1.5 or newer, plus its `spatial` extension. Point it at the
file with `read_parquet` — the reader does not auto-detect the
`.geoparquet` extension, so the explicit function is required. Every
query below ran against the tracked file:

```sql
INSTALL spatial; LOAD spatial;  -- once per session
-- add INSTALL httpfs; LOAD httpfs; for the published URL

-- Every contract in the portfolio, one row each.
SELECT id, license, is_mirror, updated, st_geometrytype(geometry) AS geometry
FROM read_parquet('examples/geocontracts.geoparquet')
ORDER BY id;

-- Contracts intersecting a place, reading only the row groups that
-- hold them. The covering struct drives the statistics pruning. A
-- CONUS-wide bbox intersects every place window; that is the data
-- speaking, not a bug.
SELECT id, title
FROM read_parquet('examples/geocontracts.geoparquet')
WHERE bbox.xmax >= -73.0 AND bbox.xmin <= -71.0
  AND bbox.ymax >= 41.0  AND bbox.ymin <= 42.0;

-- The columns of one contract, as a table description.
SELECT table_columns
FROM read_parquet('examples/geocontracts.geoparquet')
WHERE id = 'federal/nepa-exclusions';
```

`table_columns` and `assets` are canonical-JSON strings. Parse them with
`json_extract` (DuckDB) or `JSON.parse` (JavaScript), the same
convention s2-stac-geoparquet documents for its 30M-row table.

## Read it in QGIS

The [Portolan Registry
plugin](https://github.com/portolan-sdi/portolan-registry-qgis) loads
`.parquet` and `.geoparquet` assets through DuckDB into a GeoPackage.
It needs DuckDB 1.5.0 or newer inside QGIS's Python. Once the catalog is
published (#30) and registered, the portfolio file appears on the
collection and "Add to map" draws every contract bbox.

## Provenance warning — read before you use a bbox

Every row's `geometry` and `bbox` come from the generated collection,
never from the contract schema. For `citizen/groton-rhine-001` this is
deliberate: the manifest coarsens the parcel-precise bbox because the
contract's public projection removed parcel detail. Treat that row's
geometry as approximate, and never re-derive a bbox from a contract
schema. See docs/plan-geoparquet-compile.md §2.

## Schema reference

The `geo` metadata declares GeoParquet 2.0, primary column `geometry`
(WKB, geoarrow.wkb extension type, OGC:CRS84 as PROJJSON, lon/lat), and
the `bbox` covering struct. Row fields:

| Column | Type | Meaning |
| --- | --- | --- |
| `geometry` | binary (WKB polygon) | The bbox as a 5-point polygon |
| `bbox` | struct(xmin, ymin, xmax, ymax) | Covering column; drives pruning |
| `id`, `title`, `description` | string | Collection identity |
| `license` | string | SPDX expression for the data |
| `keywords` | list<string> | Manifest keywords |
| `tenant`, `domain`, `status`, `contract_version`, `primary_entity` | string | `geocontract:*` facts, nullable |
| `is_mirror` | bool | Producer differs from host (provenance F3) |
| `updated` | string | Manifest-authored date; never a build timestamp |
| `via_url`, `canonical_url`, `self_url` | string | Provenance links, nullable |
| `table_columns`, `assets` | string | Canonical JSON |
| `stac_extensions` | list<string> | Extension URIs |
| `collection_url` | string | Source `collection.json` in the tree |
