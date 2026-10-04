"""Tests for the ODCS-flatten projection (plan §3.6).

Round-trip: nested Proposal → ODCS-flat row → nested Proposal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.odcs_flatten import flatten, unflatten  # noqa: E402

REPO_ROOT = ROOT
EXAMPLE_PATH = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"


def _example_proposal() -> dict:
    """Return the v2 worked example's nested proposal dict."""
    return json.loads(EXAMPLE_PATH.read_text())["proposal"]


def test_public_flatten_omits_restricted_fields() -> None:
    proposal = _example_proposal()
    row = flatten(proposal, projection="public")
    assert "id" in row
    assert row["id"] == "groton-rhine-001"
    assert "activityCode" in row
    assert row["activityCode"] == "housing.rehabilitation.facade"
    # Restricted fields must be absent in public projection.
    assert "applicantDisplayName" not in row
    assert "geometry" not in row
    assert "proofSignature" not in row


def test_restricted_flatten_includes_restricted_fields() -> None:
    proposal = _example_proposal()
    row = flatten(proposal, projection="restricted")
    assert row["applicantDisplayName"] == "Jane Groton-Resident"
    assert row["geometry"] is not None
    # proof is null in the example, so the columns are null.
    assert row["proofSignature"] is None


def test_round_trip_public() -> None:
    proposal = _example_proposal()
    row = flatten(proposal, projection="public")
    rebuilt = unflatten(row, projection="public")
    # Compare public-keyed fields only.
    assert rebuilt["id"] == proposal["id"]
    assert rebuilt["parcel"]["jurisdiction"] == proposal["parcel"]["jurisdiction"]
    assert rebuilt["parcel"]["crs"] == proposal["parcel"]["crs"]
    assert rebuilt["activity"]["code"] == proposal["activity"]["code"]
    assert rebuilt["lifecycle"]["state"] == proposal["lifecycle"]["state"]


def test_round_trip_restricted() -> None:
    proposal = _example_proposal()
    row = flatten(proposal, projection="restricted")
    rebuilt = unflatten(row, projection="restricted")
    assert rebuilt["applicant"]["displayName"] == proposal["applicant"]["displayName"]
    assert rebuilt["parcel"]["geometry"] == proposal["parcel"]["geometry"]


def test_odcs_contract_property_names_match_mapping() -> None:
    """Every ODCS column produced by flatten() must have a property in the contract.

    This is the conformance check: the canonical-model mapping table
    (§3.6) and the ODCS contract's `physicalName` annotations must
    agree. We parse the contract YAML, extract the `physicalName`
    trailing segment, and assert set equality with the flatten output.
    """
    import yaml  # noqa: PLC0415

    contract_path = REPO_ROOT / "contracts" / "groton-rhine-001.datacontract.yaml"
    contract = yaml.safe_load(contract_path.read_text())

    proposal_props = contract["schema"][0]["properties"]
    contract_columns = {p["name"] for p in proposal_props}

    proposal = _example_proposal()
    row = flatten(proposal, projection="public")
    flatten_columns = set(row.keys())

    # The contract must declare every public-flatten column.
    missing = flatten_columns - contract_columns
    assert not missing, f"contract missing columns: {missing}"
    # And the contract's proposal-entity columns must all be reachable
    # via flatten (i.e. no orphan columns).
    orphan = contract_columns - flatten_columns
    assert not orphan, f"contract has orphan columns: {orphan}"


def test_odcs_contract_omits_restricted_fields() -> None:
    """The ODCS contract must not declare restricted-only fields.

    Per plan §3.6: applicant.*, proof.*, raw geometry are RESTRICTED
    and excluded from the public ODCS-flatten projection.
    """
    import yaml  # noqa: PLC0415

    contract_path = REPO_ROOT / "contracts" / "groton-rhine-001.datacontract.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    names = {p["name"] for p in contract["schema"][0]["properties"]}

    forbidden = {
        "applicantDisplayName",
        "applicantContactEmail",
        "applicantResidencyKind",
        "applicantAuthorityKind",
        "geometry",  # raw geometry is restricted; the contract has geometryFormat / crs / snapshotHash instead
        "proofSignature",
        "proofSigningKey",
        "proofNonce",
    }
    leaked = names & forbidden
    assert not leaked, f"ODCS contract leaked restricted fields: {leaked}"