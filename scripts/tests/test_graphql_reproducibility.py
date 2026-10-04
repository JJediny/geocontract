"""Tests for the generated GraphQL SDL.

jxql performs schema parse + SDL generation in one step; if jxql
succeeds, the SDL is parseable by construction. We therefore test:

1. The generated SDL files exist and are non-empty.
2. They start with the GENERATED header (anti-curation guard).
3. Running `mise run generate-graphql` twice yields byte-equal output
   (reproducibility check).
4. The Proposal type implements Node (entity marker), and value-object
   types do NOT.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

REPO_ROOT = ROOT
MODELS = REPO_ROOT / "models"


def test_models_exist() -> None:
    for name in (
        "dcat-us-catalog",
        "nepa-exclusions",
        "pic-standards",
        "proposed-action",
    ):
        path = MODELS / f"{name}.canonical.graphql"
        assert path.exists(), f"missing {path}"
        assert path.stat().st_size > 0, f"empty {path}"


def test_generated_header_present() -> None:
    for sdl in MODELS.glob("*.canonical.graphql"):
        first = sdl.read_text().splitlines()[0]
        assert first.startswith("# GENERATED"), f"{sdl.name}: {first!r}"


def test_proposal_type_is_entity() -> None:
    """Only Proposal should `implements Node` (plan §3.5)."""
    sdl = (MODELS / "proposed-action.canonical.graphql").read_text()
    proposal_match = re.search(r"type Proposal[^{]*\{", sdl)
    assert proposal_match is not None, "Proposal type not found"
    assert "implements Node" in proposal_match.group(0)
    assert "@key" in proposal_match.group(0)


def test_value_objects_do_not_implement_node() -> None:
    """Applicant, ResidencyProof, AuthorityProof, Parcel, Activity,
    AnchorReceipt, Lifecycle, Revision, Proof must NOT implement Node
    (plan §3.5: only Proposal is an entity)."""
    sdl = (MODELS / "proposed-action.canonical.graphql").read_text()
    forbidden = [
        "Applicant",
        "ResidencyProof",
        "AuthorityProof",
        "Parcel",
        "Activity",
        "AnchorReceipt",
        "Lifecycle",
        "Revision",
        "Proof",
    ]
    for tname in forbidden:
        m = re.search(rf"type {tname}[^{{]*\{{", sdl)
        assert m is not None, f"{tname} type not found"
        assert "implements Node" not in m.group(0), (
            f"{tname} unexpectedly `implements Node`"
        )


def test_no_token_fields_in_graphql() -> None:
    """Plan §13.1: token issuance is out-of-core. The generated SDL
    must not carry tokenSymbol / tokenAddress / raiseTarget / fundingGoal."""
    sdl = (MODELS / "proposed-action.canonical.graphql").read_text()
    for forbidden in ("tokenSymbol", "tokenAddress", "raiseTarget", "fundingGoal"):
        assert forbidden not in sdl, f"{forbidden} leaked into core GraphQL"


def test_no_approval_code_field() -> None:
    """v1 conflated anchoring with approval (`approvalCode`). v2 separates them."""
    sdl = (MODELS / "proposed-action.canonical.graphql").read_text()
    assert "approvalCode" not in sdl
    assert "approval_code" not in sdl


def test_generated_graphql_is_reproducible() -> None:
    """Running `mise run generate-graphql` twice yields byte-equal output."""
    sdl_path = MODELS / "proposed-action.canonical.graphql"
    before = sdl_path.read_bytes()
    try:
        subprocess.run(
            ["mise", "run", "generate-graphql"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        after = sdl_path.read_bytes()
        assert before == after, "generated SDL is not byte-reproducible"
    finally:
        sdl_path.write_bytes(before)