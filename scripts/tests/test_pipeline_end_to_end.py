"""End-to-end pipeline integration test.

Exercises the entire geocontract v2 pipeline against the committed
worked example:

  1. Validate ``examples/groton-rhine-001.example.data.json``
     against ``templates/proposed-action.template.schema.json``.
  2. Verify the example's proof envelope (walletless / null-proof
     path) via ``verify_proof``.
  3. Validate ``contracts/groton-rhine-001.datacontract.yaml``
     against the canonical ODCS v3.1.0 master schema.
  4. Harvest the example through the citizen-source harvester and
     confirm the resulting JSONL record is well-formed.
  5. Harvest the example through the directory-mode harvester and
     confirm the manifest + records.jsonl + contracts/ layout.
  6. Apply the public projection and confirm restricted fields are
     absent.
  7. Validate the activity code against the ontology catalog.
  8. Round-trip flatten → unflatten on the public columns and
     confirm parity.

This test is intentionally self-contained: it does not require
network access, only the committed files. It runs as part of
``mise run test`` and gives the suite a single regression net
across the whole v2 core path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.canonicalize import canonicalize_for_signing  # noqa: E402
from geocontract_tools.odcs_flatten import flatten, unflatten  # noqa: E402
from geocontract_tools.public_projection import public_projection  # noqa: E402
from geocontract_tools.validate_odcs import load_master_schema, validate_odcs_yaml  # noqa: E402
from geocontract_tools.validate_ontology import ActivityOntology  # noqa: E402
from geocontract_tools.validate_proof import verify_proof  # noqa: E402

from geocontract_tools.citizen_source import harvest_one, to_jsonl as citizen_to_jsonl  # noqa: E402
from geocontract_tools.citizen_source_manifest import harvest_directory  # noqa: E402

REPO_ROOT = ROOT
TEMPLATE = REPO_ROOT / "templates" / "proposed-action.template.schema.json"
EXAMPLE = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"
CONTRACT = REPO_ROOT / "contracts" / "groton-rhine-001.datacontract.yaml"
CATALOG = REPO_ROOT / "ontology" / "activity-concept-catalog.v1.0.json"


@pytest.fixture(scope="module")
def proposal() -> dict:
    return json.loads(EXAMPLE.read_text())["proposal"]


# ── 1. JSON Schema validation ───────────────────────────────────────────────


def test_step1_json_schema_validates(proposal: dict) -> None:
    schema = json.loads(TEMPLATE.read_text())
    Draft202012Validator(schema).validate({"proposal": proposal})


# ── 2. Proof envelope verification (walletless / null path) ───────────────


def test_step2_proof_envelope_no_proof_means_draft(proposal: dict) -> None:
    """Worked example is draft / walletless — proof is null. verify_proof
    must accept this without raising."""
    assert proposal.get("proof") is None
    verify_proof(proposal)  # no did_resolver needed; absence is OK


# ── 3. ODCS contract validation ─────────────────────────────────────────────


def test_step3_odcs_contract_validates() -> None:
    master = load_master_schema()
    errors = validate_odcs_yaml(CONTRACT, master)
    assert errors == [], "ODCS contract failed validation:\n" + "\n".join(errors)


# ── 4. Citizen-source harvester emits a JSONL record ────────────────────────


def test_step4_harvest_emits_jsonl() -> None:
    record = harvest_one(EXAMPLE, fetched_at="2026-09-13T00:00:00+00:00")
    obj = json.loads(citizen_to_jsonl([record]).strip())
    assert obj["contract_id"] == "groton-rhine-001"
    assert obj["projection"] == "public"
    assert obj["content_hash"].startswith("sha256:")


# ── 5. Directory-mode harvester produces the expected layout ───────────────


def test_step5_directory_layout(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    manifest = harvest_directory([EXAMPLE, CONTRACT], out_dir=out)
    assert manifest["records_count"] == 2
    assert (out / "manifest.json").exists()
    assert (out / "records.jsonl").exists()
    assert (out / "contracts" / EXAMPLE.name).exists()
    assert (out / "contracts" / CONTRACT.name).exists()


# ── 6. Public projection strips restricted fields ───────────────────────────


def test_step6_public_projection_strips_restricted(proposal: dict) -> None:
    public = public_projection(proposal)
    assert "applicant" not in public
    assert "proof" not in public
    assert "geometry" not in public["parcel"]
    # Public fields preserved.
    assert public["id"] == proposal["id"]
    assert public["parcel"]["jurisdiction"] == proposal["parcel"]["jurisdiction"]
    assert public["activity"]["code"] == proposal["activity"]["code"]


# ── 7. Activity code is in the ontology catalog ─────────────────────────────


def test_step7_activity_in_ontology(proposal: dict) -> None:
    ont = ActivityOntology.load(CATALOG)
    row = ont.validate_code(proposal["activity"]["code"])
    assert row["lifecycleStatus"] == "active"
    assert row["regulatoryStatus"] == "descriptive_only"


# ── 8. ODCS-flatten round-trip on public columns ────────────────────────────


def test_step8_odcs_flatten_round_trip(proposal: dict) -> None:
    row = flatten(proposal, projection="public")
    rebuilt = unflatten(row, projection="public")
    assert rebuilt["id"] == proposal["id"]
    assert rebuilt["parcel"]["jurisdiction"] == proposal["parcel"]["jurisdiction"]
    assert rebuilt["activity"]["code"] == proposal["activity"]["code"]
    assert rebuilt["lifecycle"]["state"] == proposal["lifecycle"]["state"]


# ── Composite invariants ─────────────────────────────────────────────────────


def test_invariants_v1_conflation_gone(proposal: dict) -> None:
    """v1 conflated anchoring with approval; v2 separates them.

    The example must NOT carry an `approvalCode` field at the
    proposal root, and must NOT carry token fields.
    """
    forbidden_root_fields = {
        "approvalCode",
        "approval_code",
        "fundingGoal",
        "tokenSymbol",
        "tokenAddress",
        "raiseTarget",
        "acceptChainIds",
    }
    assert forbidden_root_fields.isdisjoint(proposal.keys()), (
        f"v1 conflation leaked: {forbidden_root_fields & proposal.keys()}"
    )


def test_invariants_anchoring_is_independent_of_approval(proposal: dict) -> None:
    """The proposal's `lifecycle.state` and `anchorReceipt.contentHash`
    are independent — neither implies the other."""
    if proposal["anchorReceipt"] is None:
        # The worked example has not been anchored; this is the v2
        # default for a draft. Confirm the lifecycle state is not
        # implicitly "approved" via the absence of anchorReceipt.
        assert proposal["lifecycle"]["state"] != "approved"


def test_invariants_restricted_projection_changes_content_hash(proposal: dict) -> None:
    """The public and restricted projections must produce different
    content_hashes because the restricted projection carries the
    applicant + proof subtrees."""
    import hashlib

    public_body = public_projection(proposal)
    pub_hash = "sha256:" + hashlib.sha256(canonicalize_for_signing(public_body)).hexdigest()
    res_hash = "sha256:" + hashlib.sha256(canonicalize_for_signing(proposal)).hexdigest()
    assert pub_hash != res_hash


def test_invariants_schema_hash_does_not_depend_on_proof(proposal: dict) -> None:
    """Adding a (placeholder) proof envelope must not change the
    content_hash of the public projection."""
    import hashlib

    without_proof = public_projection(proposal)
    base_hash = "sha256:" + hashlib.sha256(canonicalize_for_signing(without_proof)).hexdigest()

    with_proof = dict(without_proof)
    with_proof["proof"] = {"signature": "ignored"}
    alt_hash = "sha256:" + hashlib.sha256(canonicalize_for_signing(with_proof)).hexdigest()
    assert base_hash == alt_hash