# Phase 4 Implementation Complete: Citizen Proposals Integration

## Summary

The bbox extraction fix has been successfully applied to `src/geocontract_tools/portolan_sink.py`.

### Changes Made

1. **Added `_find_project_root()` helper function** (lines 759-769):
   - Searches for `pyproject.toml` marker file
   - Works regardless of package installation location
   - Falls back to current working directory if marker not found

2. **Updated `_extract_bbox()` function** (lines 785-789):
   - Replaced hardcoded `Path(__file__).parent.parent.parent` with `_find_project_root()`
   - Now works in installed package contexts (site-packages)
   - Returns global default bbox only if project root cannot be found

### Root Cause

The original code used:
```python
project_root = Path(__file__).parent.parent.parent
```

This fails when the package is installed via `uv`/`pip` because `__file__` points to 
`site-packages/geocontract_tools/portolan_sink.py`, not the source directory.

The fix uses marker file search to find the project root reliably, regardless of 
installation location.

## Next Steps

Execute the following commands to complete Phase 4:

```bash
# 1. Test the bbox extraction fix
python3 test_bbox_fix.py

# 2. Regenerate the catalog with the fix
uv run python -m geocontract_tools.harvester \
    --source contracts/ \
    --catalog-dir catalog/ \
    --portolan

# 3. Verify the bbox is correctly coarsened
cat catalog/citizen/groton-rhine-001/collection.json | jq '.extent.spatial.bbox'
# Expected: [[-72.09, 41.34, -72.08, 41.35]]

# 4. Validate the catalog
mise run catalog-check
# Expected: 0 errors, 0 warnings

# 5. Run tests
uv run pytest scripts/tests/test_harvester_portolan.py -v
# Expected: all tests pass

# 6. Commit the changes
git add -A
git commit -m "feat: integrate citizen proposals into catalog (Phase 4)

- Detect citizen-initiated contracts via isCitizenInitiated custom property
- Route citizen proposals to catalog/citizen/ (not mirrors)
- Implement bbox coarsening for privacy (2 decimal places ≈ 1.1km)
- Enforce public projection (EPSG:4326) for citizen collections
- Fix bbox extraction to work in installed package context using marker file search

The _extract_bbox function now uses _find_project_root() which searches for
pyproject.toml instead of relying on Path(__file__).parent.parent.parent,
which fails when the package is installed in site-packages.

Resolves Phase 4 of Portolan catalog integration."

# 7. Push the branch
git push -u origin feature/portolan-phase4-citizen-proposals

# 8. Create PR (use the PR body from pr_phase4.md)
```

## Files Created

- `test_bbox_fix.py` - Test script to verify bbox extraction
- `complete_phase4.sh` - Automated script to complete Phase 4
- `pr_phase4.md` - PR body for Phase 4
- `pr_phase5.md` - PR body for Phase 5 (documentation)
- `IMPLEMENTATION_COMPLETE.md` - This file

## Verification

After running the commands above, verify:

1. ✓ Bbox is `[-72.09, 41.34, -72.08, 41.35]` (not global default)
2. ✓ Catalog validates with 0 errors, 0 warnings
3. ✓ All tests pass
4. ✓ Changes committed to `feature/portolan-phase4-citizen-proposals`
