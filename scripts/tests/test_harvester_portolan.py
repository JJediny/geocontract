"""Tests for geocontract_tools.harvester and geocontract_tools.portolan_sink.

Tests the federated harvester with --sink portolan functionality:
1. Source discovery (file, URL, git, S3)
2. Contract fetching and parsing
3. Mirror collection generation
4. Catalog structure updates
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from geocontract_tools.harvester import (
    HarvestError,
    HarvestResult,
    HarvestSource,
    _extract_source_url,
    discover,
    fetch_source,
    harvest_source,
    slugify,
)
from geocontract_tools.portolan_sink import (
    build_mirror_collection,
    ensure_mirror_catalog,
    slugify as portolan_slugify,
    update_mirror_catalog,
    update_root_catalog,
    write_mirror_collection,
)


# ── Source Discovery ─────────────────────────────────────────────────────────


def test_discover_local_file() -> None:
    """Local file paths are classified as 'file' kind."""
    sources = discover(["contracts/nepa-exclusions.datacontract.yaml"])
    assert len(sources) == 1
    assert sources[0].kind == "file"
    assert sources[0].location == "contracts/nepa-exclusions.datacontract.yaml"


def test_discover_http_url() -> None:
    """HTTP URLs are classified as 'url' kind."""
    sources = discover(["https://example.com/contract.yaml"])
    assert len(sources) == 1
    assert sources[0].kind == "url"
    assert sources[0].location == "https://example.com/contract.yaml"


def test_discover_git_url() -> None:
    """Git URLs are classified as 'git' kind."""
    sources = discover(["git@github.com:user/repo.git"])
    assert len(sources) == 1
    assert sources[0].kind == "git"


def test_discover_s3_uri() -> None:
    """S3 URIs are classified as 's3' kind."""
    sources = discover(["s3://bucket/contract.yaml"])
    assert len(sources) == 1
    assert sources[0].kind == "s3"


def test_discover_file_uri() -> None:
    """file:// URIs are classified as 'file' kind with prefix stripped."""
    sources = discover(["file:///path/to/contract.yaml"])
    assert len(sources) == 1
    assert sources[0].kind == "file"
    assert sources[0].location == "/path/to/contract.yaml"


# ── Slug Generation ──────────────────────────────────────────────────────────


def test_slugify_basic() -> None:
    """Basic slugification works."""
    assert slugify("My Contract Name") == "my-contract-name"
    assert slugify("Test_Contract_123") == "test-contract-123"


def test_slugify_special_chars() -> None:
    """Special characters are replaced with hyphens."""
    assert slugify("Test@Contract#123!") == "test-contract-123"
    assert slugify("Multiple---Hyphens") == "multiple-hyphens"


def test_slugify_empty() -> None:
    """Empty strings become 'unknown'."""
    assert slugify("") == "unknown"
    assert slugify("!!!") == "unknown"


# ── Source URL Extraction ────────────────────────────────────────────────────


def test_extract_source_url_from_comment() -> None:
    """Source URL is extracted from contract comments."""
    contract_data = b"""# This is a contract
# Source: https://example.com/data.json
# Other comment

id: test
name: Test Contract
"""
    url = _extract_source_url(contract_data)
    assert url == "https://example.com/data.json"


def test_extract_source_url_not_found() -> None:
    """Returns None if no Source comment found."""
    contract_data = b"""# This is a contract
# No source here

id: test
"""
    url = _extract_source_url(contract_data)
    assert url is None


def test_extract_source_url_invalid() -> None:
    """Returns None for non-URL Source comments."""
    contract_data = b"""# Source: not-a-url
id: test
"""
    url = _extract_source_url(contract_data)
    assert url is None


# ── Contract Fetching ────────────────────────────────────────────────────────


def test_fetch_source_local_file() -> None:
    """Local files are fetched successfully."""
    source = HarvestSource(
        location="contracts/nepa-exclusions.datacontract.yaml",
        kind="file",
    )
    data = fetch_source(source)
    assert len(data) > 0
    contract = yaml.safe_load(data)
    assert contract["id"] == "geocontract-nepa-exclusions"


def test_fetch_source_file_not_found() -> None:
    """Missing files raise HarvestError."""
    source = HarvestSource(location="nonexistent.yaml", kind="file")
    with pytest.raises(HarvestError, match="File not found"):
        fetch_source(source)


