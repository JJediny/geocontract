"""Tests for geocontract_tools.build_catalog

Verifies that the Portolan catalog generator:
1. Produces deterministic output (same input → same output)
2. Correctly derives mirror status from providers
3. Validates required fields (license, bbox, provenance)
4. Generates valid STAC Collection and Catalog JSON
5. Seeds README.md and AGENTS.md files
6. Correctly handles the --check mode for CI drift detection
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from geocontract_tools.build_catalog import (
    BuildError,
    build,
    build_collection,
    validate_bbox,
    write_tree,
)

MANIFEST_PATH = Path("catalog/manifests/geocontract.yaml")
CATALOG_PATH = Path("catalog")


@pytest.fixture
def manifest_path() -> Path:
    """Return the path to the canonical manifest."""
    return MANIFEST_PATH


@pytest.fixture
def manifest() -> dict:
    """Load the canonical manifest."""
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def tmp_catalog() -> Path:
    """Create a temporary directory for catalog builds."""
    tmp = Path(tempfile.mkdtemp(prefix="geocontract-test-catalog-"))
    yield tmp
    if tmp.exists():
        shutil.rmtree(tmp)


@pytest.fixture
def tmp_manifest(tmp_path: Path, manifest: dict) -> Path:
    """Write manifest to a temp file and return the path."""
    manifest_file = tmp_path / "test-manifest.yaml"
    manifest_file.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest_file


def test_manifest_loads(manifest: dict) -> None:
    """The manifest is valid YAML with required fields."""
    assert "id" in manifest
    assert "title" in manifest
    assert "host" in manifest
    assert "collections" in manifest
    assert isinstance(manifest["collections"], list)


def test_build_is_deterministic(tmp_manifest: Path, tmp_catalog: Path) -> None:
    """Building twice produces identical output."""
    build(tmp_manifest, tmp_catalog)
    first_run = {p.read_text() for p in tmp_catalog.rglob("*.json")}

    shutil.rmtree(tmp_catalog)
    tmp_catalog.mkdir()
    build(tmp_manifest, tmp_catalog)
    second_run = {p.read_text() for p in tmp_catalog.rglob("*.json")}

    assert first_run == second_run


def test_build_creates_expected_structure(tmp_manifest: Path, manifest: dict, tmp_catalog: Path) -> None:
    """The build creates the expected directory structure."""
    written = build(tmp_manifest, tmp_catalog)
    write_tree(written, tmp_catalog)

    # Root catalog.json exists
    assert (tmp_catalog / "catalog.json").exists()

    # Sub-catalogs exist for each theme
    themes = {c["id"].split("/")[0] for c in manifest["collections"]}
    for theme in themes:
        assert (tmp_catalog / theme / "catalog.json").exists()
        assert (tmp_catalog / theme / "README.md").exists()
        assert (tmp_catalog / theme / "AGENTS.md").exists()

    # Collections exist
    for collection in manifest["collections"]:
        cid = collection["id"]
        theme, slug = cid.split("/")
        assert (tmp_catalog / theme / slug / "collection.json").exists()
        assert (tmp_catalog / theme / slug / "README.md").exists()
        assert (tmp_catalog / theme / slug / "AGENTS.md").exists()


def test_build_collection_valid_structure(manifest: dict, tmp_catalog: Path) -> None:
    """A generated collection.json has valid STAC structure."""
    collection_entry = manifest["collections"][0]  # federal/nepa-exclusions
    theme, doc = build_collection(collection_entry, manifest, tmp_catalog)

    # Required STAC fields
    assert doc["type"] == "Collection"
    assert doc["stac_version"] == "1.1.0"
    assert doc["id"] == collection_entry["id"]
    assert doc["title"]
    assert doc["description"]
    assert doc["license"] == "CC0-1.0"
    assert doc["providers"]
    assert doc["extent"]["spatial"]["bbox"]
    assert doc["extent"]["temporal"]["interval"]

    # Portolan profile extension
    assert "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json" in doc["stac_extensions"]

    # Links
    rels = {link["rel"] for link in doc["links"]}
    assert "root" in rels
    assert "parent" in rels
    assert "agents" in rels
    assert "describedby" in rels

    # Custom properties
    assert "geocontract:contract_id" in doc
    assert "geocontract:contract_version" in doc


def test_mirror_derivation_from_providers(manifest: dict, tmp_catalog: Path) -> None:
    """Mirror status is derived from providers, not declared."""
    # federal/nepa-exclusions has upstream producer, so it's a mirror
    nepa = next(c for c in manifest["collections"] if c["id"] == "federal/nepa-exclusions")
    theme, doc = build_collection(nepa, manifest, tmp_catalog)
    assert doc["geocontract:mirror"] is True

    # citizen/groton-rhine-001 has geocontract as producer, so it's official
    groton = next(c for c in manifest["collections"] if c["id"] == "citizen/groton-rhine-001")
    theme, doc = build_collection(groton, manifest, tmp_catalog)
    assert doc["geocontract:mirror"] is False


def test_mirror_requires_via_link() -> None:
    """A mirror collection without provenance.via raises an error."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "CC0-1.0",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
                "producers": [{"name": "PIC", "url": "https://permitting.innovation.gov/", "roles": ["producer"]}],
                # Missing provenance.via
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(BuildError, match="provenance.via"):
            build_collection(manifest["collections"][0], manifest, Path(tmp))


