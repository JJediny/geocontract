"""Tests for geocontract_tools.validate_odcs and the canonical contract files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable when running pytest without `uv sync`.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.validate_odcs import (  # noqa: E402
    load_dcat_us_schema,
    load_master_schema,
    load_odcs_schema,
    validate_dcat_us_json,
    validate_embedded_schemas,
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
    "contracts/examples/full-coverage.datacontract.yaml",
]

# The dcat-us-catalog contract uses `embeddedSchemas`, which only the
# geocontract master schema (ODCS v3.1.0 + embeddedSchemas) accepts.
# It is validated against the master schema, not bare ODCS.
MASTER_CONTRACT_FILES = CONTRACT_FILES + [
    "contracts/dcat-us-catalog.datacontract.yaml",
]

SHIM_FILES = [
    "contracts/shim/nepa-exclusions.datacontract-shim.json",
    "contracts/shim/pic-standards.datacontract-shim.json",
    "contracts/shim/dcat-us-catalog.datacontract-shim.json",
]


@pytest.mark.parametrize("relpath", CONTRACT_FILES)
def test_contract_validates(relpath: str) -> None:
    schema = load_odcs_schema()
    path = REPO_ROOT / relpath
    errors = validate_odcs_yaml(path, schema)
    assert errors == [], f"{relpath} failed validation:\n" + "\n".join(errors)


def test_full_coverage_exercises_every_top_level_key() -> None:
    """Regression sentinel: the full-coverage example must touch every
    top-level ODCS v3.1.0 key. If someone drops a section, this fails."""
    import yaml

    path = REPO_ROOT / "contracts/examples/full-coverage.datacontract.yaml"
    doc = yaml.safe_load(path.read_text())

    # The full set of optional-but-supported ODCS v3.1.0 top-level keys.
    # The required keys (version, apiVersion, kind, id, status) are already
    # guaranteed by the validator; we check the optionals here.
    expected_optional = {
        "tenant", "tags", "servers", "dataProduct", "description",
        "domain", "schema", "support", "price", "team", "roles",
        "slaDefaultElement", "slaProperties", "authoritativeDefinitions",
        "customProperties", "contractCreatedTs",
    }
    missing = expected_optional - set(doc.keys())
    assert not missing, f"full-coverage example missing top-level keys: {missing}"


def test_full_coverage_exercises_every_support_tool() -> None:
    """All seven ODCS SupportItem.tool enum values should appear."""
    import yaml

    path = REPO_ROOT / "contracts/examples/full-coverage.datacontract.yaml"
    doc = yaml.safe_load(path.read_text())
    tools = {s.get("tool") for s in doc.get("support", [])}
    expected = {"email", "slack", "teams", "discord", "ticket", "googlechat", "other"}
    missing = expected - tools
    assert not missing, f"support tools not covered: {missing}"


def test_full_coverage_exercises_every_quality_type() -> None:
    """library, sql, custom, text — each must appear at least once."""
    import yaml

    path = REPO_ROOT / "contracts/examples/full-coverage.datacontract.yaml"
    doc = yaml.safe_load(path.read_text())

    found = set()
    for obj in doc.get("schema", []):
        for k in ("quality",):
            for q in obj.get(k, []):
                if "type" in q:
                    found.add(q["type"])
        for prop in obj.get("properties", []):
            for q in prop.get("quality", []):
                if "type" in q:
                    found.add(q["type"])
    expected = {"library", "sql", "custom", "text"}
    missing = expected - found
    assert not missing, f"quality types not covered: {missing}"


def test_full_coverage_exercises_every_logical_type() -> None:
    """string, integer, number, boolean, date, timestamp, time, object, array."""
    import yaml

    path = REPO_ROOT / "contracts/examples/full-coverage.datacontract.yaml"
    doc = yaml.safe_load(path.read_text())

    found = set()
    for obj in doc.get("schema", []):
        if obj.get("logicalType"):
            found.add(obj["logicalType"])
        for prop in obj.get("properties", []):
            if prop.get("logicalType"):
                found.add(prop["logicalType"])
    expected = {"string", "integer", "number", "boolean", "date", "timestamp", "time", "object", "array"}
    missing = expected - found
    assert not missing, f"logicalType values not covered: {missing}"


def test_full_coverage_exercises_every_server_type() -> None:
    """api, local, postgres, kafka, s3, snowflake, bigquery, redshift,
    athena, glue, custom — each at least one server entry."""
    import yaml

    path = REPO_ROOT / "contracts/examples/full-coverage.datacontract.yaml"
    doc = yaml.safe_load(path.read_text())
    types = {s.get("type") for s in doc.get("servers", [])}
    expected = {
        "api", "local", "postgres", "kafka", "s3", "snowflake",
        "bigquery", "redshift", "athena", "glue", "custom",
    }
    missing = expected - types
    assert not missing, f"server types not covered: {missing}"


@pytest.mark.parametrize("relpath", SHIM_FILES)
def test_shim_validates(relpath: str) -> None:
    path = REPO_ROOT / relpath
    errors = validate_shim_json(path)
    assert errors == [], f"{relpath} failed validation:\n" + "\n".join(errors)


# ── geocontract master schema (ODCS + embeddedSchemas) ─────────────────────────


@pytest.mark.parametrize("relpath", MASTER_CONTRACT_FILES)
def test_contract_validates_master(relpath: str) -> None:
    """Every contract must validate against the geocontract master schema.
    The master schema is a strict superset of bare ODCS, so the bare-ODCS
    contracts pass too — this is the backwards-compatibility sentinel."""
    schema = load_master_schema()
    path = REPO_ROOT / relpath
    errors = validate_odcs_yaml(path, schema)
    assert errors == [], f"{relpath} failed master-schema validation:\n" + "\n".join(errors)
    # The human-readable embedded-schema checks must also pass.
    import yaml
    doc = yaml.safe_load(path.read_text())
    assert validate_embedded_schemas(doc) == []


def test_dcat_contract_rejected_by_bare_odcs() -> None:
    """Sentinel: bare ODCS (additionalProperties: false) must reject the
    embeddedSchemas block — this is the reason the master schema exists."""
    schema = load_odcs_schema()
    path = REPO_ROOT / "contracts/dcat-us-catalog.datacontract.yaml"
    errors = validate_odcs_yaml(path, schema)
    assert any("embeddedSchemas" in e for e in errors), (
        "bare ODCS should reject embeddedSchemas; master schema is required"
    )


def test_master_schema_has_embedded_schemas_property() -> None:
    """The master schema must define embeddedSchemas and use
    unevaluatedProperties (not additionalProperties) so it composes."""
    schema = load_master_schema()
    assert "embeddedSchemas" in schema["properties"]
    assert schema.get("unevaluatedProperties") is False
    assert "additionalProperties" not in schema  # swapped out by the generator


def test_embedded_schemas_rejects_non_schema_value() -> None:
    """validate_embedded_schemas flags a value that is a data instance,
    not a JSON Schema (no type/$ref/properties/…)."""
    bad = {"embeddedSchemas": {"mySchema": {"foo": "bar", "baz": 1}}}
    assert validate_embedded_schemas(bad) != []


def test_embedded_schemas_accepts_ref_and_inline() -> None:
    """Both $ref and inline (type+properties) embedded schemas are accepted."""
    good = {
        "embeddedSchemas": {
            "byRef": {"$ref": "external/dcat-us-catalog.json"},
            "inline": {"type": "object", "properties": {"x": {"type": "string"}}},
        }
    }
    assert validate_embedded_schemas(good) == []


# ── DCAT-US Catalog instance validation ─────────────────────────────────────────


def test_dcat_us_example_instance_validates() -> None:
    """The worked DCAT-US Catalog example must validate against the pinned
    GSA DCAT-US 3.0.0 schema (with the vendored sub-definition registry)."""
    from geocontract_tools.validate_odcs import _dcat_us_registry
    schema = load_dcat_us_schema()
    registry = _dcat_us_registry()
    path = REPO_ROOT / "examples/dcat-us-catalog.example.data.json"
    errors = validate_dcat_us_json(path, schema, registry=registry)
    assert errors == [], "dcat-us example failed validation:\n" + "\n".join(errors)


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
