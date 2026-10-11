#!/usr/bin/env python3
"""Build the STAC-GeoParquet portfolio file from the generated Portolan tree.

One row per generated collection, so a client reads the whole contract
portfolio from one Parquet object with HTTP range reads and no STAC
walking. The plan is docs/plan-geoparquet-compile.md; this module is its
PR A (issue #44).

The builder reads only `catalog/**/collection.json`. It never re-derives
a bbox from a contract or the manifest: citizen bboxes are deliberately
coarsened in the manifest, and re-deriving would re-expose what the
projection removed (plan §2). The generated tree is the permitted view,
the same trust boundary build_dcat.py and build_datacite.py already
respect.

Conformance targets the registry's QGIS plugin
(portolan-registry-qgis core/geoparquet.py) and its engine, DuckDB 1.5:

- `geo` metadata, GeoParquet 2.0, primary_column "geometry", WKB
  encoding, `geometry_types`, and the CRS as PROJJSON with its OGC id —
  DuckDB 1.5 rejects a WKT2 CRS ("invalid CRS") and rejects a 1.1-style
  metadata block ("does not have geometry types"), both verified against
  read_parquet with the spatial extension loaded;
- the geometry column as a geoarrow.wkb Arrow extension type via
  geoarrow-pyarrow, the writer the s2-stac-geoparquet catalog builds on;
- a `bbox` covering struct declared in the covering metadata, so the
  plugin's DuckDB reader prunes row groups via Parquet statistics;
- typed columns for the per-collection facts; `table:columns` and
  `assets` ride as canonical-JSON strings, the same decision
  s2-stac-geoparquet made for `assets` at 30M-row scale.

Deterministic: rows sort by id, JSON strings are canonical, no
wall-clock values. `updated` comes from the manifest via the generated
tree. Rebuilding an unchanged tree reproduces the file byte for byte
(same pyarrow version; the footer records the writer version).

Validation reopens the written file and asserts the invariants above
plus bbox round-trips against the source collections, instead of
trusting the write. `--validate-only` skips the build, mirroring how
catalog-check re-runs rashid over what catalog-build produced.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import canonicaljson
import geoarrow.pyarrow as ga
import pyarrow as pa
import pyarrow.parquet as pq
import pyproj

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "catalog"
OUT_PATH = ROOT / "examples" / "geocontracts.geoparquet"

GEO_VERSION = "2.0.0"
GEOMETRY_COLUMN = "geometry"
COVERING_COLUMN = "bbox"
GEOMETRY_TYPES = ["Polygon"]

# GeoParquet 2.0 carries the CRS as PROJJSON. OGC:CRS84 is longitude/latitude,
# matching the axis order of every bbox the manifest records. A WKT2 string
# (the 1.1 form) makes DuckDB 1.5 reject the file with "invalid CRS"
# (verified against read_parquet); the registry QGIS plugin's own reader
# documents the PROJJSON form and maps its id to "OGC:CRS84".
CRS_AUTHORITY = "OGC:CRS84"

_SCHEMA_FIELDS: list[pa.Field] = [
    # The geometry column is a geoarrow.wkb extension type, not a plain
    # binary field with extension metadata. DuckDB 1.5 — the engine the
    # registry QGIS plugin reads through — refuses the latter:
    # "Geoparquet column 'geometry' does not have geometry types"
    # (verified against read_parquet). GeoParquet 1.1 permits the
    # extension type; geoarrow-pyarrow is the reference writer the
    # s2-stac-geoparquet catalog also builds on.
    pa.field("geometry", ga.wkb(), nullable=False),
    pa.field(
        COVERING_COLUMN,
        pa.struct(
            [
                pa.field("xmin", pa.float64(), nullable=False),
                pa.field("ymin", pa.float64(), nullable=False),
                pa.field("xmax", pa.float64(), nullable=False),
                pa.field("ymax", pa.float64(), nullable=False),
            ]
        ),
        nullable=False,
    ),
    pa.field("id", pa.string(), nullable=False),
    pa.field("title", pa.string(), nullable=False),
    pa.field("description", pa.string(), nullable=False),
    pa.field("license", pa.string(), nullable=False),
    pa.field("keywords", pa.list_(pa.string()), nullable=False),
    pa.field("tenant", pa.string(), nullable=True),
    pa.field("domain", pa.string(), nullable=True),
    pa.field("status", pa.string(), nullable=True),
    pa.field("contract_version", pa.string(), nullable=True),
    pa.field("primary_entity", pa.string(), nullable=True),
    pa.field("is_mirror", pa.bool_(), nullable=False),
    pa.field("updated", pa.string(), nullable=False),
    pa.field("via_url", pa.string(), nullable=True),
    pa.field("canonical_url", pa.string(), nullable=True),
    pa.field("self_url", pa.string(), nullable=True),
    pa.field("table_columns", pa.string(), nullable=True),
    pa.field("assets", pa.string(), nullable=False),
    pa.field("stac_extensions", pa.list_(pa.string()), nullable=False),
    pa.field("collection_url", pa.string(), nullable=False),
]

_TABLE_SCHEMA = pa.schema(_SCHEMA_FIELDS)


def crs_projjson() -> dict:
    """PROJJSON for OGC:CRS84, generated by PROJ rather than hardcoded."""
    return json.loads(pyproj.crs.CRS(CRS_AUTHORITY).to_json())


def geo_metadata() -> bytes:
    """The GeoParquet 2.0 `geo` metadata value (canonical JSON).

    Empirical consumer contract, verified against DuckDB 1.5.6 + spatial
    (the engine the registry QGIS plugin reads through) and grounded in the
    plugin's own reader:

    - version "2.0.0" plus `geometry_types` on the column, or DuckDB
      rejects the file with "does not have geometry types";
    - the CRS as PROJJSON with its OGC id, or DuckDB rejects it with
      "invalid CRS"; the plugin maps the id to "OGC:CRS84";
    - the geometry column as a geoarrow.wkb Arrow extension type (see
      _SCHEMA_FIELDS), not a plain binary field.
    """
    return canonicaljson.encode_canonical_json(
        {
            "version": GEO_VERSION,
            "primary_column": GEOMETRY_COLUMN,
            "columns": {
                GEOMETRY_COLUMN: {
                    "encoding": "WKB",
                    "geometry_types": GEOMETRY_TYPES,
                    "crs": crs_projjson(),
                    "covering": {
                        "bbox": {
                            "xmin": [COVERING_COLUMN, "xmin"],
                            "ymin": [COVERING_COLUMN, "ymin"],
                            "xmax": [COVERING_COLUMN, "xmax"],
                            "ymax": [COVERING_COLUMN, "ymax"],
                        }
                    },
                }
            },
        }
    )


def wkb_polygon(bbox: list[float]) -> bytes:
    """WKB for the axis-aligned polygon of a [xmin, ymin, xmax, ymax] bbox.

    One ring, five points, little-endian, geometry type 3 (Polygon).
    Hand-rolled so the builder needs no geometry stack; the validator
    parses it back with struct the same way.
    """
    xmin, ymin, xmax, ymax = (float(v) for v in bbox)
    ring = [
        (xmin, ymin),
        (xmax, ymin),
        (xmax, ymax),
        (xmin, ymax),
        (xmin, ymin),
    ]
    parts = [struct.pack("<BI", 1, 3), struct.pack("<I", 1), struct.pack("<I", len(ring))]
    parts.extend(struct.pack("<dd", x, y) for x, y in ring)
    return b"".join(parts)


def _link(collection: dict, rel: str) -> str | None:
    for link in collection.get("links", []):
        if link.get("rel") == rel:
            return link.get("href")
    return None


def _text(collection: dict, key: str) -> str | None:
    value = collection.get(key)
    return value if isinstance(value, str) else None


def row_for(collection: dict, collection_url: str) -> dict[str, object]:
    """One row from one generated collection. Plan §3 is the schema."""
    boxes = collection.get("extent", {}).get("spatial", {}).get("bbox", [])
    if not boxes or not isinstance(boxes[0], list) or len(boxes[0]) != 4:
        raise ValueError(f"{collection_url}: no 4-number bbox in extent.spatial.bbox")
    bbox = boxes[0]
    return {
        "geometry": wkb_polygon(bbox),
        "bbox": {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3]},
        "id": collection["id"],
        "title": collection["title"],
        "description": collection["description"],
        "license": collection["license"],
        "keywords": collection.get("keywords", []),
        "tenant": _text(collection, "geocontract:tenant"),
        "domain": _text(collection, "geocontract:domain"),
        "status": _text(collection, "geocontract:status"),
        "contract_version": _text(collection, "geocontract:contract_version"),
        "primary_entity": _text(collection, "geocontract:primary_entity"),
        "is_mirror": bool(collection.get("geocontract:mirror", False)),
        "updated": collection["updated"],
        "via_url": _link(collection, "via"),
        "canonical_url": _link(collection, "canonical"),
        "self_url": _link(collection, "self"),
        "table_columns": canonicaljson.encode_canonical_json(collection["table:columns"])
        if "table:columns" in collection
        else None,
        "assets": canonicaljson.encode_canonical_json(collection.get("assets", {})),
        "stac_extensions": collection.get("stac_extensions", []),
        "collection_url": collection_url,
    }


def load_rows_from(catalog_dir: Path, root: Path | None = None) -> list[dict[str, object]]:
    """Every generated collection under catalog_dir as a row, sorted by id.

    `root` anchors the relative collection_url recorded in each row: paths
    under it stay relative, anything else falls back to a posix path. The
    tracked build passes the repo root; the harvester sink passes its own
    out dir (plan §5 PR B).
    """
    anchor = root if root is not None else ROOT
    rows: list[dict[str, object]] = []
    for path in sorted(catalog_dir.rglob("collection.json")):
        collection = json.loads(path.read_text())
        try:
            url = path.relative_to(anchor).as_posix()
        except ValueError:
            url = path.as_posix()
        rows.append(row_for(collection, url))
    rows.sort(key=lambda row: str(row["id"]))
    ids = [str(row["id"]) for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate collection ids in {catalog_dir}: {sorted(ids)}")
    return rows


def load_rows() -> list[dict[str, object]]:
    """Rows for the tracked catalog tree, the build-geoparquet default."""
    return load_rows_from(CATALOG_DIR)


def build_table(rows: list[dict[str, object]]) -> pa.Table:
    schema = _TABLE_SCHEMA.with_metadata({b"geo": geo_metadata()})
    columns: dict[str, pa.Array] = {
        "geometry": ga.array([row["geometry"] for row in rows], type=ga.wkb())
    }
    for field in _SCHEMA_FIELDS[1:]:
        columns[field.name] = pa.array(
            [row[field.name] for row in rows], type=field.type
        )
    return pa.Table.from_pydict(columns, schema=schema)


def write_table(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", write_statistics=True)


def _parse_wkb_polygon(blob: bytes) -> list[tuple[float, float]]:
    """Inverse of wkb_polygon: [(x, y) ...] of the single ring."""
    offset = 0

    def take(fmt: str) -> tuple[object, ...]:
        nonlocal offset
        values = struct.unpack_from(fmt, blob, offset)
        offset += struct.calcsize(fmt)
        return values

    (byte_order,) = take("<B")
    if byte_order != 1:
        raise ValueError("expected little-endian WKB")
    (geom_type,) = take("<I")
    if geom_type != 3:
        raise ValueError(f"expected Polygon (type 3), got {geom_type}")
    (num_rings,) = take("<I")
    if num_rings != 1:
        raise ValueError(f"expected 1 ring, got {num_rings}")
    (num_points,) = take("<I")
    points = [take("<dd") for _ in range(num_points)]
    if offset != len(blob):
        raise ValueError("trailing bytes after ring")
    return points


def validate_against(path: Path, catalog_dir: Path, root: Path | None = None) -> list[str]:
    """Assert the written file against a source tree. Empty list = pass."""
    anchor = root if root is not None else ROOT
    errors: list[str] = []
    collections: dict[str, dict] = {}
    for source in sorted(catalog_dir.rglob("collection.json")):
        try:
            url = source.relative_to(anchor).as_posix()
        except ValueError:
            url = source.as_posix()
        collections[url] = json.loads(source.read_text())

    table = pq.read_table(path)
    meta = table.schema.metadata or {}
    if b"geo" not in meta:
        return [f"{path}: no `geo` metadata key in the schema"]
    geo = json.loads(meta[b"geo"])
    if geo.get("version") != GEO_VERSION:
        errors.append(f"{path}: geo.version {geo.get('version')!r} != {GEO_VERSION!r}")
    if geo.get("primary_column") != GEOMETRY_COLUMN:
        errors.append(f"{path}: primary_column {geo.get('primary_column')!r} != geometry")
    column = geo.get("columns", {}).get(GEOMETRY_COLUMN, {})
    if column.get("encoding") != "WKB":
        errors.append(f"{path}: geometry encoding {column.get('encoding')!r} != 'WKB'")
    if column.get("geometry_types") != GEOMETRY_TYPES:
        errors.append(
            f"{path}: geometry_types {column.get('geometry_types')!r} != {GEOMETRY_TYPES!r}"
        )
    crs = column.get("crs")
    crs_id = crs.get("id") if isinstance(crs, dict) else None
    if not (isinstance(crs_id, dict) and crs_id.get("authority") == "OGC" and crs_id.get("code") == "CRS84"):
        errors.append(f"{path}: crs is not the OGC:CRS84 PROJJSON the builder emits")
    if column.get("covering", {}).get("bbox") != {
        "xmin": [COVERING_COLUMN, "xmin"],
        "ymin": [COVERING_COLUMN, "ymin"],
        "xmax": [COVERING_COLUMN, "xmax"],
        "ymax": [COVERING_COLUMN, "ymax"],
    }:
        errors.append(f"{path}: covering declaration missing or malformed")

    data = table.to_pylist()
    if len(data) != len(collections):
        errors.append(f"{path}: {len(data)} rows != {len(collections)} collections")
    if [row["id"] for row in data] != sorted(row["id"] for row in data):
        errors.append(f"{path}: rows are not sorted by id")
    seen: set[str] = set()
    for row in data:
        cid = row["id"]
        seen.add(row["collection_url"])
        collection = collections.get(row["collection_url"])
        if collection is None:
            errors.append(f"{path}: row {cid} cites unknown source {row['collection_url']}")
            continue
        bbox = collection["extent"]["spatial"]["bbox"][0]
        expected = {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3]}
        if row["bbox"] != expected:
            errors.append(f"{path}: row {cid} covering {row['bbox']} != source {expected}")
        points = _parse_wkb_polygon(row["geometry"])
        ring = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3]), (bbox[0], bbox[1])]
        if points != ring:
            errors.append(f"{path}: row {cid} geometry does not round-trip to the source bbox")
        if collection.get("license") != row["license"]:
            errors.append(f"{path}: row {cid} license drift vs source")
    missing = set(collections) - seen
    if missing:
        errors.append(f"{path}: collections missing from the file: {sorted(missing)}")
    return errors


def validate(path: Path) -> list[str]:
    """Validate against the tracked catalog tree, the default gate."""
    return validate_against(path, CATALOG_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="skip the build; validate the existing output file against the tree",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help=f"output path (default: {OUT_PATH})",
    )
    args = parser.parse_args(argv)

    if not args.validate_only:
        rows = load_rows()
        write_table(build_table(rows), args.out)
        print(f"{args.out}: wrote {len(rows)} rows")

    errors = validate(args.out)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"{args.out}: validated against {CATALOG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