# ── Harvest Result ───────────────────────────────────────────────────────────


def test_harvest_source_success() -> None:
    """Harvesting a local file produces a valid HarvestResult."""
    source = HarvestSource(
        location="contracts/nepa-exclusions.datacontract.yaml",
        kind="file",
    )
    result = harvest_source(source)
    
    assert result.source == source
    assert result.contract["id"] == "geocontract-nepa-exclusions"
    assert len(result.contract_data) > 0
    assert result.contract_checksum.startswith("sha256:")
    assert result.fetched_at.endswith("Z")


# ── Mirror Collection Building ───────────────────────────────────────────────


def test_build_mirror_collection_structure() -> None:
    """Mirror collection has correct Portolan structure."""
    contract = {
        "id": "test-contract",
        "name": "Test Contract",
        "version": "1.0.0",
        "description": "Test description",
        "tenant": "test-tenant",
        "tags": ["test", "example"],
        "schema": [
            {
                "name": "TestEntity",
                "properties": [
                    {"name": "id", "logicalType": "integer", "description": "ID"},
                    {"name": "name", "logicalType": "string", "description": "Name"},
                ],
            }
        ],
    }
    
    source = HarvestSource(location="test.yaml", kind="file")
    result = HarvestResult(
        source=source,
        contract=contract,
        contract_data=b"test data",
        contract_checksum="sha256:abc123",
        fetched_at="2026-10-03T00:00:00Z",
    )
    
    source_info = {
        "source_url": "test.yaml",
        "upstream_name": "Test Upstream",
        "upstream_url": "https://example.com",
        "via_url": "https://example.com/source",
    }
    
    class SinkResult:
        def __init__(self):
            self.contract = contract
            self.source_data = b"test data"
            self.source_info = source_info
    
    collection = build_mirror_collection(SinkResult(), "2026-10-03T00:00:00Z")
    
    # Check required fields
    assert collection["type"] == "Collection"
    assert collection["stac_version"] == "1.1.0"
    assert collection["id"] == "mirror/test-contract"
    assert collection["title"] == "Mirror: Test Contract"
    assert collection["license"] == "CC0-1.0"
    
    # Check providers
    assert len(collection["providers"]) == 2
    assert collection["providers"][0]["roles"] == ["producer"]
    assert collection["providers"][1]["roles"] == ["host"]
    
    # Check links
    rels = {link["rel"] for link in collection["links"]}
    assert "via" in rels
    assert "root" in rels
    assert "parent" in rels
    
    # Check custom properties
    assert collection["geocontract:mirror"] is True
    assert collection["geocontract:contract_id"] == "test-contract"


def test_build_mirror_collection_odcs_description() -> None:
    """ODCS description object is converted to string."""
    contract = {
        "id": "test",
        "name": "Test",
        "version": "1.0.0",
        "description": {
            "purpose": "This is the purpose",
            "usage": "This is the usage",
            "limitations": "These are limitations",
        },
        "tenant": "test",
        "schema": [{"name": "Entity", "properties": []}],
    }
    
    source = HarvestSource(location="test.yaml", kind="file")
    result = HarvestResult(
        source=source,
        contract=contract,
        contract_data=b"test",
        contract_checksum="sha256:abc",
        fetched_at="2026-10-03T00:00:00Z",
    )
    
    class SinkResult:
        def __init__(self):
            self.contract = contract
            self.source_data = b"test"
            self.source_info = {"source_url": "test.yaml", "via_url": "https://example.com"}
    
    collection = build_mirror_collection(SinkResult(), "2026-10-03T00:00:00Z")
    
    # Description should be a string, not an object
    assert isinstance(collection["description"], str)
    assert collection["description"] == "This is the purpose"


# ── Mirror Catalog Management ────────────────────────────────────────────────


def test_ensure_mirror_catalog_creates_structure(tmp_path: Path) -> None:
    """ensure_mirror_catalog creates the mirror sub-catalog structure."""
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    
    mirror_catalog_path = ensure_mirror_catalog(catalog_dir)
    
    assert mirror_catalog_path.exists()
    assert (catalog_dir / "mirror" / "README.md").exists()
    assert (catalog_dir / "mirror" / "AGENTS.md").exists()
    
    catalog = json.loads(mirror_catalog_path.read_text())
    assert catalog["type"] == "Catalog"
    assert catalog["id"] == "mirror"


