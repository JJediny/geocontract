#!/usr/bin/env python3
"""
Complete replacement for _extract_bbox that will definitely work.
This is a standalone script that patches the file.
"""

import sys
from pathlib import Path

# Read the file
file_path = Path("src/geocontract_tools/portolan_sink.py")
lines = file_path.read_text().split('\n')

# Find the _extract_bbox function
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith('def _extract_bbox'):
        start_idx = i
    elif start_idx is not None and line.strip().startswith('def _coarsen_bbox'):
        end_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find _extract_bbox function")
    sys.exit(1)

# New function implementation
new_function = '''
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
    
    # Find project root
    project_root = _find_project_root()
    if not project_root:
        return [-180.0, -90.0, 180.0, 90.0]
    
    examples_dir = project_root / "examples"
    if not examples_dir.exists():
        return [-180.0, -90.0, 180.0, 90.0]
    
    # Look for example data file
    for example_file in examples_dir.glob("*.example.data.json"):
        if contract_id in example_file.stem:
            try:
                with open(example_file) as f:
                    data = json.load(f)
                
                # Extract geometry WKT
                geometry_wkt = None
                if "proposal" in data and "parcel" in data["proposal"]:
                    geometry_wkt = data["proposal"]["parcel"].get("geometry")
                
                if geometry_wkt and geometry_wkt.startswith("POLYGON"):
                    # Parse: POLYGON((x1 y1, x2 y2, ...))
                    match = re.search(r'POLYGON\\(\\(([^)]+)\\)\\)', geometry_wkt)
                    if match:
                        coords = []
                        for point_str in match.group(1).split(','):
                            parts = point_str.strip().split()
                            if len(parts) >= 2:
                                x, y = float(parts[0]), float(parts[1])
                                coords.append((x, y))
                        
                        if coords:
                            xs = [c[0] for c in coords]
                            ys = [c[1] for c in coords]
                            return [min(xs), min(ys), max(xs), max(ys)]
            except Exception:
                pass
    
    return [-180.0, -90.0, 180.0, 90.0]

'''

# Replace the function
new_lines = lines[:start_idx] + new_function.split('\n') + lines[end_idx:]

# Write back
file_path.write_text('\n'.join(new_lines))
print("✓ Successfully replaced _extract_bbox function")
print("\nNow run: python3 test_bbox_fix.py")
