"""Tests for the harvester's geoparquet sink (issue #45, plan §5 PR B).

The sink must produce rows with the same schema as the generated
portfolio (shared row-builder, not a copy), route non-citizen contracts
to mirror rows with is_mirror=True and a via URL, and never touch the
tracked catalog/ tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools import build_geoparquet as bg  # noqa: E402
from geocontract_tools.harvester import (  # noqa: E402
    HarvestResult,
    HarvestSource,
    harvest_to_geoparquet,
)

MIRROR_CONTRACT_YAML = """# Source: https://example.com/source-data
id: test-harvest
name: Test Harvest Contract
version: 1.0.0
description: Test description for harvesting
tenant: test-org
tags:
  - test
schema:
  - name: TestEntity
    properties:
      - name: id
        logicalType: integer
      - name: value
        logicalType: string
"""

CITIZEN_CONTRACT_YAML = """# Source: https://example.org/citizen-proposal
id: test-citizen
name: Test Citizen Proposal
version: 1.0.0
description: A citizen-initiated proposal
tenant: us-ct-test
tags:
  - citizen
customProperties:
  - property: isCitizenInitiated
    value: true
  - property: jurisdiction
    value: us-ct-test
schema:
  - name: Proposal
    properties:
      - name: id
        logicalType: integer
"""


def _result(yaml_text: str, location: str = "test.yaml") -> HarvestResult:
    return HarvestResult(
        source=HarvestSource(location=location, kind="file"),
        contract=yaml.safe_load(yaml_text),
        contract_data=yaml_text.encode("utf-8"),
        contract_checksum="sha256:test123",
        fetched_at="2026-10-03T00:00:00Z",
    )


def _rows(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


def test_sink_writes_mirror_rows_with_via_url(tmp_path: Path) -> None:
    out = harvest_to_geoparquet([_result(MIRROR_CONTRACT_YAML)], tmp_path)

    assert out == tmp_path / "harvested.geoparquet"
    rows = _rows(out)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "mirror/test-harvest"
    assert row["is_mirror"] is True
    assert row["via_url"] == "https://example.com/source-data"
    assert row["updated"]


def test_sink_routes_citizen_proposals_to_non_mirror_rows(tmp_path: Path) -> None:
    out = harvest_to_geoparquet(
        [_result(CITIZEN_CONTRACT_YAML, "citizen.yaml")], tmp_path
    )
    rows = _rows(out)
    assert len(rows) == 1
    assert rows[0]["id"] == "citizen/test-citizen"
    assert rows[0]["is_mirror"] is False


def test_sink_schema_matches_generated_portfolio(tmp_path: Path) -> None:
    """Harvested rows and generated rows share one schema (plan §3)."""
    out = harvest_to_geoparquet([_result(MIRROR_CONTRACT_YAML)], tmp_path)

    harvested = pq.read_table(out).schema
    tracked = pq.read_table(ROOT / "examples" / "geocontracts.geoparquet").schema
    assert [f.name for f in harvested] == [f.name for f in tracked]
    assert harvested.field("geometry").type == tracked.field("geometry").type
    assert harvested.field("bbox").type == tracked.field("bbox").type
    assert (
        json.loads(harvested.metadata[b"geo"])["version"]
        == json.loads(tracked.metadata[b"geo"])["version"]
    )


def test_sink_output_stays_outside_the_tracked_tree(tmp_path: Path) -> None:
    harvest_to_geoparquet([_result(MIRROR_CONTRACT_YAML)], tmp_path)

    assert not (ROOT / "catalog" / "mirror" / "test-harvest").exists()
    assert not (ROOT / "harvested.geoparquet").exists()
    assert (tmp_path / "portolan-mirror" / "mirror").exists()


def test_sink_validates_by_reopening(tmp_path: Path) -> None:
    """The sink's own validation gate: bbox round-trip against the mirror tree."""
    out = harvest_to_geoparquet([_result(MIRROR_CONTRACT_YAML)], tmp_path)
    errors = bg.validate_against(out, tmp_path / "portolan-mirror", root=tmp_path)
    assert errors == []
