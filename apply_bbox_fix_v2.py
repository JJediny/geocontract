#!/usr/bin/env python3
"""
Complete fix for _extract_bbox in portolan_sink.py

This replaces the broken implementation with a working version.
Run this script to apply the fix.
"""

import re
from pathlib import Path

def apply_fix():
    """Apply the corrected _extract_bbox function."""
    
    # Read the current file
    file_path = Path("src/geocontract_tools/portolan_sink.py")
    if not file_path.exists():
        print(f"ERROR: {file_path} not found")
        return False
    
    content = file_path.read_text()
    
    # The corrected function
    new_function = '''def _extract_bbox(contract: dict) -> list[float]:
    """Extract bbox from contract or associated proposal data.

    For citizen proposals, tries to load the example data file and extract
    geometry from proposal.parcel.geometry (WKT POLYGON).

    Returns [west, south, east, north] or default global bbox.
    """
    import json
    from pathlib import Path

    contract_id = contract.get("id", "")

    # Find project root using marker file search
    project_root = _find_project_root()
    if not project_root:
        return [-180.0, -90.0, 180.0, 90.0]

    examples_dir = project_root / "examples"
    if not examples_dir.exists():
        return [-180.0, -90.0, 180.0, 90.0]

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
                    # Parse WKT POLYGON: POLYGON((x1 y1, x2 y2, ...))
                    import re
                    coords_match = re.search(r'POLYGON\\(\\(([^)]+)\\)\\)', geometry_wkt)
                    if coords_match:
                        coords_str = coords_match.group(1)
                        coords = []
                        for point_str in coords_str.split(','):
                            parts = point_str.strip().split()
                            if len(parts) >= 2:
                                try:
                                    x = float(parts[0])
                                    y = float(parts[1])
                                    coords.append((x, y))
                                except ValueError:
                                    continue

                        if coords:
                            xs = [c[0] for c in coords]
                            ys = [c[1] for c in coords]
                            return [min(xs), min(ys), max(xs), max(ys)]
            except Exception as e:
                # If extraction fails, continue to next file
                pass

    # Default global bbox
    return [-180.0, -90.0, 180.0, 90.0]'''

    # Find the existing function and replace it
    # Pattern matches from 'def _extract_bbox' to the next function or end
    pattern = r'def _extract_bbox\(contract: dict\) -> list\[float\]:.*?(?=\n\ndef |\nclass |\Z)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("ERROR: Could not find _extract_bbox function")
        return False
    
    # Replace the function
    new_content = content[:match.start()] + new_function + content[match.end():]
    
    # Write back
    file_path.write_text(new_content)
    print("✓ Successfully applied fix to _extract_bbox function")
    return True

if __name__ == "__main__":
    success = apply_fix()
    if success:
        print("\nNow run: python3 test_bbox_fix.py")
    else:
        print("\nFix failed. Check the error messages above.")
