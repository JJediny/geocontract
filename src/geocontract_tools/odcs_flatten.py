"""ODCS-flatten projection of the v2 canonical Proposal model.

Per plan §3.6, the ODCS contract is a flattened projection of the
nested-JSON canonical model. This module is the inverse direction:
given a canonical Proposal, produce the ODCS-flatten row.

The mapping is a fixed table (§3.6 in the plan). It is the inverse
of the ODCS contract's `physicalName` annotations; each row's
`physicalName` is `<table>.<json-pointer-from-proposal-root>` and
this module uses exactly that mapping.

Restricted fields (applicant.*, proof.*, raw parcel.geometry) are
**not** emitted by the public projection. Use ``projection="restricted"``
to emit them (for authorised consumers).
"""

from __future__ import annotations

from typing import Any, Literal

# Each row: (canonical_path, odcs_column_name)
PUBLIC_MAPPING: tuple[tuple[str, str], ...] = (
    ("id", "id"),
    ("schemaVersion", "schemaVersion"),
    ("createdAt", "createdAt"),
    ("parcel.jurisdiction", "jurisdiction"),
    ("parcel.parcelAuthority", "parcelAuthority"),
    ("parcel.authoritativeParcelId", "parcelId"),
    ("parcel.authorityRecordVersion", "authorityRecordVersion"),
    ("parcel.authorityRetrievedAt", "authorityRetrievedAt"),
    ("parcel.geometryFormat", "geometryFormat"),
    ("parcel.crs", "crs"),
    ("parcel.snapshotHash", "snapshotHash"),
    ("parcel.ownershipStatus", "parcelOwnershipStatus"),
    ("parcel.address", "address"),
    ("activity.code", "activityCode"),
    ("activity.preferredLabel", "activityPreferredLabel"),
    ("purpose", "purpose"),
    ("estimatedCostUsd", "estimatedCostUsd"),
    ("lifecycle.state", "lifecycleState"),
    ("lifecycle.decisionIssuer", "decisionIssuer"),
    ("lifecycle.decisionAt", "decisionAt"),
    ("lifecycle.decisionEvidence", "decisionEvidence"),
    ("lifecycle.supersedes", "supersedes"),
    ("lifecycle.revokedAt", "revokedAt"),
    ("anchorReceipt.contentHash", "anchorContentHash"),
    ("anchorReceipt.submissionId", "anchorSubmissionId"),
    ("anchorReceipt.anchoredAt", "anchorAnchoredAt"),
    ("anchorReceipt.serviceRef", "anchorServiceRef"),
)

RESTRICTED_EXTRA: tuple[tuple[str, str], ...] = (
    ("applicant.displayName", "applicantDisplayName"),
    ("applicant.contactEmail", "applicantContactEmail"),
    ("applicant.residencyProof.kind", "applicantResidencyKind"),
    ("applicant.residencyProof.credentialRef", "applicantResidencyCredentialRef"),
    ("applicant.residencyProof.issuerDid", "applicantResidencyIssuerDid"),
    ("applicant.residencyProof.validUntil", "applicantResidencyValidUntil"),
    ("applicant.authorityProof.kind", "applicantAuthorityKind"),
    ("applicant.authorityProof.credentialRef", "applicantAuthorityCredentialRef"),
    ("parcel.geometry", "geometry"),
    ("proof.signedDigest", "proofSignedDigest"),
    ("proof.hashAlgorithm", "proofHashAlgorithm"),
    ("proof.signatureAlgorithm", "proofSignatureAlgorithm"),
    ("proof.signingKey", "proofSigningKey"),
    ("proof.signature", "proofSignature"),
    ("proof.signedAt", "proofSignedAt"),
    ("proof.domain", "proofDomain"),
    ("proof.nonce", "proofNonce"),
    ("proof.keyId", "proofKeyId"),
)


def _resolve(proposal: dict[str, Any], dotted: str) -> Any:
    """Walk a dotted path against a proposal dict."""
    cur: Any = proposal
    for part in dotted.split("."):
        if cur is None or not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def flatten(
    proposal: dict[str, Any],
    *,
    projection: Literal["public", "restricted"] = "public",
) -> dict[str, Any]:
    """Flatten a canonical Proposal into the ODCS-row representation.

    Returns a dict keyed by the ODCS column names. Restricted fields
    are included iff ``projection='restricted'``.
    """
    mapping = PUBLIC_MAPPING + (RESTRICTED_EXTRA if projection == "restricted" else ())
    row: dict[str, Any] = {}
    for canonical_path, odcs_column in mapping:
        row[odcs_column] = _resolve(proposal, canonical_path)
    return row


def unflatten(
    row: dict[str, Any],
    *,
    projection: Literal["public", "restricted"] = "public",
) -> dict[str, Any]:
    """Inverse of ``flatten``: given an ODCS row, rebuild the canonical model.

    Used by the round-trip test in tests/test_odcs_flatten.py.
    """
    mapping = PUBLIC_MAPPING + (RESTRICTED_EXTRA if projection == "restricted" else ())

    # Reverse the mapping: odcs column -> canonical dotted path.
    reverse: dict[str, str] = {col: path for path, col in mapping}

    proposal: dict[str, Any] = {}
    for col, val in row.items():
        if col not in reverse:
            # Unrecognised column; preserve at top level for diagnostic.
            proposal[col] = val
            continue
        parts = reverse[col].split(".")
        cur = proposal
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = val
    return proposal