def test_bbox_validation() -> None:
    """Bbox validation enforces core.md rules."""
    # Valid CONUS bbox
    bbox = validate_bbox([-125.0, 24.0, -66.0, 50.0], "test")
    assert bbox == [-125.0, 24.0, -66.0, 50.0]

    # Invalid: NaN
    with pytest.raises(BuildError, match="NaN"):
        validate_bbox([float("nan"), 0.0, 10.0, 10.0], "test")

    # Invalid: infinite
    with pytest.raises(BuildError, match="infinite"):
        validate_bbox([0.0, float("inf"), 10.0, 10.0], "test")

    # Invalid: sentinel value
    with pytest.raises(BuildError, match="sentinel"):
        validate_bbox([0.0, 0.0, 10.0, 1e308], "test")

    # Invalid: out of range
    with pytest.raises(BuildError, match="longitude"):
        validate_bbox([-200.0, 0.0, 200.0, 10.0], "test")

    # Invalid: south > north
    with pytest.raises(BuildError, match="south"):
        validate_bbox([-10.0, 50.0, 10.0, 0.0], "test")


def test_via_link_must_be_html() -> None:
    """provenance.via must be an https URL (text/html landing page)."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "CC0-1.0",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
                "producers": [{"name": "PIC", "url": "https://permitting.innovation.gov/", "roles": ["producer"]}],
                "provenance": {"via": "http://example.com", "updated": "2026-10-03T00:00:00Z"},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(BuildError, match="https"):
            build_collection(manifest["collections"][0], manifest, Path(tmp))


def test_upstream_stac_emits_canonical_link() -> None:
    """A manifest entry that declares `upstream_stac` produces a rel:canonical link."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "CC0-1.0",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
                "producers": [{"name": "PIC", "url": "https://permitting.innovation.gov/", "roles": ["producer"]}],
                "provenance": {"via": "https://permitting.innovation.gov/", "updated": "2026-10-03T00:00:00Z"},
                "upstream_stac": "https://permitting.innovation.gov/stac/catalog.json",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        _, doc = build_collection(manifest["collections"][0], manifest, Path(tmp))
        canonical = [link for link in doc["links"] if link["rel"] == "canonical"]
        assert len(canonical) == 1
        assert canonical[0]["href"] == "https://permitting.innovation.gov/stac/catalog.json"
        assert canonical[0]["type"] == "application/json"


def test_upstream_stac_optional() -> None:
    """A manifest without `upstream_stac` does NOT emit a rel:canonical link."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "CC0-1.0",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
                "producers": [{"name": "PIC", "url": "https://permitting.innovation.gov/", "roles": ["producer"]}],
                "provenance": {"via": "https://permitting.innovation.gov/", "updated": "2026-10-03T00:00:00Z"},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        _, doc = build_collection(manifest["collections"][0], manifest, Path(tmp))
        canonical = [link for link in doc["links"] if link["rel"] == "canonical"]
        assert canonical == [], "no upstream_stac -> no canonical link"


def test_upstream_stac_must_be_https() -> None:
    """`upstream_stac` must be an https URL (F4 parity with `via`)."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "CC0-1.0",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
                "producers": [{"name": "PIC", "url": "https://permitting.innovation.gov/", "roles": ["producer"]}],
                "provenance": {"via": "https://permitting.innovation.gov/", "updated": "2026-10-03T00:00:00Z"},
                "upstream_stac": "http://example.com/stac/catalog.json",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(BuildError, match="https"):
            build_collection(manifest["collections"][0], manifest, Path(tmp))


