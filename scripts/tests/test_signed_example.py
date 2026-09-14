"""Tests for the full-coverage signed Proposal example.

Verifies that ``examples/groton-rhine-002.example.data.json``:

- validates against the JSON Schema template
- has every required Proposal field populated
- carries a real, verifiable Ed25519 detached proof envelope
- the signedDigest matches a fresh canonicalisation
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.canonicalize import canonicalize_for_signing  # noqa: E402
from geocontract_tools.validate_proof import verify_proof  # noqa: E402
from geocontract_tools._schema_validation import make_format_checker  # noqa: E402

FORMAT_CHECKER = make_format_checker()

TEMPLATE = ROOT / "templates" / "proposed-action.template.schema.json"
EXAMPLE = ROOT / "examples" / "groton-rhine-002.example.data.json"
YAML_EXAMPLE = ROOT / "examples" / "groton-rhine-002.example.data.yaml"

TEST_PRIV_SEED = b"\x01" * 32
TEST_PUB_HEX = "8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c"
# Derive the W3C did:key for the test pubkey (multicodec 0xed 0x01 + base58btc).
# Matched against scripts/build_signed_example.py:TEST_DID.
try:
    import base58  # noqa: PLC0415
except ImportError:  # base58 is a build-time-only dep; tests should
                     # run with the default install too.
    TEST_DID = None  # type: ignore[assignment]
else:
    _priv = Ed25519PrivateKey.from_private_bytes(TEST_PRIV_SEED)
    _pub = _priv.public_key().public_bytes_raw()
    assert _pub.hex() == TEST_PUB_HEX, "test keypair drift"
    TEST_DID = "did:key:z" + base58.b58encode(b"\xed\x01" + _pub).decode("ascii")


def _resolver_for_test_did(did: str, key_id: str) -> bytes:
    if did != TEST_DID or key_id != "k-1":
        raise ValueError("unknown test key")
    priv = Ed25519PrivateKey.from_private_bytes(TEST_PRIV_SEED)
    return priv.public_key().public_bytes_raw()


@pytest.fixture(scope="module")
def example() -> dict:
    return json.loads(EXAMPLE.read_text())


def test_example_validates_against_schema(example: dict) -> None:
    schema = json.loads(TEMPLATE.read_text())
    Draft202012Validator(schema, format_checker=FORMAT_CHECKER).validate(example)


def test_example_is_full_coverage(example: dict) -> None:
    """The example populates every top-level Proposal field."""
    proposal = example["proposal"]
    # Identity
    for key in ("id", "schemaVersion", "createdAt"):
        assert proposal[key], f"{key} must be populated"
    # Applicant — restricted sub-tree is fully populated.
    applicant = proposal["applicant"]
    assert applicant["displayName"]
    assert applicant["contactEmail"]
    assert applicant["residencyProof"]["kind"]
    assert applicant["authorityProof"]["kind"]
    # Parcel — every documented §5.9 field populated.
    parcel = proposal["parcel"]
    for key in (
        "jurisdiction",
        "parcelAuthority",
        "authoritativeParcelId",
        "authorityRecordVersion",
        "authorityRetrievedAt",
        "geometryFormat",
        "crs",
        "geometry",
        "snapshotHash",
        "ownershipStatus",
        "address",
    ):
        assert parcel[key], f"parcel.{key} must be populated"
    # Activity — ontology code AND preferredLabel.
    assert proposal["activity"]["code"]
    assert proposal["activity"]["preferredLabel"]
    # Purpose + cost
    assert proposal["purpose"]
    assert proposal["estimatedCostUsd"] is not None
    # Lifecycle — non-draft state to demonstrate FSM
    assert proposal["lifecycle"]["state"] != "draft"


def test_example_proof_envelope_is_complete(example: dict) -> None:
    proof = example["proposal"]["proof"]
    assert proof is not None
    for key in (
        "signedDigest",
        "hashAlgorithm",
        "signatureAlgorithm",
        "signingKey",
        "signature",
        "signedAt",
        "domain",
        "nonce",
        "keyId",
    ):
        assert proof[key], f"proof.{key} must be populated"


def test_example_uses_test_did(example: dict) -> None:
    proof = example["proposal"]["proof"]
    assert proof["signingKey"] == TEST_DID


def test_example_signed_digest_matches_recomputed(example: dict) -> None:
    proposal = example["proposal"]
    expected = "sha256:" + hashlib.sha256(canonicalize_for_signing(proposal)).hexdigest()
    assert proposal["proof"]["signedDigest"] == expected


def test_yaml_companion_matches_json(example: dict) -> None:
    assert YAML_EXAMPLE.exists()
    assert yaml.safe_load(YAML_EXAMPLE.read_text()) == example


def test_example_signature_verifies_with_test_pubkey(example: dict) -> None:
    """End-to-end: the proof verifies with the documented test pubkey."""
    proposal = example["proposal"]
    verify_proof(proposal, did_resolver=_resolver_for_test_did)


def test_example_signature_breaks_when_proposal_is_mutated(example: dict) -> None:
    """A single-byte change to a signed field must invalidate the signature."""
    proposal = json.loads(json.dumps(example["proposal"]))  # deep copy
    proposal["purpose"] = proposal["purpose"] + "."
    with pytest.raises(Exception):  # ProofInvalid
        verify_proof(proposal, did_resolver=_resolver_for_test_did)


def test_example_is_byte_reproducible() -> None:
    """Regenerating the JSON and YAML examples produces identical bytes."""
    import subprocess  # noqa: PLC0415

    before_json = EXAMPLE.read_bytes()
    before_yaml = YAML_EXAMPLE.read_bytes()
    subprocess.run(
        ["mise", "run", "build-signed-example"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert EXAMPLE.read_bytes() == before_json
    assert YAML_EXAMPLE.read_bytes() == before_yaml


def test_example_public_projection_drops_applicant_and_proof(example: dict) -> None:
    """The public projection strips the restricted subtrees."""
    from geocontract_tools.public_projection import public_projection  # noqa: PLC0415

    public = public_projection(example["proposal"])
    assert "applicant" not in public
    assert "proof" not in public
    assert "geometry" not in public["parcel"]
    # Public fields preserved.
    assert public["id"] == example["proposal"]["id"]
    assert public["parcel"]["jurisdiction"] == example["proposal"]["parcel"]["jurisdiction"]


def test_example_uses_active_ontology_code(example: dict) -> None:
    from geocontract_tools.validate_ontology import ActivityOntology  # noqa: PLC0415

    ont = ActivityOntology.load(ROOT / "ontology" / "activity-concept-catalog.v1.0.json")
    row = ont.validate_code(example["proposal"]["activity"]["code"])
    assert row["lifecycleStatus"] == "active"
    assert row["regulatoryStatus"] == "descriptive_only"