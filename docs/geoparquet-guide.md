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
| Published | `<public_base>/examples/geocontracts.geoparquet` | `public_base` comes from `catalog.publish.yaml`; blocked on #30 |

The published URL is an http(s) URL. The QGIS plugin refuses
object-store URIs such as `s3://` for "Add to map", so link the
published file, never the bucket URI.

## Read it with DuckDB

Install nothing beyond DuckDB 1.5 or newer, then point it at the file.
The queries below run against the tracked file from the repo root:

```sql
INSTALL httpfs; LOAD httpfs;  -- only for the published URL, not local files

-- Every contract in the portfolio, one row each.
SELECT id, license, is_mirror, updated
FROM 'examples/geocontracts.geoparquet'
ORDER BY id;

-- Contracts intersecting a place, reading only the row groups that
-- hold them. The covering struct drives the statistics pruning.
SELECT id, title
FROM 'examples/geocontracts.geoparquet'
WHERE bbox.xmax >= -73.0 AND bbox.xmin <= -71.0
  AND bbox.ymax >= 41.0  AND bbox.ymin <= 42.0;

-- The columns of one contract, as a table description.
SELECT table_columns
FROM 'examples/geocontracts.geoparquet'
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

The `geo` metadata declares GeoParquet 1.1, primary column `geometry`
(WKB, OGC:CRS84, lon/lat), and the `bbox` covering struct. Row fields:

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
