"""Tests for the public projection (plan §5.8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.public_projection import public_projection  # noqa: E402

REPO_ROOT = ROOT
EXAMPLE_PATH = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"


def _example_proposal() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())["proposal"]


def test_public_projection_omits_applicant() -> None:
    proposal = _example_proposal()
    public = public_projection(proposal)
    assert "applicant" not in public
    assert "proof" not in public


def test_public_projection_preserves_public_fields() -> None:
    proposal = _example_proposal()
    public = public_projection(proposal)
    assert public["id"] == proposal["id"]
    assert public["parcel"]["jurisdiction"] == proposal["parcel"]["jurisdiction"]
    assert public["parcel"]["geometryFormat"] == proposal["parcel"]["geometryFormat"]
    assert "geometry" not in public["parcel"]
    assert public["activity"]["code"] == proposal["activity"]["code"]


def test_public_projection_does_not_mutate_input() -> None:
    proposal = _example_proposal()
    before = json.dumps(proposal, sort_keys=True)
    _ = public_projection(proposal)
    after = json.dumps(proposal, sort_keys=True)
    assert before == after


def test_public_projection_omits_proof_under_root() -> None:
    """The `proof` key is at the proposal root and must be dropped."""
    proposal = _example_proposal()
    proposal["proof"] = {"signature": "x"}
    public = public_projection(proposal)
    assert "proof" not in public


def test_public_projection_handles_lists() -> None:
    proposal = _example_proposal()
    proposal["revisions"] = [
        {"contentHash": "sha256:" + "a" * 64, "createdAt": "2026-09-12T00:00:00Z"},
        {"contentHash": "sha256:" + "b" * 64, "createdAt": "2026-09-13T00:00:00Z"},
    ]
    public = public_projection(proposal)
    assert len(public["revisions"]) == 2
    assert public["revisions"][0]["contentHash"].startswith("sha256:a")