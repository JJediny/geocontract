"""Generate the activity SKOS ontology from the curated JSON catalog.

The JSON catalog is the source of truth. The Turtle file is a deterministic
projection for RDF/OWL tooling and must not be edited by hand.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from geocontract_tools.validate_ontology import ActivityOntology, OntologyError

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = ROOT / "ontology" / "activity-concept-catalog.v1.0.json"
TURTLE_PATH = CATALOG_PATH.with_suffix(".ttl")
ONTOLOGY_IRI = "https://geocontract.dev/ontology/activity-concept-catalog"
CONCEPT_BASE = "https://geocontract.dev/ontology/activity/"
SCHEME_IRI = "gc:activity-concept-catalog"

PREFIXES = """@prefix gc: <https://geocontract.dev/ontology/activity-concept-catalog#> .
@prefix gca: <https://geocontract.dev/ontology/activity/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def concept_reference(code: str) -> str:
    """Return the stable, version-independent RDF reference for a code."""
    return f"gca:{code}"


def literal(value: str, datatype: str | None = None) -> str:
    """Encode a JSON string as a Turtle literal."""
    encoded = json.dumps(value, ensure_ascii=False)
    return f"{encoded}^^{datatype}" if datatype else encoded


def iri_reference(value: str) -> str:
    """Encode an absolute URI as a Turtle IRIREF without allowing injection."""
    forbidden = any(ord(char) <= 0x20 or ord(char) == 0x7F or char in '<>"{}|^`\\' for char in value)
    try:
        absolute = bool(urlsplit(value).scheme)
    except ValueError as exc:
        raise OntologyError(f"invalid source citation IRI: {value!r}") from exc
    if not value or forbidden or not absolute:
        raise OntologyError(f"invalid source citation IRI: {value!r}")
    return f"<{value}>"


