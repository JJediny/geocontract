"""Portolan sink for the federated harvester.

Writes harvested contracts as mirror collections under catalog/mirror/.
Each harvested source becomes a Portolan mirror collection with:

- producer = upstream (from contract metadata)
- host = geocontract
- via link = upstream landing page (text/html)
- canonical link = upstream STAC catalog (if exists)
- updated = harvest timestamp
- source-role asset = upstream contract/data with checksum

This implements Phase 3 of docs/plan-portolan-catalog-integration.md.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from geocontract_tools.harvester import HarvestError, HarvestResult

# STAC extension URIs (must match build_catalog.py)
PORTOLAN_PROFILE = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
FILE_EXT = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"

# Column type mapping (must match build_catalog.py)
COLUMN_TYPES = {
    "string": "varchar",
    "integer": "bigint",
    "number": "double",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "timestamp",
    "time": "time",
    "object": "struct",
    "array": "list",
}


def slugify(s: str) -> str:
    """Convert a string to a valid Portolan collection ID slug.

    Lowercase, replace non-alphanumeric with hyphens, collapse multiple hyphens.
    """
    import re

    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s


def compute_multihash_sha256(data: bytes) -> str:
    """Compute multihash SHA-256 checksum (0x12 0x20 prefix + hex digest)."""
    digest = hashlib.sha256(data).hexdigest()
    return f"1220{digest}"


def extract_table_columns(contract: dict) -> list[dict]:
    """Extract table:columns from contract schema.

    Uses the first schema entity's properties. If multiple entities exist,
    we could extend this to merge or pick a primary entity, but for now
    we use the first one as the representative schema.
    """
    schema = contract.get("schema") or []
    if not schema:
        return []

    # Use first entity
    entity = schema[0]
    properties = entity.get("properties") or []

    columns = []
    for prop in properties:
        name = prop.get("name")
        if not name:
            continue

        logical_type = prop.get("logicalType", "string")
        col_type = COLUMN_TYPES.get(logical_type, "varchar")
        description = prop.get("description", f"Field {name}")

        columns.append({
            "name": name,
            "type": col_type,
            "description": description,
        })

    return columns


def build_mirror_collection(
    result: HarvestResult,
    harvest_timestamp: str,
    catalog_host: dict | None = None,
) -> dict:
    """Build a Portolan mirror collection.json from a harvest result.

    Args:
        result: The harvest result.
        harvest_timestamp: ISO 8601 timestamp of the harvest.
        catalog_host: Optional host provider info.

    Returns:
        A dict representing the collection.json content.
    """
    contract = result.contract
    source_info = result.source_info

    # Extract contract metadata
    contract_id = contract.get("id", "unknown")
    contract_name = contract.get("name", contract_id)
    contract_version = contract.get("version", "0.0.0")
    
    # Convert ODCS description object to string (Portolan requires string)
    contract_description = contract.get("description", "")
    if isinstance(contract_description, dict):
        # ODCS format: {purpose, usage, limitations}
        # Use purpose as the main description
        contract_description = contract_description.get("purpose", contract_name)
    contract_description = str(contract_description).strip()

    # Build slug from contract id
    slug = slugify(contract_id)
    collection_id = f"mirror/{slug}"

    # Provider: upstream is producer, geocontract is host
    upstream_name = source_info.get("upstream_name", "Unknown Upstream")
    upstream_url = source_info.get("upstream_url", "")
    canonical_url = source_info.get("canonical_url")

    producer = {
        "name": upstream_name,
        "roles": ["producer"],
    }
    if upstream_url:
        producer["url"] = upstream_url

    # Host provider (defaults to geocontract)
    if catalog_host is None:
        catalog_host = {
            "name": "geocontract",
            "url": "https://github.com/JJediny/geocontract",
            "email": "permits@innovation.gov",
        }

    host = dict(catalog_host)
    host["roles"] = ["host"]

    providers = [producer, host]

    # Via link (required for mirrors)
    via_url = source_info.get("via_url", upstream_url)
    if not via_url:
        raise HarvestError(
            f"Mirror collection for {contract_id} requires a via URL. "
            f"Set upstream_url or via_url in source metadata."
        )

    # Bbox: use upstream bbox if provided, otherwise default to global
    # (This is a tabular/non-spatial collection, so bbox is area of interest)
    upstream_bbox = source_info.get("bbox")
    if upstream_bbox:
        bbox = [upstream_bbox]
    else:
        # Default to global extent for unknown area of interest
        bbox = [[-180.0, -90.0, 180.0, 90.0]]

    # Extract table columns
    table_columns = extract_table_columns(contract)

    # Keywords from contract tags
    keywords = contract.get("tags", [])

    # Build source asset metadata
    source_data = result.source_data
    source_filename = source_info.get("source_filename", f"{slug}.datacontract.yaml")

    source_asset = {
        "href": f"./{source_filename}",
        "type": "application/yaml",
        "title": f"Source contract: {contract_name}",
        "roles": ["source"],
        "file:size": len(source_data),
        "file:checksum": compute_multihash_sha256(source_data),
    }

    # Build links
    links = [
        {"rel": "root", "href": "../../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {
            "rel": "via",
            "href": via_url,
            "type": "text/html",
            "title": "Original source",
        },
        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
        {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
    ]

    # Add canonical link if upstream has a STAC catalog
    if canonical_url:
        links.append({
            "rel": "canonical",
            "href": canonical_url,
            "type": "application/json",
            "title": "Upstream STAC catalog",
        })

    # Build collection.json
    collection = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_PROFILE, FILE_EXT, TABLE_EXT],
        "id": collection_id,
        "title": f"Mirror: {contract_name}",
        "description": contract_description or f"Mirror of {contract_name} from {upstream_name}",
        "license": "CC0-1.0",  # Default; can be overridden via source metadata
        "keywords": keywords,
        "providers": providers,
        "extent": {
            "spatial": {"bbox": bbox},
            "temporal": {"interval": [[harvest_timestamp, None]]},
        },
        "table:columns": table_columns,
        "assets": {
            "source": source_asset,
        },
        "links": links,
        "updated": harvest_timestamp,
        # Custom properties
        "geocontract:contract_id": contract_id,
        "geocontract:contract_version": contract_version,
        "geocontract:status": contract.get("status", "unknown"),
        "geocontract:tenant": contract.get("tenant", "unknown"),
        "geocontract:domain": contract.get("domain", "unknown"),
        "geocontract:mirror": True,
        "geocontract:harvested_from": source_info.get("source_url", "unknown"),
        "geocontract:harvested_at": harvest_timestamp,
    }

    return collection


def write_mirror_collection(
    result: HarvestResult,
    catalog_dir: Path,
    harvest_timestamp: str,
    catalog_host: dict | None = None,
) -> Path:
    """Write a mirror collection to the catalog directory.

    Args:
        result: The harvest result.
        catalog_dir: Path to the catalog/ directory.
        harvest_timestamp: ISO 8601 timestamp of the harvest.
        catalog_host: Optional host provider info.

    Returns:
        Path to the written collection.json.
    """
    contract_id = result.contract.get("id", "unknown")
    slug = slugify(contract_id)

    # Create collection directory
    collection_dir = catalog_dir / "mirror" / slug
    collection_dir.mkdir(parents=True, exist_ok=True)

    # Build collection.json
    collection = build_mirror_collection(result, harvest_timestamp, catalog_host)

    # Write collection.json
    collection_path = collection_dir / "collection.json"
    collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")

    # Write source contract file
    source_filename = result.source_info.get("source_filename", f"{slug}.datacontract.yaml")
    source_path = collection_dir / source_filename
    source_path.write_bytes(result.source_data)

    # Write README.md if not exists
    readme_path = collection_dir / "README.md"
    if not readme_path.exists():
        upstream_name = result.source_info.get("upstream_name", "Unknown Upstream")
        via_url = result.source_info.get("via_url", result.source_info.get("upstream_url", ""))
        license_id = collection.get("license", "CC0-1.0")
        readme_content = f"""# Mirror: {collection['title']}

