"""Tests for the DataCite v4.3 validator and record generator (issue #21)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.validate_odcs import (  # noqa: E402
    load_datacite_43_schema,
    validate_datacite_43_json,
)

RECORDS_DIR = ROOT / "examples" / "datacite4.3"


def _record_files() -> list[Path]:
    files = sorted(RECORDS_DIR.glob("*.json"))
    assert files, "generated records are missing; run mise run build-datacite"
    return files


def test_generated_records_validate() -> None:
    """Every generated record must pass the vendored 4.3 schema."""
    schema = load_datacite_43_schema()
    for f in _record_files():
        assert validate_datacite_43_json(f, schema) == [], f"{f} failed validation"


def test_missing_required_field_fails() -> None:
    schema = load_datacite_43_schema()
    doc = json.loads(_record_files()[0].read_text())
    del doc["titles"]
    bad = ROOT / ".pytest_cache" / "datacite-negative.json"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text(json.dumps(doc))
    try:
        errors = validate_datacite_43_json(bad, schema)
        assert any("titles" in e for e in errors)
    finally:
        bad.unlink()


def test_bad_funder_identifier_type_fails() -> None:
    """Enums hold: 'WALLET' is not a funderIdentifierType (issue #21)."""
    schema = load_datacite_43_schema()
    doc = json.loads(_record_files()[0].read_text())
    doc["fundingReferences"] = [
        {"funderName": "Open Grants DAO", "funderIdentifierType": "WALLET"}
    ]
    bad = ROOT / ".pytest_cache" / "datacite-negative2.json"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text(json.dumps(doc))
    try:
        errors = validate_datacite_43_json(bad, schema)
        assert any("funderIdentifierType" in e for e in errors)
    finally:
        bad.unlink()


def test_unknown_top_level_rejected() -> None:
    """additionalProperties:false: junk keys cannot ride along."""
    schema = load_datacite_43_schema()
    doc = json.loads(_record_files()[0].read_text())
    doc["onChainReceipt"] = {"tx": "0x…"}
    bad = ROOT / ".pytest_cache" / "datacite-negative3.json"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text(json.dumps(doc))
    try:
        errors = validate_datacite_43_json(bad, schema)
        assert any("onChainReceipt" in e for e in errors)
    finally:
        bad.unlink()


def test_malformed_publication_year_fails() -> None:
    """The custom 'year' format is enforced, not skipped."""
    schema = load_datacite_43_schema()
    doc = json.loads(_record_files()[0].read_text())
    doc["publicationYear"] = "20X6"
    bad = ROOT / ".pytest_cache" / "datacite-negative4.json"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text(json.dumps(doc))
    try:
        errors = validate_datacite_43_json(bad, schema)
        assert any("publicationYear" in e for e in errors)
    finally:
        bad.unlink()


def test_citizen_record_geo_is_coarsened() -> None:
    """The citizen record's geo box is the coarsened parcel bbox, never the raw parcel."""
    maybe = RECORDS_DIR / "groton-rhine-001.json"
    doc = json.loads(maybe.read_text())
    box = doc["geoLocations"][0]["geoLocationBox"]
    for value in box.values():
        assert abs(float(value) * 100 - round(float(value) * 100)) < 1e-6
