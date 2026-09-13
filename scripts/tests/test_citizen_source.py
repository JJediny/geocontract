"""Tests for the citizen-source harvester (plan §6, Phase 4 of §8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.citizen_source import (  # noqa: E402
    HarvestRecord,
    harvest_many,
    harvest_one,
    load_canonical,
    main,
    to_jsonl,
)

REPO_ROOT = ROOT
EXAMPLE_PATH = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"
CONTRACT_PATH = REPO_ROOT / "contracts" / "groton-rhine-001.datacontract.yaml"


# ── Loaders ──────────────────────────────────────────────────────────────────


def test_load_canonical_from_nested_json() -> None:
    proposal = load_canonical(EXAMPLE_PATH)
    assert proposal["id"] == "groton-rhine-001"
    assert proposal["activity"]["code"] == "housing.rehabilitation.facade"
    assert proposal["lifecycle"]["state"] == "draft"


def test_load_canonical_from_canonical_yaml(tmp_path: Path) -> None:
    document = json.loads(EXAMPLE_PATH.read_text())
    path = tmp_path / "proposal.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    proposal = load_canonical(path)
    assert proposal["id"] == "groton-rhine-001"
    assert proposal["parcel"]["authoritativeParcelId"] == "M:123 B:45 L:678"


def test_load_canonical_from_odcs_yaml() -> None:
    proposal = load_canonical(CONTRACT_PATH)
    # The ODCS YAML stores values in `examples[]`; the rebuild
    # recovers the public-projection canonical keys.
    assert proposal["id"] == "groton-rhine-001"
    assert proposal["activity"]["code"] == "housing.rehabilitation.facade"
    assert proposal["lifecycle"]["state"] == "draft"


def test_load_canonical_unsupported_format(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello")
    with pytest.raises(ValueError, match="unsupported source format"):
        load_canonical(p)


# ── Harvesting ───────────────────────────────────────────────────────────────


def test_cli_emits_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(EXAMPLE_PATH)]) == 0
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["contract_id"] == "groton-rhine-001"
    assert record["projection"] == "public"


def test_harvest_one_public_projection() -> None:
    record = harvest_one(EXAMPLE_PATH, projection="public")
    assert isinstance(record, HarvestRecord)
    assert record.contract_id == "groton-rhine-001"
    assert record.projection == "public"
    assert record.lifecycle_state == "draft"
    assert record.activity_code == "housing.rehabilitation.facade"
    assert record.jurisdiction == "us-ct-groton"
    assert record.content_hash.startswith("sha256:")
    assert len(record.content_hash) == len("sha256:") + 64


def test_harvest_one_restricted_requires_token() -> None:
    with pytest.raises(PermissionError, match="authority-token"):
        harvest_one(EXAMPLE_PATH, projection="restricted")


def test_harvest_one_restricted_with_token() -> None:
    record = harvest_one(
        EXAMPLE_PATH,
        projection="restricted",
        authority_token="t-1",
    )
    assert record.projection == "restricted"
    # Restricted projection keeps applicant + proof (which are public-Proj-stripped).
    # We can't easily assert on the record fields because they're flattened;
    # instead we check the content_hash differs from the public projection
    # because the canonical bytes include the applicant/proof subtrees.
    public = harvest_one(EXAMPLE_PATH, projection="public")
    assert record.content_hash != public.content_hash


def test_harvest_many_returns_list() -> None:
    records = harvest_many([EXAMPLE_PATH])
    assert len(records) == 1


def test_harvest_one_picks_up_contract_version_from_yaml() -> None:
    record = harvest_one(CONTRACT_PATH)
    assert record.contract_version == "0.2.0"


def test_harvest_one_picks_up_no_contract_version_for_json() -> None:
    record = harvest_one(EXAMPLE_PATH)
    assert record.contract_version is None


def test_harvest_one_records_source_path() -> None:
    record = harvest_one(EXAMPLE_PATH)
    assert record.source.endswith("groton-rhine-001.example.data.json")


def test_harvest_one_records_fetched_at_utc() -> None:
    record = harvest_one(EXAMPLE_PATH)
    assert record.fetched_at.endswith("+00:00") or record.fetched_at.endswith("Z")


# ── JSONL serialisation ──────────────────────────────────────────────────────


def test_to_jsonl_produces_one_line_per_record() -> None:
    records = harvest_many([EXAMPLE_PATH])
    out = to_jsonl(records)
    lines = out.strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["contract_id"] == "groton-rhine-001"
    assert obj["projection"] == "public"


def test_to_jsonl_keys_are_sorted() -> None:
    records = harvest_many([EXAMPLE_PATH])
    out = to_jsonl(records)
    obj = json.loads(out.strip())
    keys = list(obj.keys())
    assert keys == sorted(keys)


def test_to_jsonl_appends_trailing_newline() -> None:
    records = harvest_many([EXAMPLE_PATH])
    out = to_jsonl(records)
    assert out.endswith("\n")


# ── Additive v2 fields per plan §6 ──────────────────────────────────────────


def test_record_carries_additive_v2_fields() -> None:
    record = harvest_one(EXAMPLE_PATH)
    # Required additive fields per §6.
    assert hasattr(record, "content_hash")
    assert hasattr(record, "lifecycle_state")
    assert hasattr(record, "submission_id")
    assert hasattr(record, "anchor_service_ref")
    assert hasattr(record, "supersedes")
    # submission_id / anchor_service_ref / supersedes are null in
    # the worked example (no anchor has been performed).
    assert record.submission_id is None
    assert record.anchor_service_ref is None
    assert record.supersedes is None


def test_record_does_not_carry_v1_approval_code_field() -> None:
    """v1 conflated anchoring with approval (`approvalCode`). v2 separates them."""
    record = harvest_one(EXAMPLE_PATH)
    assert not hasattr(record, "approval_code")
    assert "approval_code" not in {f.name for f in _fields(record)}


def test_record_does_not_carry_token_fields() -> None:
    """v2 core has no tokens."""
    record = harvest_one(EXAMPLE_PATH)
    payload = json.loads(to_jsonl([record]).strip())
    for forbidden in ("tokenAddress", "tokenSymbol", "raiseTarget", "fundingGoal"):
        assert forbidden not in payload


def _fields(record: HarvestRecord) -> list:
    import dataclasses

    return dataclasses.fields(record)