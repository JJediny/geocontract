"""Tests for geocontract_tools.validate_odcs and the canonical contract files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable when running pytest without `uv sync`.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.validate_odcs import (  # noqa: E402
    load_odcs_schema,
    validate_odcs_yaml,
    validate_shim_json,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Schema loading ────────────────────────────────────────────────────────────

def test_odcs_schema_loads() -> None:
    schema = load_odcs_schema()
    assert schema["title"] == "Open Data Contract Standard (ODCS)"
    assert schema["properties"]["apiVersion"]["enum"][0] == "v3.1.0"


def test_odcs_schema_required_top_level() -> None:
    schema = load_odcs_schema()
    required = set(schema["required"])
    assert {"version", "apiVersion", "kind", "id", "status"} <= required


# ── Validator against the bundled, hand-authored contracts ────────────────────

CONTRACT_FILES = [
    "contracts/odcs-v3.1.0-template.yaml",
    "contracts/nepa-exclusions.datacontract.yaml",
    "contracts/pic-standards.datacontract.yaml",
]

SHIM_FILES = [
    "contracts/shim/nepa-exclusions.datacontract-shim.json",
    "contracts/shim/pic-standards.datacontract-shim.json",
]


@pytest.mark.parametrize("relpath", CONTRACT_FILES)
def test_contract_validates(relpath: str) -> None:
    schema = load_odcs_schema()
    path = REPO_ROOT / relpath
    errors = validate_odcs_yaml(path, schema)
    assert errors == [], f"{relpath} failed validation:\n" + "\n".join(errors)


@pytest.mark.parametrize("relpath", SHIM_FILES)
def test_shim_validates(relpath: str) -> None:
    path = REPO_ROOT / relpath
    errors = validate_shim_json(path)
    assert errors == [], f"{relpath} failed validation:\n" + "\n".join(errors)


# ── Negative tests (the validator must catch real mistakes) ───────────────────

def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("apiVersion: v3.1.0\nkind: NotDataContract\n")
    schema = load_odcs_schema()
    errors = validate_odcs_yaml(bad, schema)
    assert any("kind" in e for e in errors)


def test_rejects_missing_required_fields(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("apiVersion: v3.1.0\n")  # missing kind/id/status/version
    schema = load_odcs_schema()
    errors = validate_odcs_yaml(bad, schema)
    # ODCS v3.1.0 requires exactly these four top-level keys (plus apiVersion,
    # which we provided).
    fields = {"kind", "id", "status", "version"}
    flagged = {f for e in errors for f in fields if f in e}
    assert fields <= flagged, f"missing required fields not flagged: {fields - flagged}"


def test_rejects_invalid_logical_type(tmp_path: Path) -> None:
    """logicalType enum is enforced strictly by ODCS v3.1.0."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "apiVersion: v3.1.0\nkind: DataContract\nid: x\nname: x\nversion: 0.1.0\nstatus: draft\n"
        "schema:\n  - name: T\n    logicalType: object\n    properties:\n"
        "      - name: c\n        logicalType: decimal\n"  # invalid enum
    )
    schema = load_odcs_schema()
    errors = validate_odcs_yaml(bad, schema)
    assert any("logicalType" in e for e in errors)


def test_shim_rejects_missing_contract() -> None:
    errors = validate_shim_json(_shim_like({"version": "1.0"}))
    assert any("contract" in e for e in errors)


def test_shim_rejects_quality_without_metric() -> None:
    payload = {
        "version": "1.0",
        "contract": {"name": "x", "version": "1.0.0"},
        "quality": [{"threshold": 1.0}],  # missing metric
    }
    errors = validate_shim_json(_shim_like(payload))
    assert any("metric" in e for e in errors)


# Helper: allow passing a dict directly to validate_shim_json by wrapping in a
# synthetic file. We use this for the negative tests above.
def _shim_like(payload: dict) -> Path:
    import json
    import tempfile

    f = Path(tempfile.mkstemp(suffix=".json")[1])
    f.write_text(json.dumps(payload))
    return f
