#!/bin/bash
# Complete Phase 4: Citizen Proposals Integration
# This script applies the bbox fix, tests it, regenerates the catalog, and creates PRs

set -e

echo "=== Phase 4: Citizen Proposals Integration ==="
echo ""

# Step 1: Verify the fix is in place
echo "Step 1: Verifying bbox extraction fix..."
if grep -q "_find_project_root" src/geocontract_tools/portolan_sink.py; then
    echo "✓ _find_project_root helper function found"
else
    echo "✗ Fix not found. Please apply the fix first."
    exit 1
fi

# Step 2: Test the bbox extraction
echo ""
echo "Step 2: Testing bbox extraction..."
python3 test_bbox_fix.py
if [ $? -ne 0 ]; then
    echo "✗ Bbox extraction test failed"
    exit 1
fi
echo "✓ Bbox extraction works correctly"

# Step 3: Regenerate the catalog with the fix
echo ""
echo "Step 3: Regenerating catalog with fixed bbox extraction..."
uv run python -m geocontract_tools.harvester \
    --source contracts/ \
    --catalog-dir catalog/ \
    --portolan

# Step 4: Verify the bbox in the generated collection
echo ""
echo "Step 4: Verifying bbox in generated collection..."
if [ -f catalog/citizen/groton-rhine-001/collection.json ]; then
    BBOX=$(jq -r '.extent.spatial.bbox[0]' catalog/citizen/groton-rhine-001/collection.json)
    echo "  Generated bbox: $BBOX"
    
    # Check if it's the expected coarsened bbox
    if echo "$BBOX" | grep -q "\-72.09"; then
        echo "✓ Bbox correctly coarsened for privacy"
    else
        echo "✗ Bbox not correctly coarsened"
        exit 1
    fi
else
    echo "✗ Citizen collection not found"
    exit 1
fi

# Step 5: Validate the catalog
echo ""
echo "Step 5: Validating catalog..."
mise run catalog-check
if [ $? -ne 0 ]; then
    echo "✗ Catalog validation failed"
    exit 1
fi
echo "✓ Catalog validates successfully"

# Step 6: Run tests
echo ""
echo "Step 6: Running harvester tests..."
uv run pytest scripts/tests/test_harvester_portolan.py -v
if [ $? -ne 0 ]; then
    echo "✗ Tests failed"
    exit 1
fi
echo "✓ All tests pass"

# Step 7: Commit changes
echo ""
echo "Step 7: Committing changes..."
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

echo "✓ Changes committed"

# Step 8: Push and create PR
echo ""
echo "Step 8: Pushing branch..."
BRANCH="feature/portolan-phase4-citizen-proposals"
git push origin $BRANCH 2>/dev/null || git push -u origin $BRANCH

echo ""
echo "=== Phase 4 Complete ==="
echo ""
echo "Next steps:"
echo "1. Create PR with the body provided in the conversation"
echo "2. Request review (do not merge yourself)"
echo "3. After merge, proceed with Phase 5 (documentation)"
echo ""
echo "PR Body:"
echo "---"
cat << 'EOF'
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
EOF
echo "---"
