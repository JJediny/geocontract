"""RFC 8785-style JCS canonicalisation for geocontract Proposal documents.

The v2 core path requires a deterministic content hash and detached
signature for each proposal (plan §5.7). The content hash excludes the
proof envelope; the signature additionally covers the protected proof
context. We use the canonicaljson package, which is a Python
implementation of RFC 8785 (JCS — JSON Canonicalisation Scheme).

The canonicalisation rules are:

  content_bytes = canonicaljson.encode_canonical_json(
      proposal_without_proof
  )

  proof_bytes = canonicaljson.encode_canonical_json(
      proposal_without_signature_and_digest
  )

The content hash excludes the complete `proof` envelope. The detached
signature instead covers the proposal body plus the proof context
(`hashAlgorithm`, `signatureAlgorithm`, `signingKey`, `signedAt`,
`domain`, `nonce`, and `keyId`), excluding only the self-referential
`signedDigest` and `signature` fields. This binds replay and domain
metadata to the signature without creating a circular input.

Both forms use RFC 8785's deterministic key ordering and number
formatting and reject NaN, Infinity, and non-JSON-serialisable values.

Test vectors are committed under scripts/tests/test_vectors/ and
exercised by tests/test_canonicalization.py.
"""

from __future__ import annotations

import hashlib
from typing import Any

import canonicaljson


PROTECTED_PROOF_FIELDS = (
    "hashAlgorithm",
    "signatureAlgorithm",
    "signingKey",
    "signedAt",
    "domain",
    "nonce",
    "keyId",
)


def canonicalize_for_signing(proposal: dict[str, Any]) -> bytes:
    """Return canonical content bytes with the complete proof removed.

    These bytes are used for the content digest. Detached signatures
    should use :func:`canonicalize_proof_input` so protected proof
    metadata is bound to the signature as well.
    """
    if not isinstance(proposal, dict):
        raise TypeError(f"proposal must be a dict, got {type(proposal).__name__}")

    payload = dict(proposal)
    payload.pop("proof", None)
    return canonicaljson.encode_canonical_json(payload)


def canonicalize_proof_input(proposal: dict[str, Any]) -> bytes:
    """Return canonical bytes covered by the detached signature.

    The proof's ``signedDigest`` and ``signature`` are excluded because
    they are derived from, or contain, the signature input. The remaining
    proof context is included so a verifier cannot alter the signer,
    domain, nonce, or key identifier without invalidating the signature.
    """
    if not isinstance(proposal, dict):
        raise TypeError(f"proposal must be a dict, got {type(proposal).__name__}")
    proof = proposal.get("proof")
    if not isinstance(proof, dict):
        raise TypeError("proposal.proof must be an object when signing a proof")

    payload = dict(proposal)
    payload["proof"] = {
        field: proof[field]
        for field in PROTECTED_PROOF_FIELDS
        if field in proof
    }
    return canonicaljson.encode_canonical_json(payload)


def content_hash(proposal: dict[str, Any]) -> str:
    """Return the canonical sha256 content hash as `sha256:<hex>`."""
    return "sha256:" + hashlib.sha256(canonicalize_for_signing(proposal)).hexdigest()
