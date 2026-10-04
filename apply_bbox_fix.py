#!/usr/bin/env python3
"""
Fix the _extract_bbox function in portolan_sink.py.

This script applies the corrected implementation.
"""

import re
from pathlib import Path

# Read the current file
file_path = Path("src/geocontract_tools/portolan_sink.py")
content = file_path.read_text()

# The corrected _extract_bbox function
corrected_function = '''
def _extract_bbox(contract: dict) -> list[float]:
    """Extract bbox from contract or associated proposal data.

    For citizen proposals, tries to load the example data file and extract
    geometry from proposal.parcel.geometry (WKT POLYGON).

    Returns [west, south, east, north] or default global bbox.
    """
    import json
    from pathlib import Path

    contract_id = contract.get("id", "")

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
                        import re as re_module
                        coords_match = re_module.search(r'POLYGON\\(\\(([^)]+)\\)\\)', geometry_wkt)
                        if coords_match:
                            coords = []
                            for point in coords_match.group(1).split(','):
                                parts = point.strip().split()
                                if len(parts) == 2:
                                    x, y = float(parts[0]), float(parts[1])
                                    coords.append((x, y))

                            if coords:
                                xs = [c[0] for c in coords]
                                ys = [c[1] for c in coords]
                                return [min(xs), min(ys), max(xs), max(ys)]
                except Exception as e:
                    # If extraction fails, fall through to default
                    print(f"Warning: Failed to extract bbox from {example_file.name}: {e}")
                    pass

    # Default global bbox (will be coarsened)
    return [-180.0, -90.0, 180.0, 90.0]
'''

# Find and replace the _extract_bbox function
# Match from 'def _extract_bbox' to the next 'def ' or end of file
pattern = r'def _extract_bbox\(contract: dict\) -> list\[float\]:.*?(?=\n\ndef |\nclass |\Z)'

if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, corrected_function.strip() + '\n', content, flags=re.DOTALL)
    file_path.write_text(content)
    print("✓ Fixed _extract_bbox function")
    print("\nKey changes:")
    print("  1. Added error logging to see what's failing")
    print("  2. Improved coordinate parsing with better validation")
    print("  3. Added length check for coordinate parts")
else:
    print("✗ Could not find _extract_bbox function to replace")
