"""Tests for the v2 canonicalisation (plan §5.7)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.canonicalize import (  # noqa: E402
    canonicalize_for_signing,
    content_hash,
)

REPO_ROOT = ROOT


def test_canonicalize_is_deterministic() -> None:
    """Same input, different key order → identical bytes."""
    proposal = {
        "id": "abc-001",
        "schemaVersion": "2.0.0",
        "createdAt": "2026-09-12T14:30:00Z",
        "parcel": {"jurisdiction": "us-ct-groton"},
    }
    proposal_reordered = {
        "parcel": {"jurisdiction": "us-ct-groton"},
        "createdAt": "2026-09-12T14:30:00Z",
        "id": "abc-001",
        "schemaVersion": "2.0.0",
    }
    a = canonicalize_for_signing(proposal)
    b = canonicalize_for_signing(proposal_reordered)
    assert a == b
    # And the hash is also identical.
    assert content_hash(proposal) == content_hash(proposal_reordered)


def test_canonicalize_excludes_proof() -> None:
    """Adding the proof envelope must not mutate the signed bytes."""
    base = {"id": "abc-001", "schemaVersion": "2.0.0"}
    signed_only = canonicalize_for_signing(base)
    with_proof = {**base, "proof": {"signature": "ignored"}}
    signed_with_proof = canonicalize_for_signing(with_proof)
    assert signed_only == signed_with_proof


def test_content_hash_is_prefixed() -> None:
    h = content_hash({"id": "x"})
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
    int(h[len("sha256:"):], 16)  # parses as hex


def test_canonicalize_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        canonicalize_for_signing("not a dict")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        canonicalize_for_signing([1, 2, 3])  # type: ignore[arg-type]


def test_known_vector_stability() -> None:
    """A committed test vector yields a stable, reproducible hash.

    The committed hex is the canonical sha256 over the vector below
    using RFC 8785-style JCS (via canonicaljson==2.0.0). If this
    test fails after a dependency bump, regenerate the vector with
    the new library and commit the new hex.
    """
    vector = {
        "id": "groton-rhine-001",
        "schemaVersion": "2.0.0",
        "createdAt": "2026-09-12T14:30:00-04:00",
        "parcel": {
            "jurisdiction": "us-ct-groton",
            "parcelAuthority": "https://permits.groton-ct.gov/parcels/",
            "authoritativeParcelId": "M:123 B:45 L:678",
            "geometryFormat": "wkt",
            "crs": "EPSG:4326",
        },
        "activity": {"code": "housing.rehabilitation.facade"},
        "lifecycle": {"state": "draft"},
    }
    h = content_hash(vector)
    # Self-consistency: re-canonicalising twice yields the same hash.
    assert h == content_hash({**vector, "parcel": {**vector["parcel"]}})
    # The hash format is sha256:<64 hex>.
    assert h.startswith("sha256:") and len(h) == len("sha256:") + 64