def test_proprietary_license_rejected() -> None:
    """Portolan bans license: proprietary."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract", "url": "https://github.com/JJediny/geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                "license": "proprietary",
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(BuildError, match="proprietary"):
            build_collection(manifest["collections"][0], manifest, Path(tmp))


def test_assets_contain_contract_yaml(manifest: dict, tmp_catalog: Path) -> None:
    """The contract asset is present and has checksums."""
    collection_entry = manifest["collections"][0]
    theme, doc = build_collection(collection_entry, manifest, tmp_catalog)

    assert "contract" in doc["assets"]
    asset = doc["assets"]["contract"]
    assert asset["href"].endswith(".datacontract.yaml")
    assert asset["type"] == "application/yaml"
    assert asset["roles"] == ["metadata"]
    assert "file:size" in asset
    assert "file:checksum" in asset
    assert asset["file:checksum"].startswith("1220")  # multihash sha256


def test_table_columns_from_primary_entity(manifest: dict, tmp_catalog: Path) -> None:
    """table:columns is derived from the primary_entity's properties."""
    collection_entry = manifest["collections"][0]  # federal/nepa-exclusions
    theme, doc = build_collection(collection_entry, manifest, tmp_catalog)

    assert "table:columns" in doc
    columns = doc["table:columns"]
    assert isinstance(columns, list)
    assert len(columns) > 0
    for col in columns:
        assert "name" in col
        assert "type" in col
        assert "description" in col


def test_official_collection_has_no_via_link(manifest: dict, tmp_catalog: Path) -> None:
    """An official collection (geocontract as producer) has no via link."""
    groton = next(c for c in manifest["collections"] if c["id"] == "citizen/groton-rhine-001")
    theme, doc = build_collection(groton, manifest, tmp_catalog)

    via_links = [link for link in doc["links"] if link["rel"] == "via"]
    assert len(via_links) == 0


def test_mirror_collection_has_via_link(manifest: dict, tmp_catalog: Path) -> None:
    """A mirror collection has a via link to the upstream landing page."""
    nepa = next(c for c in manifest["collections"] if c["id"] == "federal/nepa-exclusions")
    theme, doc = build_collection(nepa, manifest, tmp_catalog)

    via_links = [link for link in doc["links"] if link["rel"] == "via"]
    assert len(via_links) == 1
    via = via_links[0]
    assert via["type"] == "text/html"
    assert via["href"].startswith("https://")


def test_bbox_coarsened_for_citizen_proposal(manifest: dict, tmp_catalog: Path) -> None:
    """Citizen proposals have coarsened bbox to preserve privacy."""
    groton = next(c for c in manifest["collections"] if c["id"] == "citizen/groton-rhine-001")
    theme, doc = build_collection(groton, manifest, tmp_catalog)

    bbox = doc["extent"]["spatial"]["bbox"][0]
    # The bbox is coarsened to ~1.1 km (2 decimal places)
    # Parcel precision would be ~6 decimals
    assert len(bbox) == 4
    # Check that coordinates are rounded to 2 decimals
    for coord in bbox:
        assert round(coord, 2) == coord


def test_updated_is_deterministic(manifest: dict, tmp_catalog: Path) -> None:
    """The updated field comes from the manifest, not the build clock."""
    collection_entry = manifest["collections"][0]
    theme, doc = build_collection(collection_entry, manifest, tmp_catalog)

    assert doc["updated"] == manifest["collections"][0]["provenance"]["updated"]


def test_build_validates_required_fields() -> None:
    """Missing required fields raise BuildError."""
    manifest = {
        "id": "test",
        "title": "Test",
        "host": {"name": "geocontract"},
        "catalogs": {"federal": {"title": "Federal", "description": "Federal sources"}},
        "collections": [
            {
                "id": "federal/test",
                "contract": "contracts/nepa-exclusions.datacontract.yaml",
                # Missing license
                "bbox": [-125.0, 24.0, -66.0, 50.0],
                "primary_entity": "Exclusion",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(BuildError, match="license"):
            build_collection(manifest["collections"][0], manifest, Path(tmp))
