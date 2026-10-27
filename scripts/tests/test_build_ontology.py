"""Tests for the deterministic JSON-to-SKOS activity ontology projection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.build_ontology import (  # noqa: E402
    CATALOG_PATH,
    TURTLE_PATH,
    build,
    concept_reference,
    iri_reference,
    literal,
)
from geocontract_tools.validate_ontology import OntologyError  # noqa: E402


def test_committed_turtle_matches_catalog() -> None:
    assert TURTLE_PATH.read_text(encoding="utf-8") == build()


def test_every_catalog_row_has_an_rdf_projection() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    turtle = build()
    for concept in catalog["concepts"]:
        assert f"{concept_reference(concept['code'])} a gc:ActivityConcept, skos:Concept ;" in turtle
        assert f"gc:activityCode {literal(concept['code'])}" in turtle
        assert f"skos:prefLabel {literal(concept['preferredLabel'])}" in turtle
        assert f"gc:regulatoryStatus {literal(concept['regulatoryStatus'])}" in turtle


def test_projection_is_deterministic() -> None:
    assert build() == build()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "relative/path",
        "https://example.com/ ends in whitespace",
        "https://example.com/> <https://evil.example/>",
    ],
)
def test_invalid_source_citations_cannot_inject_turtle(value: str) -> None:
    with pytest.raises(OntologyError, match="source citation"):
        iri_reference(value)


def test_valid_source_citation_is_wrapped_as_an_iri() -> None:
    assert iri_reference("https://example.com/source") == "<https://example.com/source>"
