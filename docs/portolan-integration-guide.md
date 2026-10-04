# Portolan Catalog Integration Guide

This guide explains how to use geocontract's Portolan-compliant catalog for publishing, consuming, and contributing data contracts.

## Overview

The geocontract catalog publishes data contracts as STAC collections following the [Portolan specification](https://github.com/portolan-sdi/portolan-spec).

The catalog contains three types of collections:

1. **Federal collections** (`catalog/federal/`): Official government data contracts
2. **Mirror collections** (`catalog/mirror/`): Harvested from external Portolan catalogs  
3. **Citizen proposals** (`catalog/citizen/`): Community-initiated contracts with privacy protections

## Consuming the Catalog

### Using rashid CLI

Install the Portolan CLI:

```bash
uv tool install portolan-cli
```

Search the catalog:

```bash
rashid search --catalog https://geocontract.example.org/catalog.json
```

Get a specific collection:

```bash
rashid collection get federal/nepa-exclusions
```

### Using Python

```python
import requests

catalog_url = "https://geocontract.example.org/catalog.json"
response = requests.get(catalog_url)
catalog = response.json()

# List collections
for link in catalog["links"]:
    if link["rel"] == "child":
        print(link["title"])
```

## Publishing the Catalog

The catalog is published via CI/CD or manually to S3.

### Dry Run (Validate Only)

```bash
mise run publish
```

This validates the catalog and shows what would be published without actually uploading.

### Publish to Production

```bash
mise run publish-confirm
```

This requires AWS S3 credentials configured in your environment.

### Configuration

Edit `catalog.publish.yaml` to configure:

- `destination`: S3 bucket URL (e.g., `s3://geocontract-catalog/`)
- `public_base`: Public URL where catalog is accessible
- `region`: AWS region
- `profile`: AWS credentials profile (optional)

### Publishing Rules

- **Validate first**: The publish script runs `rashid check` before uploading
- **Never delete manually**: Removing files from `catalog/` doesn't remove them from S3
- **Change detection**: Files are uploaded only if size or checksum differs
- **Relative vs absolute links**: Keep structural links relative in git; the published root gets an absolute `self` link

## Contributing Contracts

### Federal Contracts

1. Create contract in `contracts/` directory following ODCS v3.1.0 format
2. Add metadata to `catalog/manifests/geocontract.yaml`:
   ```yaml
   collections:
     - id: my-contract
       title: "My Contract Title"
       description: "Description of the contract"
       license: "CC0-1.0"
       bbox: [-180, -90, 180, 90]
   ```
3. Run catalog build:
   ```bash
   mise run catalog-build
   ```
4. Validate:
   ```bash
   mise run catalog-check
   ```
5. Submit PR

### Citizen Proposals

Citizen proposals contain sensitive location data and require privacy protections.

1. Create contract with `customProperties.isCitizenInitiated: true`:
   ```yaml
   customProperties:
     - property: isCitizenInitiated
       value: true
   ```

2. Include parcel geometry in WKT format in the example data file (`examples/my-proposal.example.data.json`):
   ```json
   {
     "proposal": {
       "parcel": {
         "geometry": "POLYGON((-72.0821 41.3472, -72.0819 41.3472, ...))"
       }
     }
   }
   ```

3. Submit PR - the harvester will:
   - Detect the citizen proposal via `isCitizenInitiated` flag
   - Route it to `catalog/citizen/` (not mirrors)
   - Coarsen the bbox to 2 decimal places (~1.1km precision) for privacy
   - Enforce EPSG:4326 projection

### Mirroring External Catalogs

Add external Portolan catalogs to mirror in `catalog/manifests/geocontract.yaml`:

```yaml
mirrors:
  - name: example-catalog
    url: https://example.org/catalog.json
    harvest_interval: 24h
```

Then run the harvester:

```bash
uv run python -m geocontract_tools.harvester \
  --source contracts/ \
  --catalog-dir catalog/ \
  --portolan
```

The harvester will:
- Fetch contracts from the source
- Generate STAC collections in `catalog/mirror/`
- Track provenance with `via` links
- Update the mirror catalog

## Validation Gates

Two validators must pass before merge:

### ODCS Validation

```bash
mise run validate-odcs
```

Validates contracts against ODCS v3.1.0 specification. Must show 0 errors, 0 warnings.

### Catalog Validation

```bash
mise run catalog-check
```

Validates the STAC catalog structure using `rashid`. Must show 0 errors, 0 warnings.

Both validators run in CI on every PR and push.

## Architecture

### Components

- **Harvester** (`src/geocontract_tools/harvester.py`): Multi-source contract harvester
- **Portolan Sink** (`src/geocontract_tools/portolan_sink.py`): STAC collection generator
- **Manifest** (`catalog/manifests/geocontract.yaml`): Catalog configuration
- **Publish Script** (`tools/publish.py`): S3 publishing tool
- **Example Data** (`examples/`): Parcel geometries for citizen proposals

### Collection Types

**Federal Collections:**
- Official government data contracts
- Located in `catalog/federal/`
- Full precision bbox
- Direct publication

**Mirror Collections:**
- Harvested from external Portolan catalogs
- Located in `catalog/mirror/`
- Provenance tracked via `via` links
- Updated on harvest schedule

**Citizen Proposals:**
- Community-initiated contracts
- Located in `catalog/citizen/`
- Bbox coarsened for privacy (2 decimal places)
- EPSG:4326 enforced
- Detected via `isCitizenInitiated` custom property

### Data Flow

```
contracts/*.datacontract.yaml
    ↓
harvester.py
    ↓
portolan_sink.py (generates STAC collections)
    ↓
catalog/{federal,mirror,citizen}/*/collection.json
    ↓
publish.py → S3
```

## Troubleshooting

### Bbox Extraction Fails

If bbox extraction returns global default `[-180, -90, 180, 90]` instead of actual coordinates:

1. Verify project root detection:
   ```bash
   python3 -c "
   from pathlib import Path
   import sys
   sys.path.insert(0, 'src')
   from geocontract_tools.portolan_sink import _find_project_root
   root = _find_project_root()
   print(f'Project root: {root}')
   print(f'pyproject.toml exists: {(root / \"pyproject.toml\").exists() if root else False}')
   "
   ```

2. Check that example data file exists and has correct structure:
   ```bash
   cat examples/my-contract.example.data.json | jq '.proposal.parcel.geometry'
   ```

3. Verify contract has matching ID:
   ```bash
   grep '"id"' contracts/my-contract.datacontract.yaml
   ```

### Catalog Validation Fails

Common issues:
- Missing required fields in collection.json
- Invalid bbox coordinates (must be [west, south, east, north])
- Missing links in catalog.json
- Invalid STAC version

Run `mise run catalog-check` to see specific errors.

### Tests Fail

Run with verbose output:
```bash
uv run pytest scripts/tests/ -v
```

Common failures:
- Bbox coarsening logic incorrect
- Missing required STAC fields
- Invalid JSON structure

## Skills

The following agent skills are available for common tasks:

| Task | Skill |
|------|-------|
| Edit and publish the catalog | `skills/git-backed-catalog/` (Mode B) |
| Portolan-ify a new source | `skills/portolan-bootstrap/` |
| Command reference | `skills/portolan-cli/` |
| Bump the pinned spec version | `skills/portolan-migrate/` |
| Publish to Source Cooperative | `skills/sourcecoop/` |
| Register the catalog | `skills/register-catalog/` |
| Report a problem in another catalog | `skills/report-catalog-issue/` |
| Consume a catalog | `skills/reading-portolan/` |
| Harvest external catalogs | `skills/federated-harvest/` |
| Integrate citizen proposals | `skills/citizen-proposals/` |

## Additional Resources

- [Portolan Specification](https://github.com/portolan-sdi/portolan-spec)
- [Implementation Plan](docs/plan-portolan-catalog-integration.md)
- [Conformance Notes](docs/portolan-conformance-notes.md)
- [Portolan CLI Documentation](https://github.com/portolan-sdi/portolan-cli)
