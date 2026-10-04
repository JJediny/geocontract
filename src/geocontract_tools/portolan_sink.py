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
from datetime import UTC, datetime
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


def write_citizen_collection(
    result: Any,
    catalog_dir: Path,
    harvest_timestamp: str,
    catalog_host: dict | None = None,
) -> Path:
    """Write a citizen proposal collection to the catalog directory.
    
    Citizen proposals are official collections (not mirrors) that geocontract
    originates. They have coarsened bbox for privacy and public projection only.
    
    Args:
        result: The harvest result with contract and source info.
        catalog_dir: Path to the catalog/ directory.
        harvest_timestamp: ISO 8601 timestamp of the harvest.
        catalog_host: Optional host provider info.
    
    Returns:
        Path to the written collection.json.
    """
    contract = result.contract
    source_info = result.source_info
    
    # Extract contract metadata
    contract_id = contract.get("id", "unknown")
    contract_name = contract.get("name", contract_id)
    contract_version = contract.get("version", "0.0.0")
    
    # Convert ODCS description to string
    contract_description = contract.get("description", "")
    if isinstance(contract_description, dict):
        contract_description = contract_description.get("purpose", contract_name)
    contract_description = str(contract_description).strip()
    
    # Build slug from contract id
    slug = slugify(contract_id)
    collection_id = f"citizen/{slug}"
    
    # Host provider (defaults to geocontract)
    if catalog_host is None:
        catalog_host = {
            "name": "geocontract",
            "url": "https://github.com/JJediny/geocontract",
            "email": "permits@innovation.gov",
        }
    
    host = dict(catalog_host)
    host["roles"] = ["producer", "licensor", "host"]
    
    providers = [host]
    
    # Extract jurisdiction and access class
    jurisdiction = source_info.get("jurisdiction", "")
    access_class = source_info.get("access_class", "public")
    
    # Bbox coarsening for privacy (2 decimal places = ~1.1km precision)
    # Extract bbox from contract if available, otherwise use default
    bbox = _extract_bbox(contract)
    coarsened_bbox = _coarsen_bbox(bbox)
    
    # Extract table columns
    columns = extract_table_columns(contract)
    
    # Keywords from contract tags
    keywords = contract.get("tags", [])
    
    # Build contract asset
    contract_filename = f"{slug}.datacontract.yaml"
    contract_asset = {
        "href": f"./{contract_filename}",
        "type": "application/yaml",
        "title": f"ODCS v3.1.0 data contract ({contract_id})",
        "roles": ["metadata"],
        "file:size": len(result.source_data),
        "file:checksum": compute_multihash_sha256(result.source_data),
    }
    
    # Build links (no via link for official collections)
    links = [
        {"rel": "root", "href": "../../catalog.json", "type": "application/json"},
        {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
        {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
        {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
    ]
    
    # Build collection.json
    collection = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_PROFILE, FILE_EXT, TABLE_EXT],
        "id": collection_id,
        "title": contract_name,
        "description": contract_description,
        "license": "CC0-1.0",
        "keywords": keywords,
        "providers": providers,
        "extent": {
            "spatial": {"bbox": [coarsened_bbox]},
            "temporal": {"interval": [[harvest_timestamp, None]]},
        },
        "table:columns": columns,
        "assets": {
            "contract": contract_asset,
        },
        "links": links,
        "updated": harvest_timestamp,
        # Custom properties
        "geocontract:contract_id": contract_id,
        "geocontract:contract_version": contract_version,
        "geocontract:status": contract.get("status", "unknown"),
        "geocontract:tenant": contract.get("tenant", "unknown"),
        "geocontract:domain": contract.get("domain", "unknown"),
        "geocontract:mirror": False,
        "geocontract:jurisdiction": jurisdiction,
        "geocontract:access_class": access_class,
        "geocontract:is_citizen_proposal": True,
    }
    
    # Create collection directory
    collection_dir = catalog_dir / "citizen" / slug
    collection_dir.mkdir(parents=True, exist_ok=True)
    
    # Write collection.json
    collection_path = collection_dir / "collection.json"
    collection_path.write_text(json.dumps(collection, indent=2) + "\n", encoding="utf-8")
    
    # Write contract file
    contract_path = collection_dir / contract_filename
    contract_path.write_bytes(result.source_data)
    
    # Write README.md if not exists
    readme_path = collection_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"""# {contract_name}

{contract_description}

## Jurisdiction

{jurisdiction}

## Access

This is a citizen-initiated proposal with {access_class} access.

## Contract

See `contract` asset for the full ODCS v3.1.0 data contract.

## Provenance

Data originates from a citizen-initiated permit proposal submitted to
the local permitting intake. The harvest timestamp and source URL are
recorded in the collection's `provenance` block. Bounding-box
coordinates are coarsened to two decimal places (~1.1 km) before
publishing.

## License

CC0-1.0. See the contract for full terms.
"""
        readme_path.write_text(readme_content, encoding="utf-8")
    
    # Write AGENTS.md if not exists
    agents_path = collection_dir / "AGENTS.md"
    if not agents_path.exists():
        agents_content = f"""# Agent Guidance, {contract_name}

This is a citizen-initiated proposal originated by geocontract.

## Metadata

- Contract ID: {contract_id}
- Version: {contract_version}
- Jurisdiction: {jurisdiction}
- Access Class: {access_class}

## Data

The `contract` asset contains the ODCS v3.1.0 data contract. This is the public
projection only. Restricted projections (if any) are not published.

## Privacy

The bbox has been coarsened to ~1.1km precision to protect citizen privacy.
"""
        agents_path.write_text(agents_content, encoding="utf-8")
    
    return collection_path


def ensure_citizen_catalog(catalog_dir: Path) -> Path:
    """Ensure the citizen sub-catalog exists.
    
    Creates catalog/citizen/catalog.json if it doesn't exist.
    
    Returns:
        Path to the citizen catalog.json.
    """
    citizen_dir = catalog_dir / "citizen"
    citizen_dir.mkdir(parents=True, exist_ok=True)
    
    catalog_path = citizen_dir / "catalog.json"
    if not catalog_path.exists():
        catalog = {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "stac_extensions": [PORTOLAN_PROFILE],
            "id": "citizen",
            "title": "Citizen-Initiated Proposals",
            "description": "Official collections for citizen-initiated proposals originated by geocontract.",
            "links": [
                {"rel": "root", "href": "../catalog.json", "type": "application/json"},
                {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
                {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
                {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
            ],
            "updated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        
        # Write README.md
        readme_path = citizen_dir / "README.md"
        if not readme_path.exists():
            readme_content = """# Citizen-Initiated Proposals

Official collections for citizen-initiated proposals originated by geocontract.

These are not mirrors; geocontract is the producer and host. Bbox values are
coarsened to protect citizen privacy.
"""
            readme_path.write_text(readme_content, encoding="utf-8")
        
        # Write AGENTS.md
        agents_path = citizen_dir / "AGENTS.md"
        if not agents_path.exists():
            agents_content = """# Agent Guidance, Citizen-Initiated Proposals

This sub-catalog contains official collections for citizen-initiated proposals.

## Structure

Each citizen collection has:
- `collection.json`: STAC collection with proposal metadata
- `contract` asset: The ODCS v3.1.0 data contract
- `README.md`: Human-readable description
- `AGENTS.md`: Agent guidance

## Privacy

All bbox values are coarsened to ~1.1km precision. Only public projections
are published. Restricted projections (if any) are never published.
"""
            agents_path.write_text(agents_content, encoding="utf-8")
    
    return catalog_path


def update_citizen_catalog(catalog_dir: Path) -> None:
    """Update the citizen catalog.json with child links to all collections.
    
    Scans catalog/citizen/ for collection directories and adds child links
    for each collection.json found.
    """
    citizen_dir = catalog_dir / "citizen"
    catalog_path = citizen_dir / "catalog.json"
    
    if not catalog_path.exists():
        return
    
    catalog = json.loads(catalog_path.read_text())
    links = catalog.get("links", [])
    
    # Remove existing child links
    links = [link for link in links if link.get("rel") != "child"]
    
    # Scan for collections and add child links
    for collection_dir in sorted(citizen_dir.iterdir()):
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


def _find_project_root() -> "Path | None":
    """Find project root by searching for pyproject.toml marker file."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback to current working directory
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    return None


def _extract_bbox(contract: dict) -> list[float]:
    """Extract bbox from contract or associated proposal data.

    For citizen proposals, tries to load the example data file and extract
    geometry from proposal.parcel.geometry (WKT POLYGON).

    Returns [west, south, east, north] or default global bbox.
    """
    import json
    import re
    from pathlib import Path

    contract_id = contract.get("id", "")

    # Use project root to find examples directory
    # Find project root using marker file search (works in installed packages)
    project_root = _find_project_root()
    if not project_root:
        return [-180.0, -90.0, 180.0, 90.0]
    examples_dir = project_root / "examples"

    if examples_dir.exists():
        # Look for example data file matching contract id
        for example_file in examples_dir.glob("*.example.data.json"):
            if contract_id in example_file.stem:
                try:
                    with open(example_file) as f:
                        data = json.load(f)

                    # Extract geometry from proposal.parcel.geometry (WKT)
                    geometry_wkt = None
                    if "proposal" in data and "parcel" in data["proposal"]:
                        geometry_wkt = data["proposal"]["parcel"].get("geometry")

                    if geometry_wkt and geometry_wkt.startswith("POLYGON"):
                        # Parse WKT POLYGON to extract coordinates
                        # Format: POLYGON((x1 y1, x2 y2, ...))
                        coords_str = re.search(r'POLYGON\(\(([^)]+)\)\)', geometry_wkt)
                        if coords_str:
                            coords = []
                            for point in coords_str.group(1).split(','):
                                x, y = map(float, point.strip().split())
                                coords.append((x, y))

                            if coords:
                                xs = [c[0] for c in coords]
                                ys = [c[1] for c in coords]
                                return [min(xs), min(ys), max(xs), max(ys)]
                except Exception as e:
                    # Extraction failure must not vanish silently: log it so
                    # a bad example file or WKT is visible to the operator.
                    import sys
                    print(
                        f"warning: failed to extract bbox from {example_file}: {e}",
                        file=sys.stderr,
                    )

    # Default global bbox (will be coarsened)
    return [-180.0, -90.0, 180.0, 90.0]


def _coarsen_bbox(bbox: list[float]) -> list[float]:
    """Coarsen bbox to 2 decimal places for privacy (~1.1km precision).
    
    Uses floor for west/south and ceil for east/north to ensure the coarsened
    bbox still encompasses the original geometry.
    """
    import math
    
    return [
        math.floor(bbox[0] * 100) / 100,  # west (floor)
        math.floor(bbox[1] * 100) / 100,  # south (floor)
        math.ceil(bbox[2] * 100) / 100,   # east (ceil)
        math.ceil(bbox[3] * 100) / 100,   # north (ceil)
    ]