Mirrored from {upstream_name}.

## Provenance

Harvested from {result.source_info.get('source_url', 'unknown source')} on {harvest_timestamp}.

Original source: [{via_url}]({via_url})

## Contract

This collection mirrors the `{contract_id}` contract (version {collection['geocontract:contract_version']}).

See `source` asset for the full contract YAML.

## License

{license_id}. See the source contract for full license terms.
"""
        readme_path.write_text(readme_content, encoding="utf-8")

    # Write AGENTS.md if not exists
    agents_path = collection_dir / "AGENTS.md"
    if not agents_path.exists():
        agents_content = f"""# Agent Guidance, {collection['title']}

This is a mirror collection harvested from an upstream source.

## Source

- Upstream: {result.source_info.get('upstream_name', 'Unknown')}
- Harvested: {harvest_timestamp}
- Source URL: {result.source_info.get('source_url', 'unknown')}

## Data

The `source` asset contains the original contract YAML. This is a metadata-only
mirror; the actual data (if any) lives at the upstream source.
"""
        agents_path.write_text(agents_content, encoding="utf-8")

    return collection_path


def update_mirror_catalog(catalog_dir: Path) -> None:
    """Update the mirror catalog.json with child links to all collections.
    
    Scans catalog/mirror/ for collection directories and adds child links
    for each collection.json found.
    """
    mirror_dir = catalog_dir / "mirror"
    catalog_path = mirror_dir / "catalog.json"
    
    if not catalog_path.exists():
        return
    
    catalog = json.loads(catalog_path.read_text())
    links = catalog.get("links", [])
    
    # Remove existing child links
    links = [link for link in links if link.get("rel") != "child"]
    
    # Scan for collections and add child links
    for collection_dir in sorted(mirror_dir.iterdir()):
        if collection_dir.is_dir():
            collection_json = collection_dir / "collection.json"
            if collection_json.exists():
                collection = json.loads(collection_json.read_text())
                links.append({
                    "rel": "child",
                    "href": f"./{collection_dir.name}/collection.json",
                    "type": "application/json",
                    "title": collection.get("title", collection_dir.name),
                })
    
    catalog["links"] = links
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


def ensure_mirror_catalog(catalog_dir: Path) -> Path:
    """Ensure the mirror sub-catalog exists.

    Creates catalog/mirror/catalog.json if it doesn't exist.

    Returns:
        Path to the mirror catalog.json.
    """
    mirror_dir = catalog_dir / "mirror"
    mirror_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = mirror_dir / "catalog.json"
    if not catalog_path.exists():
        catalog = {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "stac_extensions": [PORTOLAN_PROFILE],
            "id": "mirror",
            "title": "Harvested Mirrors",
            "description": "Mirror collections harvested from external geocontract sources.",
            "links": [
                {"rel": "root", "href": "../catalog.json", "type": "application/json"},
                {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
                {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
                {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
            ],
            "updated": datetime.now().isoformat() + "Z",
        }
        catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

        # Write README.md
        readme_path = mirror_dir / "README.md"
        if not readme_path.exists():
            readme_content = """# Harvested Mirrors

