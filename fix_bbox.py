#!/usr/bin/env python3
"""Fix the _extract_bbox function in portolan_sink.py to use marker file search."""

import re
from pathlib import Path

# Read the file
file_path = Path("src/geocontract_tools/portolan_sink.py")
content = file_path.read_text()

# Define the new helper function
new_helper = '''
def _find_project_root() -> "Path | None":
    """Find project root by searching for pyproject.toml marker file."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback to current working directory
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    return None


'''

# Find where to insert the helper (before _extract_bbox)
insert_pattern = r'(def _extract_bbox\(contract: dict\))'
content = re.sub(insert_pattern, new_helper + r'\1', content, count=1)

# Define the new _extract_bbox function
old_extract_pattern = r'def _extract_bbox\(contract: dict\) -> list\[float\]:.*?(?=\n\ndef |\nclass |\Z)'

new_extract = '''def _extract_bbox(contract: dict) -> list[float]:
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
        # Fallback: try common locations
        for candidate in [
            Path(__file__).resolve().parent.parent.parent,
            Path.cwd(),
        ]:
            if (candidate / "examples").exists():
                project_root = candidate
                break
    
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
                        coords_str = re_module.search(r'POLYGON\\(\\(([^)]+)\\)\\)', geometry_wkt)
                        if coords_str:
                            coords = []
                            for point in coords_str.group(1).split(','):
                                x, y = map(float, point.strip().split())
                                coords.append((x, y))

                            if coords:
                                xs = [c[0] for c in coords]
                                ys = [c[1] for c in coords]
                                return [min(xs), min(ys), max(xs), max(ys)]
                except Exception as e:
                    # If extraction fails, fall through to default
                    pass

    # Default global bbox (will be coarsened)
    return [-180.0, -90.0, 180.0, 90.0]

'''

content = re.sub(old_extract_pattern, new_extract, content, flags=re.DOTALL)

# Write back
file_path.write_text(content)
print("✓ Fixed _extract_bbox function to use marker file search")
print("✓ Added _find_project_root helper function")
