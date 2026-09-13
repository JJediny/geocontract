#!/usr/bin/env python3
"""Generate the full-coverage signed Proposal example.

Produces ``examples/groton-rhine-002.example.data.json`` (a second
worked example) with every supported field populated and a real
Ed25519 detached proof envelope attached. The signature is over
RFC 8785-style JCS of the proposal with ``proof`` excluded.

The example uses a documented TEST KEYPAIR (the private-key bytes
are committed to the repo and tagged "TEST ONLY" — anyone can
re-derive the public key and verify the signature). Production
citizens must use their own keys.

Run::

    uv run python scripts/build_signed_example.py

The output is byte-reproducible: re-running with no edits produces
byte-identical files because:

- The proposal body uses no ``fetched_at`` / ``now()`` calls (only
  the fixed ``2026-09-12T14:30:00-04:00`` timestamp).
- The Ed25519 keypair is the fixed 32-byte seed below.
- The ``signedAt`` timestamp in the proof envelope IS regenerated
  each run, but the signature is over the canonicalised proposal
  body WITHOUT the proof, so the signature is stable.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Make src/ importable when run from a checkout without `uv sync`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.canonicalize import canonicalize_for_signing  # noqa: E402
from geocontract_tools.validate_ontology import ActivityOntology  # noqa: E402

# ── TEST KEYPAIR (deterministic seed; documented in repo) ────────────────
# Private-key seed bytes. Hex: 0101010101…01 (32 bytes).
# Public key (derived): 8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c
# DID:key (Ed25519 multibase): did:key:z7QGKiOPddAnxlf1S2y08ul1yymcJvx2UEhvzdIgBtA9vXA
#
# ⚠ TEST ONLY. Never use this keypair in production.
TEST_PRIV_SEED = b"\x01" * 32
TEST_PUB_HEX = "8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c"
TEST_DID = "did:key:z7QGKiOPddAnxlf1S2y08ul1yymcJvx2UEhvzdIgBtA9vXA"

OUTPUT_PATH = ROOT / "examples" / "groton-rhine-002.example.data.json"


def _b64(b: bytes) -> str:
    return "base64:" + base64.b64encode(b).decode("ascii")


def _build_proposal_body() -> dict:
    """Build the full-coverage Proposal body (no proof yet)."""
    now = "2026-09-12T14:30:00-04:00"  # FIXED for reproducibility
    return {
        "id": "groton-rhine-002",
        "schemaVersion": "2.0.0",
        "createdAt": now,
        # ── Applicant — RESTRICTED ───────────────────────────────────
        "applicant": {
            "displayName": "Jane Groton-Resident",
            "contactEmail": "jane@example.invalid",
            "residencyProof": {
                "kind": "municipal_vc",
                "credentialRef": "ipfs://bafy...groton-residency-vc",
                "issuerDid": TEST_DID,  # re-use the test DID for the issuer placeholder
                "validUntil": "2027-12-31",
            },
            "authorityProof": {
                "kind": "owner",
                "credentialRef": "town-clerk-deed-2026-08-15",
            },
        },
        # ── Parcel — typed reference (plan §5.9) ────────────────────
        "parcel": {
            "jurisdiction": "us-ct-groton",
            "parcelAuthority": "https://permits.groton-ct.gov/parcels/",
            "authoritativeParcelId": "M:124 B:45 L:679",
            "authorityRecordVersion": "2026-09-01",
            "authorityRetrievedAt": now,
            "geometryFormat": "wkt",
            "crs": "EPSG:4326",
            "geometry": (
                "POLYGON((-72.0821 41.3473, -72.0819 41.3473, "
                "-72.0819 41.3475, -72.0821 41.3475, -72.0821 41.3473))"
            ),
            "snapshotHash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
            "ownershipStatus": "owner_verified",
            "address": "44 Rhine Street, Groton, CT 06340",
        },
        # ── Activity — ontology code (plan §4.3) ────────────────────
        "activity": {
            "code": "housing.rehabilitation.facade.repointing",
            "preferredLabel": "Mortar repointing",
        },
        # ── Free-text purpose + cost ─────────────────────────────────
        "purpose": (
            "Repoint the east elevation's failed mortar joints. "
            "Approximately 220 linear feet of joints; lime-based "
            "mortar matching the original 1920s spec. No structural "
            "work; no colour change; no alteration of window openings."
        ),
        "estimatedCostUsd": 18500.00,
        # ── Lifecycle FSM (plan §3.4) — submitted, awaiting review ──
        "lifecycle": {
            "state": "submitted",
            "decisionIssuer": None,
            "decisionAt": None,
            "decisionEvidence": None,
            "supersedes": None,
            "revokedAt": None,
        },
        # ── Revisions — empty for first revision ─────────────────────
        "revisions": [],
        # ── Anchor receipt — none yet (optional, plan §3.4) ──────────
        "anchorReceipt": None,
        # ── Proof — populated below ───────────────────────────────────
        "proof": None,
    }


def _attach_proof(proposal: dict) -> dict:
    """Sign the proposal and attach the detached proof envelope."""
    priv = Ed25519PrivateKey.from_private_bytes(TEST_PRIV_SEED)
    pub = priv.public_key().public_bytes_raw()
    assert pub.hex() == TEST_PUB_HEX, "test keypair drift"

    payload = dict(proposal)
    payload.pop("proof", None)
    canonical = canonicalize_for_signing(payload)
    digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    signature = priv.sign(canonical)

    # `signedAt` is NOT part of the signed payload (the canonical
    # body excludes `proof` entirely). It is included in the
    # envelope for human readability.
    proposal["proof"] = {
        "signedDigest": digest,
        "hashAlgorithm": "sha-256",
        "signatureAlgorithm": "ed25519",
        "signingKey": TEST_DID,
        "signature": _b64(signature),
        "signedAt": "2026-09-12T14:30:00-04:00",  # FIXED for reproducibility
        "domain": "geocontract.example",
        "nonce": _b64(b"\x42" * 16),
        "keyId": "k-1",
    }
    return proposal


def _validate_ontology_membership(proposal: dict) -> None:
    """Ensure the example's activity.code is in the catalog."""
    ont = ActivityOntology.load(ROOT / "ontology" / "activity-concept-catalog.v1.0.json")
    row = ont.validate_code(proposal["activity"]["code"])
    print(f"  activity.code {proposal['activity']['code']!r} → catalog row OK")
    print(f"  preferredLabel: {row['preferredLabel']!r}")


def main() -> int:
    body = _build_proposal_body()
    print(f"Built proposal body: id={body['id']!r}")
    _validate_ontology_membership(body)
    body = _attach_proof(body)
    print(
        f"Attached detached proof envelope: "
        f"signature={body['proof']['signature'][:24]}..."
    )

    output = {
        "$schema": "https://geocontract.dev/schemas/proposed-action.template.schema.json",
        "proposal": body,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")
    print()
    print("Re-run anytime: uv run python scripts/build_signed_example.py")
    print()
    print(f"Test public key: {TEST_PUB_HEX}")
    print(f"Test DID:        {TEST_DID}")
    print("⚠  TEST ONLY — do not use in production.")
    return 0


if __name__ == "__main__":
    sys.exit(main())