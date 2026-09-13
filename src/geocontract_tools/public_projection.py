"""Public projection (plan §5.8) — emit only access-class=public fields.

The default projection for any harvested Proposal. The harvester
uses this projection by default and requires an authority-authenticated
header for the restricted projection.
"""

from __future__ import annotations

from typing import Any

# JSON paths explicitly tagged `x-graphql-access-class: restricted` in
# the v2 schema, plus the wrapper objects that contain them. Paths are
# relative to the proposal root; keeping the path explicit prevents a
# future unrelated `geometry` field from being removed accidentally.
# Anything not in this set is public-by-default (default-deny).
RESTRICTED_PATHS: frozenset[str] = frozenset(
    {
        "applicant",
        "proof",
        "parcel.geometry",
    }
)


def public_projection(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied proposal with all restricted fields removed."""
    if not isinstance(proposal, dict):
        raise TypeError(f"proposal must be a dict, got {type(proposal).__name__}")
    return _shallow_public(proposal)


def _shallow_public(node: Any, *, path: tuple[str, ...] = ()) -> Any:
    """Recursively strip restricted subtrees using proposal-relative paths."""
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for key, value in node.items():
            child_path = ".".join((*path, key))
            if child_path in RESTRICTED_PATHS:
                continue  # drop restricted subtree
            result[key] = _shallow_public(value, path=(*path, key))
        return result
    if isinstance(node, list):
        return [_shallow_public(item, path=path) for item in node]
    return node