Mirror collections harvested from external geocontract sources.

Each collection mirrors a contract from an upstream source. The upstream
is the producer; geocontract is the host.
"""
            readme_path.write_text(readme_content, encoding="utf-8")

        # Write AGENTS.md
        agents_path = mirror_dir / "AGENTS.md"
        if not agents_path.exists():
            agents_content = """# Agent Guidance, Harvested Mirrors

This sub-catalog contains mirror collections harvested from external sources.

## Structure

Each mirror collection has:
- `collection.json`: STAC collection with mirror metadata
- `source` asset: The original contract YAML
- `README.md`: Human-readable description
- `AGENTS.md`: Agent guidance

## Harvesting

Mirrors are created by the federated harvester:

```bash
uv run geocontract-harvest --sink portolan <source-url>
```

See `docs/design-harvester.md` for details.
"""
            agents_path.write_text(agents_content, encoding="utf-8")

    return catalog_path


def update_root_catalog(catalog_dir: Path) -> None:
    """Update the root catalog.json to include the mirror sub-catalog.

    Adds a child link to catalog/mirror/catalog.json if not already present.
    """
    root_catalog_path = catalog_dir / "catalog.json"
    if not root_catalog_path.exists():
        return

    root_catalog = json.loads(root_catalog_path.read_text())
    links = root_catalog.get("links", [])

    # Check if mirror child link exists
    mirror_link_exists = any(
        link.get("rel") == "child" and "mirror/catalog.json" in link.get("href", "")
        for link in links
    )

    if not mirror_link_exists:
        links.append({
            "rel": "child",
            "href": "./mirror/catalog.json",
            "type": "application/json",
            "title": "Harvested Mirrors",
        })
        root_catalog["links"] = links
        root_catalog_path.write_text(json.dumps(root_catalog, indent=2) + "\n", encoding="utf-8")
