#!/usr/bin/env python3
"""Test the bbox extraction fix."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from geocontract_tools.portolan_sink import _find_project_root, _extract_bbox, _coarsen_bbox

# Test _find_project_root
print("Testing _find_project_root...")
project_root = _find_project_root()
print(f"  Project root: {project_root}")
print(f"  pyproject.toml exists: {(project_root / 'pyproject.toml').exists() if project_root else False}")
print(f"  examples dir exists: {(project_root / 'examples').exists() if project_root else False}")

# Test _extract_bbox with groton-rhine-001 contract
print("\nTesting _extract_bbox with groton-rhine-001...")
contract = {"id": "groton-rhine-001"}
bbox = _extract_bbox(contract)
print(f"  Extracted bbox: {bbox}")

# Test _coarsen_bbox
print("\nTesting _coarsen_bbox...")
coarsened = _coarsen_bbox(bbox)
print(f"  Coarsened bbox: {coarsened}")
print(f"  Expected: [-72.09, 41.34, -72.08, 41.35]")

# Verify the fix
if coarsened == [-72.09, 41.34, -72.08, 41.35]:
    print("\n✓ SUCCESS: Bbox extraction works correctly!")
    sys.exit(0)
else:
    print(f"\n✗ FAILURE: Expected [-72.09, 41.34, -72.08, 41.35], got {coarsened}")
    sys.exit(1)
