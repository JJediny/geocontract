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

The content digest is computed over the canonicalised proposal with
`proof` excluded. The signature covers the proposal body plus the
protected proof context, excluding only `signedDigest` and `signature`.
The DID is dereferenced via the caller-provided DID-resolver hook; this
module only performs the local signature check once the public-key bytes
have been resolved.

Usage:

    from geocontract_tools.validate_proof import verify_proof
    verify_proof(proposal)  # raises ProofInvalid on any failure

For test vectors, see scripts/tests/test_vectors/.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import re
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from geocontract_tools.canonicalize import (
    canonicalize_proof_input,
    canonicalize_for_signing,
)


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
    if not isinstance(value, str):
        raise ProofInvalid(f"{field} malformed: expected a string")
    try:
        stripped = _strip_prefix(value, "base64:")
    except ProofInvalid as exc:
        raise ProofInvalid(f"{field} malformed: {exc}") from exc
    try:
        return base64.b64decode(stripped, validate=True)
    except Exception as exc:
        raise ProofInvalid(f"{field}: invalid base64 ({exc})") from exc


def _required_string(proof: dict[str, Any], field: str) -> str:
    value = proof.get(field)
    if not isinstance(value, str):
        raise ProofInvalid(f"proof.{field}: expected a string")
    return value


def _validate_timestamp(value: str, *, field: str) -> None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProofInvalid(f"proof.{field}: invalid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProofInvalid(f"proof.{field}: timestamp must include a timezone")


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

    Replay protection: if ``seen_nonces`` is supplied, a non-draft
    nonce is checked before verification and recorded only after the
    signature succeeds. If the proposal's own ``lifecycle.state`` is
    ``draft``, replay protection is not applied.
    """
    if not isinstance(proposal, dict):
        raise ProofInvalid(f"proposal: expected an object, got {type(proposal).__name__}")

    proof = proposal.get("proof")
    if proof is None:
        # Draft / walletless path: signature absence is allowed.
        return
    if not isinstance(proof, dict):
        raise ProofInvalid("proof: expected an object or null")

    # ── Required fields ─────────────────────────────────────────────────
    missing = [field for field in REQUIRED_FIELDS if field not in proof]
    if missing:
        raise ProofInvalid(f"proof: missing required field(s): {missing}")

    hash_algorithm = _required_string(proof, "hashAlgorithm")
    signature_algorithm = _required_string(proof, "signatureAlgorithm")
    signed_digest = _required_string(proof, "signedDigest")
    signing_key = _required_string(proof, "signingKey")
    signature = _required_string(proof, "signature")
    signed_at = _required_string(proof, "signedAt")
    domain = _required_string(proof, "domain")
    nonce_value = _required_string(proof, "nonce")
    key_id = _required_string(proof, "keyId")

    # ── Algorithm pinning ───────────────────────────────────────────────
    if hash_algorithm not in ALLOWED_HASH_ALGS:
        raise ProofInvalid(
            f"proof.hashAlgorithm {hash_algorithm!r} not allowed; "
            f"must be one of {sorted(ALLOWED_HASH_ALGS)}"
        )
    if signature_algorithm not in ALLOWED_SIG_ALGS:
        raise ProofInvalid(
            f"proof.signatureAlgorithm {signature_algorithm!r} not allowed; "
            f"must be one of {sorted(ALLOWED_SIG_ALGS)}"
        )

    # ── Field formats ──────────────────────────────────────────────────
    if not SHA256_PREFIXED.fullmatch(signed_digest):
        raise ProofInvalid(f"proof.signedDigest malformed: {signed_digest!r}")
    if not DID_PATTERN.fullmatch(signing_key):
        raise ProofInvalid(f"proof.signingKey malformed: {signing_key!r}")
    if not KEYID_PATTERN.fullmatch(key_id):
        raise ProofInvalid(f"proof.keyId malformed: {key_id!r}")
    if not domain or len(domain) > 253:
        raise ProofInvalid("proof.domain must contain 1–253 characters")
    _validate_timestamp(signed_at, field="signedAt")

    signature_bytes = _decode_base64(signature, field="proof.signature")
    if len(signature_bytes) != 64:
        raise ProofInvalid("proof.signature must decode to 64 bytes for Ed25519")
    nonce_bytes = _decode_base64(nonce_value, field="proof.nonce")
    if len(nonce_bytes) < 8:
        raise ProofInvalid("proof.nonce must decode to at least 8 bytes")

    # ── Replay protection ──────────────────────────────────────────────
    lifecycle_state = (proposal.get("lifecycle") or {}).get("state")
    replay_protected = seen_nonces is not None and lifecycle_state != "draft"
    if replay_protected and nonce_value in seen_nonces:
        raise ProofInvalid(f"proof.nonce replay detected: {nonce_value[:24]}…")

    # ── Signature verification ────────────────────────────────────────
    canonical = canonicalize_for_signing(proposal)
    expected_digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if signed_digest != expected_digest:
        raise ProofInvalid(
            f"proof.signedDigest mismatch: proof claims {signed_digest!r}, "
            f"recomputed {expected_digest!r}"
        )

    resolver = did_resolver or resolve_public_key
    try:
        public_key_bytes = resolver(signing_key, key_id)
    except ProofInvalid:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProofInvalid(f"DID resolver failed: {exc}") from exc
    if not isinstance(public_key_bytes, bytes):
        raise ProofInvalid("DID resolver must return raw public-key bytes")

    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            canonicalize_proof_input(proposal),
        )
    except InvalidSignature as exc:
        raise ProofInvalid(f"Ed25519 signature failed verification: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ProofInvalid(f"Ed25519 verification error: {exc}") from exc

    # Do not consume a nonce until all validation, key resolution, and
    # signature checks have succeeded. Otherwise an attacker can poison
    # a caller's replay cache with an invalid proof.
    if replay_protected:
        seen_nonces.add(nonce_value)
