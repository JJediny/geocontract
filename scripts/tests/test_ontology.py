"""Tests for the ActivityConcept catalog membership validator."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

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


def test_underscore_does_not_match_dot_pattern(ontology: ActivityOntology) -> None:
    """A single-segment code with no dots must be rejected."""
    with pytest.raises(OntologyError):
        ontology.validate_code("housing")


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