def test_update_mirror_catalog_adds_child_links(tmp_path: Path) -> None:
    """update_mirror_catalog adds child links to existing collections."""
    catalog_dir = tmp_path / "catalog"
    mirror_dir = catalog_dir / "mirror"
    mirror_dir.mkdir(parents=True)
    
    # Create mirror catalog
    ensure_mirror_catalog(catalog_dir)
    
    # Create a test collection
    collection_dir = mirror_dir / "test-collection"
    collection_dir.mkdir()
    collection = {
        "type": "Collection",
        "id": "mirror/test-collection",
        "title": "Test Collection",
    }
    (collection_dir / "collection.json").write_text(json.dumps(collection))
    
    # Update mirror catalog
    update_mirror_catalog(catalog_dir)
    
    # Check that child link was added
    mirror_catalog = json.loads((mirror_dir / "catalog.json").read_text())
    child_links = [link for link in mirror_catalog["links"] if link["rel"] == "child"]
    assert len(child_links) == 1
    assert child_links[0]["href"] == "./test-collection/collection.json"
    assert child_links[0]["title"] == "Test Collection"


def test_update_root_catalog_adds_mirror_link(tmp_path: Path) -> None:
    """update_root_catalog adds mirror child link to root catalog."""
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    
    # Create root catalog
    root_catalog = {
        "type": "Catalog",
        "id": "test",
        "links": [
            {"rel": "root", "href": "./catalog.json"},
            {"rel": "child", "href": "./federal/catalog.json", "title": "Federal"},
        ],
    }
    (catalog_dir / "catalog.json").write_text(json.dumps(root_catalog))
    
    # Create mirror sub-catalog
    mirror_dir = catalog_dir / "mirror"
    mirror_dir.mkdir()
    (mirror_dir / "catalog.json").write_text("{}")
    
    # Update root catalog
    update_root_catalog(catalog_dir)
    
    # Check that mirror link was added
    updated_catalog = json.loads((catalog_dir / "catalog.json").read_text())
    child_links = [link for link in updated_catalog["links"] if link["rel"] == "child"]
    assert len(child_links) == 2
    mirror_link = [link for link in child_links if "mirror" in link["href"]]
    assert len(mirror_link) == 1
    assert mirror_link[0]["title"] == "Harvested Mirrors"


# ── End-to-End Harvest ───────────────────────────────────────────────────────


def test_harvest_to_portolan_end_to_end(tmp_path: Path) -> None:
    """End-to-end test of harvesting to Portolan mirror collections."""
    from geocontract_tools.harvester import harvest_to_portolan
    
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    
    # Create a test contract with source URL in comments
    contract_yaml = """# Source: https://example.com/source-data
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
    contract = yaml.safe_load(contract_yaml)
    contract_data = contract_yaml.encode("utf-8")
    
    # Create harvest result
    source = HarvestSource(location="test.yaml", kind="file")
    result = HarvestResult(
        source=source,
        contract=contract,
        contract_data=contract_data,
        contract_checksum="sha256:test123",
        fetched_at="2026-10-03T00:00:00Z",
    )
    
    # Harvest to Portolan
    harvest_to_portolan([result], catalog_dir)
    
    # Verify structure
    assert (catalog_dir / "mirror" / "catalog.json").exists()
    assert (catalog_dir / "mirror" / "test-harvest" / "collection.json").exists()
    assert (catalog_dir / "mirror" / "test-harvest" / "test-harvest.datacontract.yaml").exists()
    
    # Verify collection content
    collection = json.loads(
        (catalog_dir / "mirror" / "test-harvest" / "collection.json").read_text()
    )
    assert collection["id"] == "mirror/test-harvest"
    assert collection["geocontract:contract_id"] == "test-harvest"
    assert collection["geocontract:mirror"] is True
    
    # Verify mirror catalog has child link
    mirror_catalog = json.loads((catalog_dir / "mirror" / "catalog.json").read_text())
    child_links = [link for link in mirror_catalog["links"] if link["rel"] == "child"]
    assert len(child_links) == 1
    assert "test-harvest" in child_links[0]["href"]
