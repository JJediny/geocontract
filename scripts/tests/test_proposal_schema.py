"""JSON-Schema validation tests for the v2 Proposal template."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools._schema_validation import make_format_checker  # noqa: E402

FORMAT_CHECKER = make_format_checker()

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
    Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(example)


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
    Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)
    ont = ActivityOntology.load(REPO_ROOT / "ontology" / "activity-concept-catalog.v1.0.json")
    with pytest.raises(OntologyError):
        ont.validate_code("not.in.ontology")


def test_unknown_property_rejected_at_root(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["surprise"] = "field"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_lifecycle_state_enum_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["lifecycle"]["state"] = "made-up-state"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_geometry_without_crs_rejected(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    del bad["proposal"]["parcel"]["crs"]
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


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
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_id_pattern_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["id"] = "UPPERCASE-AND_UNDERSCORE"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_jurisdiction_pattern_enforced(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["parcel"]["jurisdiction"] = "Groton, CT"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)

# ── format enforcement (Q12 follow-up) ───────────────────────────────────────
# The Draft 2020-12 default format_checker is intentionally narrow and
# does NOT cover `date-time` or `uri`. _schema_validation.make_format_checker
# extends the default checker to enforce both. These tests pin the
# extension so a jsonschema upgrade that drops the custom checks will
# fail loudly.


def test_date_time_format_rejects_naive_timestamp(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["createdAt"] = "2026-09-12T14:30:00"  # no timezone
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_date_time_format_accepts_z_suffix(schema: dict, example: dict) -> None:
    ok = json.loads(json.dumps(example))
    ok["proposal"]["createdAt"] = "2026-09-12T14:30:00Z"
    Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(ok)


def test_uri_format_rejects_bare_path(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["parcel"]["parcelAuthority"] = "/relative/path"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_email_format_rejects_non_email(schema: dict, example: dict) -> None:
    bad = json.loads(json.dumps(example))
    bad["proposal"]["applicant"]["contactEmail"] = "not-an-email"
    with pytest.raises(Exception):
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(bad)


def test_null_values_skip_format_check(schema: dict, example: dict) -> None:
    """`type: ["null", "string"]` with `format: date-time` must accept null.

    The format check is a no-op on non-strings; the type validator
    already accepts null. This pins the behaviour so a future change
    to the custom checkers does not start rejecting null fields.
    """
    Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(example)
    # The example has several `null` values for date-time fields;
    # they must remain valid.
    assert example["proposal"]["lifecycle"]["decisionAt"] is None
    assert example["proposal"]["lifecycle"]["revokedAt"] is None
