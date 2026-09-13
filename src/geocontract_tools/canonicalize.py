"""RFC 8785-style JCS canonicalisation for geocontract Proposal documents.

The v2 core path requires that any proposal's detached signature be
over the canonicalised bytes of the proposal with `proof` excluded
(plan §5.7). We use the canonicaljson package, which is a Python
implementation of RFC 8785 (JCS — JSON Canonicalisation Scheme).

The canonicalisation rule is:

  bytes_to_sign = canonicaljson.encode_canonical_json(
      proposal_without_proof
  )

The signed payload therefore:

- excludes the `proof` envelope itself (so adding the proof does not
  mutate the signed bytes);
- uses RFC 8785's deterministic key ordering and number formatting;
- rejects NaN, Infinity, and non-JSON-serialisable values.

Test vectors are committed under scripts/tests/test_vectors/ and
exercised by tests/test_canonicalization.py.
"""

from __future__ import annotations

import hashlib
from typing import Any

import canonicaljson


def canonicalize_for_signing(proposal: dict[str, Any]) -> bytes:
    """Return the canonical bytes that should be signed.

    The input must be a dict; ``proposal.proof`` is stripped before
    canonicalisation so the signature does not self-reference.
    """
    if not isinstance(proposal, dict):
        raise TypeError(f"proposal must be a dict, got {type(proposal).__name__}")

    payload = dict(proposal)
    payload.pop("proof", None)
    return canonicaljson.encode_canonical_json(payload)


def content_hash(proposal: dict[str, Any]) -> str:
    """Return the canonical sha256 content hash as `sha256:<hex>`."""
    return "sha256:" + hashlib.sha256(canonicalize_for_signing(proposal)).hexdigest()