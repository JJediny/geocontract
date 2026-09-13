"""Tests for the citizen-source directory harvest (plan §6).

Verifies:

- ``manifest.json`` is written with the right shape.
- ``records.jsonl`` contains one line per successfully-harvested source.
- ``contracts/`` contains a copy of each source file.
- Errors on a single source do not abort the whole harvest; the
  manifest records ``status: error`` with the message.
- Restricted projection requires the authority token.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.citizen_source_manifest import (  # noqa: E402
    harvest_directory,
    load_canonical,
)

REPO_ROOT = ROOT
EXAMPLE = REPO_ROOT / "examples" / "groton-rhine-001.example.data.json"
CONTRACT = REPO_ROOT / "contracts" / "groton-rhine-001.datacontract.yaml"


# ── Directory layout ────────────────────────────────────────────────────────


def test_directory_layout_created(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE], out_dir=out)
    assert (out / "manifest.json").exists()
    assert (out / "records.jsonl").exists()
    assert (out / "contracts").is_dir()
    assert (out / "contracts" / EXAMPLE.name).exists()


def test_manifest_shape(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["harvester_version"].startswith("geocontract-tools")
    assert manifest["projection"] == "public"
    assert manifest["records_count"] == 1
    assert len(manifest["sources"]) == 1
    src = manifest["sources"][0]
    assert src["status"] == "ok"
    assert src["contract_id"] == "groton-rhine-001"
    assert src["lifecycle_state"] == "draft"
    assert src["content_hash"].startswith("sha256:")
    assert src["source_hash"].startswith("sha256:")
    assert src["kind"] == "file"


def test_records_jsonl_shape(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE], out_dir=out)
    lines = (out / "records.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["contract_id"] == "groton-rhine-001"
    assert obj["projection"] == "public"


def test_multiple_sources_emit_multiple_records(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE, CONTRACT], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["records_count"] == 2
    assert len(manifest["sources"]) == 2
    lines = (out / "records.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_duplicate_basenames_are_recorded_as_an_error(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / EXAMPLE.name
    second = second_dir / EXAMPLE.name
    first.write_bytes(EXAMPLE.read_bytes())
    second.write_bytes(EXAMPLE.read_bytes())

    out = tmp_path / "harvest"
    harvest_directory([first, second], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert [source["status"] for source in manifest["sources"]] == ["ok", "error"]
    assert manifest["records_count"] == 1
    assert "basename collision" in manifest["sources"][1]["error"]


def test_error_source_recorded_but_does_not_abort(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    bad = tmp_path / "broken.json"
    bad.write_text("not valid json{")
    harvest_directory([EXAMPLE, bad], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    # Good source succeeded; bad source recorded as error.
    statuses = [s["status"] for s in manifest["sources"]]
    assert statuses == ["ok", "error"]
    # records.jsonl contains only the successful one.
    lines = (out / "records.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    # contracts/ does NOT contain the failed file (no copy attempted).
    assert not (out / "contracts" / bad.name).exists()


def test_restricted_projection_requires_token(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    with pytest.raises(PermissionError, match="authority_token"):
        harvest_directory([EXAMPLE], out_dir=out, projection="restricted")


def test_restricted_projection_with_token_changes_content_hash(tmp_path: Path) -> None:
    """Public vs restricted projection must produce different content_hashes
    because the restricted projection includes the applicant + proof subtrees.
    """
    pub = tmp_path / "pub"
    harvest_directory([EXAMPLE], out_dir=pub, projection="public")
    res = tmp_path / "res"
    harvest_directory(
        [EXAMPLE],
        out_dir=res,
        projection="restricted",
        authority_token="t-1",
    )
    pub_record = json.loads((pub / "records.jsonl").read_text().strip())
    res_record = json.loads((res / "records.jsonl").read_text().strip())
    assert pub_record["content_hash"] != res_record["content_hash"]


def test_manifest_records_fetched_at_utc(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    fa = manifest["fetched_at"]
    assert fa.endswith("+00:00") or fa.endswith("Z")


def test_contracts_copy_is_byte_equal(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([EXAMPLE], out_dir=out)
    copied = (out / "contracts" / EXAMPLE.name).read_bytes()
    original = EXAMPLE.read_bytes()
    assert copied == original


def test_yaml_source_works(tmp_path: Path) -> None:
    out = tmp_path / "harvest"
    harvest_directory([CONTRACT], out_dir=out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["sources"][0]["contract_id"] == "groton-rhine-001"
    assert manifest["sources"][0]["contract_version"] == "0.2.0"