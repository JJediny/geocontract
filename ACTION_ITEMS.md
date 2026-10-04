# Action Items: Complete Portolan Catalog Integration

## Current Status

✅ **Phase 4 Code Fix Applied**
- Added `_find_project_root()` helper function to `src/geocontract_tools/portolan_sink.py`
- Updated `_extract_bbox()` to use marker file search instead of hardcoded path
- Created test script `test_bbox_fix.py`
- Created implementation script `complete_phase4.sh`

⚠️ **Tool Errors Encountered**
- Persistent "tool input was not fully received" errors prevented automated execution
- Manual execution required for remaining steps

---

## PR 1: Phase 4 - Citizen Proposals Integration

**Branch:** `feature/portolan-phase4-citizen-proposals`

### Action Items

1. **Test the bbox extraction fix**
   ```bash
   cd /home/john/geocontract
   python3 test_bbox_fix.py
   ```
   Expected: `✓ SUCCESS: Bbox extraction works correctly!`

2. **Regenerate the catalog**
   ```bash
   uv run python -m geocontract_tools.harvester \
       --source contracts/ \
       --catalog-dir catalog/ \
       --portolan
   ```

3. **Verify bbox is correctly coarsened**
   ```bash
   cat catalog/citizen/groton-rhine-001/collection.json | jq '.extent.spatial.bbox'
   ```
   Expected: `[[-72.09, 41.34, -72.08, 41.35]]`

4. **Validate the catalog**
   ```bash
   mise run catalog-check
   ```
   Expected: `✓ catalog validates: 0 errors, 0 warnings`

5. **Run tests**
   ```bash
   uv run pytest scripts/tests/test_harvester_portolan.py -v
   ```
   Expected: `✓ 20 passed`

6. **Commit changes**
   ```bash
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
   ```

7. **Push branch**
   ```bash
   git push -u origin feature/portolan-phase4-citizen-proposals
   ```

8. **Create PR**
   - Use PR body from `pr_phase4.md`
   - Request review (do not merge yourself)

---

## PR 2: Phase 5 - Documentation & Integration Guide

**Branch:** `feature/portolan-phase5-docs` (create after Phase 4 merges)

### Action Items

1. **Create the integration guide**
   ```bash
   # Create docs/portolan-integration-guide.md with the content from the PR body
   ```

2. **Update AGENTS.md skill map**
   Add these entries to the Skills table:
   ```markdown
   | Harvest external catalogs | `skills/federated-harvest/` |
   | Integrate citizen proposals | `skills/citizen-proposals/` |
   ```

3. **Validate catalog and tests**
   ```bash
   mise run catalog-check
   uv run pytest scripts/tests/ -v
   ```

4. **Commit changes**
   ```bash
   git checkout -b feature/portolan-phase5-docs
   git add -A
   git commit -m "docs: add Portolan catalog integration guide (Phase 5)

   - Create comprehensive integration guide documenting all catalog operations
   - Document consumption, publishing, and contribution workflows
   - Cover all three collection types: federal, mirror, citizen
   - Explain validation gates (ODCS + rashid)
   - Update AGENTS.md with new skill map entries

   Completes Phase 5 of Portolan catalog integration."
   ```

5. **Push branch**
   ```bash
   git push -u origin feature/portolan-phase5-docs
   ```

6. **Create PR**
   - Use PR body from `pr_phase5.md`
   - Request review (do not merge yourself)

---

## Verification Checklist

After both PRs are merged:

- [ ] All 5 phases complete
- [ ] Catalog validates: `mise run catalog-check` shows 0 errors, 0 warnings
- [ ] All tests pass: `uv run pytest scripts/tests/` shows all tests passing
- [ ] Documentation accessible at `docs/portolan-integration-guide.md`
- [ ] Citizen proposals correctly coarsened in `catalog/citizen/`
- [ ] Federal collections in `catalog/federal/`
- [ ] Mirror collections in `catalog/mirror/`

---

## Files Created for You

- `IMPLEMENTATION_COMPLETE.md` - Phase 4 implementation summary
- `test_bbox_fix.py` - Test script to verify bbox extraction
- `complete_phase4.sh` - Automated script to complete Phase 4
- `pr_phase4.md` - PR body for Phase 4
- `pr_phase5.md` - PR body for Phase 5
- `ACTION_ITEMS.md` - This file

---

## Quick Start

If you want to automate as much as possible:

```bash
# Phase 4
chmod +x complete_phase4.sh
./complete_phase4.sh

# Then manually create PR on GitHub using pr_phase4.md

# After Phase 4 merges, create Phase 5
# (documentation creation needs to be manual due to tool errors)
```

---

## Troubleshooting

### Bbox still shows global default

If the bbox is still `[-180, -90, 180, 90]` after running the harvester:

1. Check that `_find_project_root()` is finding the project root:
   ```bash
   python3 -c "
   import sys
   from pathlib import Path
   sys.path.insert(0, 'src')
   from geocontract_tools.portolan_sink import _find_project_root
   root = _find_project_root()
   print(f'Project root: {root}')
   print(f'pyproject.toml exists: {(root / \"pyproject.toml\").exists() if root else False}')
   "
   ```

2. Verify the examples directory exists:
   ```bash
   ls -la examples/
   ```

3. Check that `groton-rhine-001.example.data.json` exists and has the correct structure

### Catalog validation fails

Run `mise run catalog-check` and review the errors. Common issues:
- Missing required fields in collection.json
- Invalid bbox coordinates
- Missing links in catalog.json

### Tests fail

Run `uv run pytest scripts/tests/ -v` to see which tests fail. Review the test code
and ensure all expected behavior is implemented.

---

## Next Steps After Merge

Once all PRs are merged:

1. **Update README.md** to reference the new documentation
2. **Announce completion** in the project changelog
3. **Consider Phase 6** if additional features are needed (e.g., advanced harvesting, filtering)

---

## Summary

You now have everything needed to complete the Portolan catalog integration:

✅ Code fix applied to resolve bbox extraction issue  
✅ Test scripts created to verify the fix  
✅ Implementation scripts to automate the process  
✅ PR bodies ready for GitHub  
✅ Clear action items for each phase  

Execute the action items in order, and you'll have a fully functional Portolan-compliant
geocontract catalog with citizen proposal support and comprehensive documentation.
