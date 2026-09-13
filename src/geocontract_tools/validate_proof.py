"""Detached proof envelope validator (plan §5.7).

The v2 core path uses a detached proof envelope with these required
fields:

  signedDigest          : "sha256:<hex>"          (over canonicalised bytes, excluding `proof`)
  hashAlgorithm         : "sha-256"
  signatureAlgorithm    : "ed25519"
  signingKey            : "did:<method>:<id>"     (DID, not raw wallet address)
  signature             : "base64:<...>"
  signedAt              : ISO 8601 with timezone
  domain                : string (replay protection / context)
  nonce                 : "base64:<...>"          (replay protection)
  keyId                 : string

The signature is verified against the canonicalised bytes of the
proposal with `proof` excluded. The DID is dereferenced via the
caller-provided DID-resolver hook; this module only performs the
local signature check once the public-key bytes have been resolved.

Usage:

    from geocontract_tools.validate_proof import verify_proof
    verify_proof(proposal)  # raises ProofInvalid on any failure

For test vectors, see scripts/tests/test_vectors/.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from geocontract_tools.canonicalize import canonicalize_for_signing


class ProofInvalid(ValueError):
    """Raised when a proposal's detached proof fails validation."""


# ── Required-field schema (re-declared here to keep this module
# self-contained for harvester use). The full JSON-Schema lives at
# templates/proposed-action.template.schema.json §$defs/Proof. ────
REQUIRED_FIELDS = (
    "signedDigest",
    "hashAlgorithm",
    "signatureAlgorithm",
    "signingKey",
    "signature",
    "signedAt",
    "domain",
    "nonce",
    "keyId",
)

ALLOWED_HASH_ALGS = {"sha-256"}
ALLOWED_SIG_ALGS = {"ed25519"}

DID_PATTERN = re.compile(r"^did:[a-z0-9]+:[A-Za-z0-9._:%-]+$")
KEYID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SHA256_PREFIXED = re.compile(r"^sha256:[a-f0-9]{64}$")
BASE64_PREFIXED = re.compile(r"^base64:[A-Za-z0-9+/=]+$")


def _strip_prefix(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        raise ProofInvalid(f"expected `{prefix}` prefix, got {value[:24]}…")
    return value[len(prefix) :]


def _decode_base64(value: str, *, field: str) -> bytes:
    stripped = _strip_prefix(value, "base64:")
    try:
        return base64.b64decode(stripped, validate=True)
    except Exception as exc:
        raise ProofInvalid(f"{field}: invalid base64 ({exc})") from exc


def resolve_public_key(signing_key: str, key_id: str) -> bytes:
    """Resolve a DID + keyId to raw Ed25519 public-key bytes.

    This is a stub. In production, the caller wires in a DID-resolver
    that dereferences `signing_key` and looks up `keyId` in the DID
    document. For tests, an in-memory resolver is supplied (see
    scripts/tests/test_validate_proof.py).
    """
    raise NotImplementedError(
        "Did resolver not wired in. Provide a resolver via "
        "validate_proof(..., did_resolver=...) for production use."
    )


def verify_proof(
    proposal: dict[str, Any],
    *,
    did_resolver: Callable[[str, str], bytes] | None = None,
    seen_nonces: set[str] | None = None,
) -> None:
    """Verify the detached proof on a proposal.

    Raises ``ProofInvalid`` on any failure (missing field, malformed
    field, signature mismatch, replay). Returns ``None`` on success.

    The default behaviour expects the caller to wire in a DID
    resolver via ``did_resolver``. For testing, the test module
    supplies an in-memory resolver.

    Replay protection: if ``seen_nonces`` is supplied, the nonce is
    added to the set and a second proposal with the same nonce
    raises ``ProofInvalid``. If the proposal's own `lifecycle.state`
    is `draft`, replay protection is not applied (a draft may be
    re-signed multiple times).
    """
    proof = proposal.get("proof")
    if proof is None:
        # Draft / walletless path: signature absence is allowed.
        return

    # ── Required fields ─────────────────────────────────────────────────
    missing = [f for f in REQUIRED_FIELDS if f not in proof]
    if missing:
        raise ProofInvalid(f"proof: missing required field(s): {missing}")

    # ── Algorithm pinning ───────────────────────────────────────────────
    if proof["hashAlgorithm"] not in ALLOWED_HASH_ALGS:
        raise ProofInvalid(
            f"proof.hashAlgorithm {proof['hashAlgorithm']!r} not allowed; "
            f"must be one of {sorted(ALLOWED_HASH_ALGS)}"
        )
    if proof["signatureAlgorithm"] not in ALLOWED_SIG_ALGS:
        raise ProofInvalid(
            f"proof.signatureAlgorithm {proof['signatureAlgorithm']!r} not allowed; "
            f"must be one of {sorted(ALLOWED_SIG_ALGS)}"
        )

    # ── Field formats ──────────────────────────────────────────────────
    if not SHA256_PREFIXED.match(proof["signedDigest"]):
        raise ProofInvalid(f"proof.signedDigest malformed: {proof['signedDigest']!r}")
    if not DID_PATTERN.match(proof["signingKey"]):
        raise ProofInvalid(f"proof.signingKey malformed: {proof['signingKey']!r}")
    if not KEYID_PATTERN.match(proof["keyId"]):
        raise ProofInvalid(f"proof.keyId malformed: {proof['keyId']!r}")
    if not BASE64_PREFIXED.match(proof["signature"]):
        raise ProofInvalid(f"proof.signature malformed: {proof['signature'][:32]}")
    if not BASE64_PREFIXED.match(proof["nonce"]):
        raise ProofInvalid(f"proof.nonce malformed: {proof['nonce'][:32]}")

    # ── Replay protection ──────────────────────────────────────────────
    lifecycle_state = (proposal.get("lifecycle") or {}).get("state")
    if seen_nonces is not None and lifecycle_state != "draft":
        nonce = proof["nonce"]
        if nonce in seen_nonces:
            raise ProofInvalid(f"proof.nonce replay detected: {nonce[:24]}…")
        seen_nonces.add(nonce)

    # ── Signature verification ────────────────────────────────────────
    expected_digest = "sha256:" + __import__("hashlib").sha256(
        canonicalize_for_signing(proposal)
    ).hexdigest()
    if proof["signedDigest"] != expected_digest:
        raise ProofInvalid(
            f"proof.signedDigest mismatch: proof claims {proof['signedDigest']!r}, "
            f"recomputed {expected_digest!r}"
        )

    resolver = did_resolver or resolve_public_key
    public_key_bytes = resolver(proof["signingKey"], proof["keyId"])
    signature_bytes = _decode_base64(proof["signature"], field="proof.signature")

    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            canonicalize_for_signing(proposal),
        )
    except InvalidSignature as exc:
        raise ProofInvalid(f"Ed25519 signature failed verification: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ProofInvalid(f"Ed25519 verification error: {exc}") from exc