def render_catalog(catalog: dict[str, Any]) -> str:
    """Render one curated catalog as a deterministic SKOS/Turtle document."""
    concepts = sorted(catalog["concepts"], key=lambda concept: concept["code"])
    top_concepts = [concept for concept in concepts if not concept.get("broader", [])]
    lines = [
        PREFIXES.rstrip(),
        "",
        f"<{ONTOLOGY_IRI}> a owl:Ontology ;",
        '    rdfs:label "Geocontract activity concept ontology" ;',
        f"    rdfs:comment {literal(catalog['description'])} ;",
        f"    dcterms:issued {literal(catalog['publishedAt'], 'xsd:date')} ;",
        f"    dcterms:publisher {literal(catalog['publisher'])} ;",
        f"    owl:versionInfo {literal(catalog['version'])} .",
        "",
        "gc:ActivityConcept a owl:Class ;",
        '    rdfs:label "Activity concept" ;',
        '    rdfs:comment "A descriptive activity term that a proposal may reference. Membership does not grant regulatory approval." .',
        "",
        "gc:activityCode a owl:DatatypeProperty ;",
        '    rdfs:label "activity code" ;',
        '    rdfs:comment "The stable dotted code used by proposal.activity.code." ;',
        "    rdfs:domain gc:ActivityConcept ;",
        "    rdfs:range xsd:string .",
        "",
        "gc:jurisdictionCode a owl:DatatypeProperty ;",
        '    rdfs:label "jurisdiction code" ;',
        '    rdfs:comment "An optional jurisdictional scope for a concept." ;',
        "    rdfs:domain gc:ActivityConcept ;",
        "    rdfs:range xsd:string .",
        "",
        "gc:lifecycleStatus a owl:DatatypeProperty ;",
        '    rdfs:label "lifecycle status" ;',
        '    rdfs:comment "The curation state of this concept, independent of any proposal or permit decision." ;',
        "    rdfs:domain gc:ActivityConcept ;",
        "    rdfs:range xsd:string .",
        "",
        "gc:regulatoryStatus a owl:DatatypeProperty ;",
        '    rdfs:label "regulatory status" ;',
        '    rdfs:comment "A description of vocabulary status only. It never asserts approval, exemption, or endorsement." ;',
        "    rdfs:domain gc:ActivityConcept ;",
        "    rdfs:range xsd:string .",
        "",
        "gc:deprecatedAfter a owl:DatatypeProperty ;",
        '    rdfs:label "deprecated after" ;',
        '    rdfs:comment "The first date on which the concept is not valid for new proposals." ;',
        "    rdfs:domain gc:ActivityConcept ;",
        "    rdfs:range xsd:date .",
        "",
        f"{SCHEME_IRI} a skos:ConceptScheme ;",
        '    rdfs:label "Geocontract activity concept catalog" ;',
        f"    rdfs:comment {literal(catalog['description'])} ;",
        f"    dcterms:issued {literal(catalog['publishedAt'], 'xsd:date')} ;",
        f"    dcterms:publisher {literal(catalog['publisher'])} ;",
        f"    owl:versionInfo {literal(catalog['version'])}",
    ]
    if top_concepts:
        lines[-1] += " ;"
        lines.append("    skos:hasTopConcept " + ", ".join(concept_reference(c["code"]) for c in top_concepts) + " .")
    else:
        lines[-1] += " ."

    for concept in concepts:
        code = concept["code"]
        lines.extend(
            [
                "",
                f"{concept_reference(code)} a gc:ActivityConcept, skos:Concept ;",
                f"    skos:inScheme {SCHEME_IRI} ;",
                f"    gc:activityCode {literal(code)} ;",
                f"    skos:prefLabel {literal(concept['preferredLabel'])} ;",
                f"    skos:definition {literal(concept['definition'])} ;",
                f"    gc:lifecycleStatus {literal(concept['lifecycleStatus'])} ;",
                f"    gc:regulatoryStatus {literal(concept['regulatoryStatus'])} ;",
            ]
        )
        for alias in sorted(concept.get("aliases", [])):
            lines.append(f"    skos:altLabel {literal(alias)} ;")
        if concept.get("jurisdiction") is not None:
            lines.append(f"    gc:jurisdictionCode {literal(concept['jurisdiction'])} ;")
        if concept.get("sourceCitation") is not None:
            lines.append(f"    dcterms:source {iri_reference(concept['sourceCitation'])} ;")
        if concept.get("deprecatedAfter") is not None:
            lines.append(f"    gc:deprecatedAfter {literal(concept['deprecatedAfter'], 'xsd:date')} ;")
        if concept.get("broader"):
            lines.append("    skos:broader " + ", ".join(concept_reference(ref) for ref in sorted(concept["broader"])) + " ;")
        if concept.get("narrower"):
            lines.append("    skos:narrower " + ", ".join(concept_reference(ref) for ref in sorted(concept["narrower"])) + " ;")
        if not concept.get("broader"):
            lines.append(f"    skos:topConceptOf {SCHEME_IRI} ;")
        lines[-1] = lines[-1][:-2] + " ."

    return "\n".join(lines) + "\n"


def build(catalog_path: Path = CATALOG_PATH) -> str:
    """Validate and render a catalog without writing it."""
    ActivityOntology.load(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return render_catalog(catalog)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed Turtle differs from the source")
    args = parser.parse_args()
    expected = build()
    if args.check:
        if not TURTLE_PATH.exists() or TURTLE_PATH.read_text(encoding="utf-8") != expected:
            print(f"ERROR {TURTLE_PATH.relative_to(ROOT)} is stale; run 'mise run ontology-build'")
            return 1
        print(f"OK   {TURTLE_PATH.relative_to(ROOT)} matches {CATALOG_PATH.relative_to(ROOT)}")
        return 0
    TURTLE_PATH.write_text(expected, encoding="utf-8")
    print(f"OK   wrote {TURTLE_PATH.relative_to(ROOT)} ({len(expected.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
