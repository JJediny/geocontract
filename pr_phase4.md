# Phase 4 PR: Citizen Proposals Integration

## What changed

Adds citizen proposal integration to the Portolan catalog (Phase 4).

- Detects citizen-initiated contracts via `isCitizenInitiated` custom property
- Routes citizen proposals to `catalog/citizen/` (not mirrors)
- Implements bbox coarsening for privacy (2 decimal places ≈ 1.1km precision)
- Enforces public projection (EPSG:4326) for citizen collections
- Fixes bbox extraction to work in installed package context

## Why

Citizen proposals contain sensitive location data that must be coarsened
for privacy before publication. The catalog needs to distinguish between
official collections (federal) and citizen proposals, applying different
rules to each.

The bbox extraction was failing in installed package contexts because it
used `Path(__file__).parent.parent.parent`, which resolves to site-packages
when the package is installed. This fix uses marker file search (pyproject.toml)
to find the project root reliably.

## Verification

```bash
# Test bbox extraction
$ python3 test_bbox_fix.py
✓ SUCCESS: Bbox extraction works correctly!

# Harvest with citizen proposal detection
$ uv run python -m geocontract_tools.harvester --source contracts/ --catalog-dir catalog/ --portolan

# Verify bbox is coarsened (not global default)
$ cat catalog/citizen/groton-rhine-001/collection.json | jq '.extent.spatial.bbox'
[
  [
    -72.09,
    41.34,
    -72.08,
    41.35
  ]
]

# Validate catalog
$ mise run catalog-check
✓ catalog validates: 0 errors, 0 warnings

# Run tests
$ uv run pytest scripts/tests/test_harvester_portolan.py -v
✓ 20 passed
```

Catalog path: `catalog/citizen/groton-rhine-001/collection.json`

## Checklist

- [x] Citizen proposal detection implemented
- [x] Bbox coarsening for privacy (2 decimal places)
- [x] Public projection enforcement (EPSG:4326)
- [x] Bbox extraction fix for installed package context
- [x] Catalog validates with 0 errors, 0 warnings
- [x] All tests pass
- [ ] Human review and approval required before merge
