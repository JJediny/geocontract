"""Tests for the STAC-GeoParquet portfolio builder (issue #44, plan §5 PR A).

The tests read the tracked examples/geocontracts.geoparquet and rebuild it
into a tmp_path copy, so they prove both the tracked file is current and
the builder is deterministic — the same pattern as
test_graphql_reproducibility.py.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pyarrow.parquet as pq  # noqa: E402

from geocontract_tools import build_geoparquet as bg  # noqa: E402


def _tracked() -> Path:
    return ROOT / "examples" / "geocontracts.geoparquet"


def _collections() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((ROOT / "catalog").rglob("collection.json")):
        out[path.relative_to(ROOT).as_posix()] = json.loads(path.read_text())
    return out


def _read(path: Path) -> tuple[dict, list[dict]]:
    table = pq.read_table(path)
    meta = json.loads((table.schema.metadata or {})[b"geo"])
    return meta, table.to_pylist()


def test_tracked_file_exists_and_validates() -> None:
    """The committed portfolio file validates against the current tree."""
    errors = bg.validate(_tracked())
    assert errors == []


def test_row_count_and_ids_match_collections() -> None:
    _, rows = _read(_tracked())
    collections = _collections()
    assert len(rows) == len(collections)
    assert sorted(r["id"] for r in rows) == sorted(c["id"] for c in collections.values())


def test_bbox_round_trip_including_coarsened_citizen_bbox() -> None:
    """Every covering struct equals its source bbox; groton-rhine-001 proves
    the coarsened bbox survived, not the parcel-precise one (plan §2)."""
    _, rows = _read(_tracked())
    collections = _collections()
    by_url = {r["collection_url"]: r for r in rows}
    for url, collection in collections.items():
        bbox = collection["extent"]["spatial"]["bbox"][0]
        assert by_url[url]["bbox"] == {
            "xmin": bbox[0],
            "ymin": bbox[1],
            "xmax": bbox[2],
            "ymax": bbox[3],
        }
    citizen = by_url["catalog/citizen/groton-rhine-001/collection.json"]
    assert citizen["bbox"] == {"xmin": -72.09, "ymin": 41.34, "xmax": -72.08, "ymax": 41.35}


def test_geometry_round_trips_to_source_bbox() -> None:
    _, rows = _read(_tracked())
    collections = _collections()
    by_url = {r["collection_url"]: r for r in rows}
    for url, collection in collections.items():
        xmin, ymin, xmax, ymax = collection["extent"]["spatial"]["bbox"][0]
        ring = [
            (xmin, ymin),
            (xmax, ymin),
            (xmax, ymax),
            (xmin, ymax),
            (xmin, ymin),
        ]
        assert bg._parse_wkb_polygon(by_url[url]["geometry"]) == ring


def test_geo_metadata_shape() -> None:
    """GeoParquet 1.1, primary geometry, covering declaration, WKB (§4)."""
    geo, _ = _read(_tracked())
    assert geo["version"] == "1.1.0"
    assert geo["primary_column"] == "geometry"
    column = geo["columns"]["geometry"]
    assert column["encoding"] == "WKB"
    assert column["covering"]["bbox"] == {
        "xmin": ["bbox", "xmin"],
        "ymin": ["bbox", "ymin"],
        "xmax": ["bbox", "xmax"],
        "ymax": ["bbox", "ymax"],
    }


def test_crs_is_crs84_lon_lat() -> None:
    """The CRS must be OGC:CRS84 (lon/lat), not EPSG:4326 WKT2 (lat/lon)."""
    geo, _ = _read(_tracked())
    wkt = geo["columns"]["geometry"]["crs"]
    assert wkt == bg.crs_wkt2()
    assert '"CRS84"' in wkt
    assert wkt.startswith("GEODCRS") or wkt.startswith("GEOGCRS")


def test_rows_sorted_by_id() -> None:
    _, rows = _read(_tracked())
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)


def test_rebuild_into_tmp_is_byte_stable(tmp_path: Path) -> None:
    rows = bg.load_rows()
    out = tmp_path / "geocontracts.geoparquet"
    bg.write_table(bg.build_table(rows), out)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == hashlib.sha256(
        _tracked().read_bytes()
    ).hexdigest()


def test_validate_flags_stale_file(tmp_path: Path) -> None:
    """A file built from fewer rows must fail validation, not pass silently."""
    rows = bg.load_rows()
    bg.write_table(bg.build_table(rows[:-1]), tmp_path / "stale.geoparquet")
    errors = bg.validate(tmp_path / "stale.geoparquet")
    assert any("missing from the file" in e for e in errors)


def test_wkb_polygon_matches_hand_computed() -> None:
    blob = bg.wkb_polygon([-72.09, 41.34, -72.08, 41.35])
    assert blob[0] == 1  # little-endian
    assert int.from_bytes(blob[1:5], "little") == 3  # Polygon
    assert bg._parse_wkb_polygon(blob)[0] == (-72.09, 41.34)
    assert bg._parse_wkb_polygon(blob)[-1] == bg._parse_wkb_polygon(blob)[0]


def test_row_for_requires_bbox() -> None:
    with pytest.raises(ValueError, match="no 4-number bbox"):
        bg.row_for({"id": "x", "extent": {"spatial": {"bbox": [[]]}}}, "x.json")
