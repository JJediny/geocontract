"""JSON-Schema validation tests for the v2 Proposal template."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

REPO_ROOT = ROOT
TEMPLATE_PATH = REPO_ROOT / "templates" / "proposed-action.template.schema.json"
EXAMPLE_PATH = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(TEMPLATE_PATH.read_text())


@pytest.fixture(scope="module")
def example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())


def test_worked_example_validates(schema: dict, example: dict) -> None:
    """The committed example must validate against the committed template."""
    Draft202012Validator(schema).validate(example)


def test_unknown_activity_code_rejected(schema: dict, example: dict) -> None:
    """JSON Schema regex passes for `not.in.ontology`, but ontology membership rejects.

    Per plan §4.3: activity code membership is enforced by the
    ActivityOntology validator, not by the JSON Schema regex. This
    test asserts the layered enforcement.
    """
    import sys
    from pathlib import Path as _P

    sys.path.insert(0, str(_P(__file__).resolve().parent.parent.parent / "src"))
    from geocontract_tools.validate_ontology import ActivityOntology, OntologyError

    bad = json.loads(json.dumps(example))
    bad["proposal"]["activity"]["code"] = "not.in.ontology"
    # JSON Schema accepts (regex passes), but the ontology rejects.
    Draft202012Validator(schema).validate(bad)
    ont = ActivityOntology.load(REPO_ROOT / "ontology" / "activity-concept-catalog.v1.0.json")
    with pytest.raises(OntologyError):
        ont.validate_code("not.in.ontology")


def test_unknown_property_rejected_at_root(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["surprise"] = "field"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_lifecycle_state_enum_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["lifecycle"]["state"] = "made-up-state"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_geometry_without_crs_rejected(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    del bad["proposal"]["parcel"]["crs"]
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_proof_signature_algorithm_pinned(schema: dict, example: dict) -> None:
    """Only Ed25519 is accepted in the v2 core."""
    bad = json.loads(json.dumps(example))
    bad["proposal"]["proof"] = {
        "signedDigest": "sha256:" + "0" * 64,
        "hashAlgorithm": "sha-256",
        "signatureAlgorithm": "secp256k1",  # NOT ed25519
        "signingKey": "did:example:x",
        "signature": "base64:AAAA",
        "signedAt": "2026-09-12T00:00:00Z",
        "domain": "geocontract.test",
        "nonce": "base64:" + "A" * 16,
        "keyId": "k-1",
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_id_pattern_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["id"] = "UPPERCASE-AND_UNDERSCORE"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)


def test_jurisdiction_pattern_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["parcel"]["jurisdiction"] = "Groton, CT"
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(bad)