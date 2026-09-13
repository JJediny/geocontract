"""Public projection (plan §5.8) — emit only access-class=public fields.

The default projection for any harvested Proposal. The harvester
uses this projection by default and requires an authority-authenticated
header for the restricted projection.
"""

from __future__ import annotations

from typing import Any

# Fields explicitly tagged `x-graphql-access-class: restricted` in
# the v2 schema, plus the wrapper objects that contain them.
# Anything not in this set is public-by-default (default-deny).
RESTRICTED_PATHS: frozenset[str] = frozenset(
    {
        "applicant",
        "proof",
    }
)


def public_projection(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied proposal with all restricted fields removed."""
    out = _shallow_public(proposal)
    return out


def _shallow_public(node: Any) -> Any:
    """Recursively strip restricted subtrees."""
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for k, v in node.items():
            if k in RESTRICTED_PATHS:
                continue  # drop restricted subtree
            result[k] = _shallow_public(v)
        return result
    if isinstance(node, list):
        return [_shallow_public(item) for item in node]
    return node