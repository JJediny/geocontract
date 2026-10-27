"""Tests for the ActivityConcept catalog membership validator."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.validate_ontology import (  # noqa: E402
    ActivityOntology,
    OntologyError,
)

REPO_ROOT = ROOT
CATALOG_PATH = REPO_ROOT / "ontology" / "activity-concept-catalog.v1.0.json"


@pytest.fixture(scope="module")
def ontology() -> ActivityOntology:
    return ActivityOntology.load(CATALOG_PATH)


def test_catalog_loads() -> None:
    ont = ActivityOntology.load(CATALOG_PATH)
    assert ont.version == "1.0.0"
    assert "housing.rehabilitation.facade" in ont.codes


def test_active_code_accepted(ontology: ActivityOntology) -> None:
    row = ontology.validate_code("housing.rehabilitation.facade")
    assert row["regulatoryStatus"] == "descriptive_only"


def test_unknown_code_rejected(ontology: ActivityOntology) -> None:
    with pytest.raises(OntologyError, match="not found"):
        ontology.validate_code("not.in.ontology")



def test_deprecated_code_rejected() -> None:
    """A row whose `deprecatedAfter` is in the past must be rejected."""
    # Build an in-memory catalog where one row has a past deprecatedAfter.
    import json
    import tempfile

    catalog = json.loads(CATALOG_PATH.read_text())
    catalog["concepts"] = list(catalog["concepts"]) + [
        {
            "code": "test.deprecated",
            "preferredLabel": "Deprecated test row",
            "definition": "x",
            "regulatoryStatus": "descriptive_only",
            "lifecycleStatus": "active",
            "deprecatedAfter": "2020-01-01",
        }
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(catalog, f)
        f.flush()
        # Copy the schema alongside for ActivityOntology.load.
        schema_src = CATALOG_PATH.with_name("activity-concept-catalog.schema.json")
        schema_dst = Path(f.name).with_name("activity-concept-catalog.schema.json")
        schema_dst.write_text(schema_src.read_text())
        try:
            ont = ActivityOntology.load(f.name)
            with pytest.raises(OntologyError, match="deprecated"):
                ont.validate_code("test.deprecated")
        finally:
            Path(f.name).unlink(missing_ok=True)
            schema_dst.unlink(missing_ok=True)


def test_broader_reference_resolves(ontology: ActivityOntology) -> None:
    """Every broader reference must point to a known code."""
    for c in ontology._by_code.values():  # noqa: SLF001 (test introspection)
        for ref in c.get("broader", []):
            assert ref in ontology._by_code, f"{c['code']} → {ref} unresolved"


def test_umbrella_codes_present(ontology: ActivityOntology) -> None:
    """v1.0 catalog has the umbrella rows used by the plan taxonomy."""
    assert "housing.rehabilitation" in ontology.codes
    assert "housing.new" in ontology.codes
    assert "civic.infrastructure" in ontology.codes
    assert "civic.event" in ontology.codes
    assert "landuse.zoning" in ontology.codes


def test_no_token_codes_in_core(ontology: ActivityOntology) -> None:
    """The v2 core catalog must not contain token / funding codes."""
    for code in ontology.codes:
        assert "token" not in code.lower()
        assert "fundrais" not in code.lower()
        assert "coin" not in code.lower()


def _load_rows(tmp_path: Path, rows: list[dict]) -> ActivityOntology:
    import json

    catalog = json.loads(CATALOG_PATH.read_text())
    catalog["concepts"] = rows
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    schema = CATALOG_PATH.with_name("activity-concept-catalog.schema.json")
    (tmp_path / schema.name).write_text(schema.read_text())
    return ActivityOntology.load(path)


def _row(code: str, *, broader: list[str] | None = None, narrower: list[str] | None = None, status: str = "active") -> dict:
    return {
        "code": code,
        "preferredLabel": code,
        "definition": f"Definition for {code}.",
        "broader": broader or [],
        "narrower": narrower or [],
        "regulatoryStatus": "descriptive_only",
        "lifecycleStatus": status,
    }


def test_duplicate_code_rejected(tmp_path: Path) -> None:
    import json

    rows = json.loads(CATALOG_PATH.read_text())["concepts"]
    with pytest.raises(OntologyError, match="duplicate"):
        _load_rows(tmp_path, rows + [rows[0]])


def test_non_active_broader_rejected(tmp_path: Path) -> None:
    rows = [
        _row("test.parent", narrower=["test.child"], status="retired"),
        _row("test.child", broader=["test.parent"]),
    ]
    with pytest.raises(OntologyError, match="non-active broader"):
        _load_rows(tmp_path, rows)


def test_asymmetric_hierarchy_rejected(tmp_path: Path) -> None:
    rows = [_row("test.parent"), _row("test.child", broader=["test.parent"])]
    with pytest.raises(OntologyError, match="missing from narrower"):
        _load_rows(tmp_path, rows)


def test_hierarchy_cycle_rejected(tmp_path: Path) -> None:
    rows = [
        _row("test.parent", broader=["test.child"], narrower=["test.child"]),
        _row("test.child", broader=["test.parent"], narrower=["test.parent"]),
    ]
    with pytest.raises(OntologyError, match="cycle"):
        _load_rows(tmp_path, rows)


def test_malformed_deprecation_date_rejected_at_load(tmp_path: Path) -> None:
    row = _row("test.child")
    row["deprecatedAfter"] = "not-a-date"
    with pytest.raises(ValidationError, match="deprecatedAfter"):
        _load_rows(tmp_path, [row])


def test_single_segment_code_rejected_at_load(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="code"):
        _load_rows(tmp_path, [_row("housing")])


def test_relative_source_citation_rejected_at_load(tmp_path: Path) -> None:
    row = _row("test.child")
    row["sourceCitation"] = "relative/path"
    with pytest.raises(ValidationError, match="sourceCitation"):
        _load_rows(tmp_path, [row])


@pytest.mark.parametrize("status", ["candidate", "retired", "superseded"])
def test_inactive_code_rejected(tmp_path: Path, status: str) -> None:
    ont = _load_rows(tmp_path, [_row("test.child", status=status)])
    with pytest.raises(OntologyError, match="not active"):
        ont.validate_code("test.child")


def test_deprecation_boundary_is_exclusive(tmp_path: Path) -> None:
    row = _row("test.child")
    row["deprecatedAfter"] = "2026-01-01"
    ont = _load_rows(tmp_path, [row])
    assert ont.validate_code("test.child", today=date(2025, 12, 31))["code"] == "test.child"
    with pytest.raises(OntologyError, match="deprecated"):
        ont.validate_code("test.child", today=date(2026, 1, 1))


def test_unresolved_narrower_rejected(tmp_path: Path) -> None:
    with pytest.raises(OntologyError, match="unresolved narrower"):
        _load_rows(tmp_path, [_row("test.parent", narrower=["test.missing"])])


def test_missing_broader_reciprocal_rejected(tmp_path: Path) -> None:
    rows = [_row("test.parent", narrower=["test.child"]), _row("test.child")]
    with pytest.raises(OntologyError, match="missing from broader"):
        _load_rows(tmp_path, rows)
