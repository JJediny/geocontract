# Portolan Catalog Integration - Complete

## Summary

All 5 phases of the Portolan catalog integration have been successfully implemented.

## Phases Completed

### ✅ Phase 0: Foundation
- Submodule registration for portolan-skills
- Toolchain pins (rashid 0.1.8, portolan-cli 0.8.0)
- Conformance documentation with 8 probe findings (F1-F8)

### ✅ Phase 1: Catalog Generation
- Manifest-driven catalog generator
- 3 collections: federal/nepa-exclusions, federal/pic-nepa-data-standard, citizen/groton-rhine-001
- Catalog validates: 0 errors, 0 warnings
- 16 tests passing

### ✅ Phase 2: Publishing & CI
- `tools/publish.py` with dry-run/confirm pattern
- GitHub Actions workflow for validation
- S3 publishing configuration

### ✅ Phase 3: Federated Harvesting
- Multi-source fetch (local, HTTP, git, S3)
- Mirror collection generation with provenance tracking
- 20 tests passing

### ✅ Phase 4: Citizen Proposals
- Citizen proposal detection via `isCitizenInitiated` custom property
- Bbox coarsening for privacy (2 decimal places ≈ 1.1km)
- Public projection enforcement (EPSG:4326)
- **Critical fix**: Bbox extraction now uses `_find_project_root()` marker file search instead of hardcoded paths, resolving the issue where extraction failed in installed package contexts

### ✅ Phase 5: Documentation
- Comprehensive integration guide (`docs/portolan-integration-guide.md`)
- Documents all catalog operations: consumption, publishing, contribution
- Covers all three collection types: federal, mirror, citizen
- Updated AGENTS.md with new skill map entries

## Key Technical Achievements

1. **Robust Project Root Detection**: The `_find_project_root()` function searches for `pyproject.toml` marker file, working correctly regardless of package installation location (source vs site-packages).

2. **Privacy-Preserving Citizen Proposals**: Citizen proposal bboxes are coarsened to 2 decimal places, protecting sensitive location data while maintaining utility.

3. **Federated Architecture**: The harvester supports multiple source types and maintains provenance tracking for mirrored catalogs.

4. **Validation Gates**: Both ODCS (contract) and rashid (catalog) validators must pass with 0 errors, 0 warnings before any merge.

## File Structure

```
geocontract/
├── catalog/
│   ├── catalog.json              # Root catalog
│   ├── federal/                  # Official government contracts
│   │   ├── nepa-exclusions/
│   │   └── pic-nepa-data-standard/
│   ├── citizen/                  # Community proposals (coarsened bbox)
│   │   └── groton-rhine-001/
│   └── mirror/                   # Harvested from external catalogs
├── contracts/                    # Source contracts (ODCS v3.1.0)
├── examples/                     # Parcel geometries for citizen proposals
├── docs/
│   ├── portolan-integration-guide.md  # Complete usage guide
│   └── plan-portolan-catalog-integration.md
├── src/geocontract_tools/
│   ├── harvester.py              # Multi-source harvester
│   └── portolan_sink.py          # STAC collection generator
└── tools/
    └── publish.py                # S3 publishing script
```

## Usage

### Consuming the Catalog

```bash
# Install rashid CLI
uv tool install portolan-cli

# Search the catalog
rashid search --catalog https://geocontract.example.org/catalog.json

# Get a specific collection
rashid collection get federal/nepa-exclusions
```

### Publishing the Catalog

```bash
# Dry run (validate only)
mise run publish

# Publish to production (requires S3 credentials)
mise run publish-confirm
```

### Contributing Contracts

1. **Federal**: Create contract in `contracts/`, add metadata to `catalog/manifests/geocontract.yaml`
2. **Citizen**: Add `isCitizenInitiated: true` to customProperties, include parcel geometry
3. **Mirror**: Add external catalog to `catalog/manifests/geocontract.yaml` mirrors section

### Validation

```bash
mise run validate-odcs    # ODCS v3.1.0 contract validation
mise run catalog-check    # rashid catalog validation
```

Both must show 0 errors, 0 warnings.

## Testing

```bash
# Run all tests
uv run pytest scripts/tests/ -v

# Expected: All tests passing
```

## Skills

The following agent skills are available:

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

## Architecture

The integration follows a layered architecture:

1. **Contracts Layer**: ODCS v3.1.0 data contracts in `contracts/`
2. **Harvester Layer**: Multi-source fetch and routing in `src/geocontract_tools/harvester.py`
3. **Sink Layer**: STAC collection generation in `src/geocontract_tools/portolan_sink.py`
4. **Catalog Layer**: Generated STAC catalog in `catalog/`
5. **Publishing Layer**: S3 publishing in `tools/publish.py`

## Conformance

The catalog conforms to:
- Portolan specification (ground truth: portolan-sdi/portolan-spec)
- ODCS v3.1.0 for data contracts
- STAC specification for catalog structure

See `docs/portolan-conformance-notes.md` for detailed conformance findings.

## Next Steps

The Portolan catalog integration is complete. Future enhancements could include:

1. **Advanced Harvesting**: Incremental harvesting, delta detection
2. **Search Optimization**: Full-text search, faceted filtering
3. **Access Control**: Authentication and authorization for restricted collections
4. **Monitoring**: Catalog health checks, harvest status dashboards
5. **Automation**: Scheduled harvesting, automated validation

## References

- [Portolan Specification](https://github.com/portolan-sdi/portolan-spec)
- [Portolan CLI](https://github.com/portolan-sdi/portolan-cli)
- [Implementation Plan](docs/plan-portolan-catalog-integration.md)
- [Integration Guide](docs/portolan-integration-guide.md)
- [Conformance Notes](docs/portolan-conformance-notes.md)
