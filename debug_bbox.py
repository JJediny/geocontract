#!/usr/bin/env python3
"""Debug bbox extraction step by step."""

import sys
import json
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from geocontract_tools.portolan_sink import _find_project_root

contract_id = "groton-rhine-001"

print("=== Debugging Bbox Extraction ===\n")

# Step 1: Find project root
project_root = _find_project_root()
print(f"Step 1: Project root: {project_root}")

# Step 2: Check examples directory
examples_dir = project_root / "examples"
print(f"Step 2: Examples dir: {examples_dir}")
print(f"  Exists: {examples_dir.exists()}")

# Step 3: List example files
print(f"\nStep 3: Looking for files matching '*{contract_id}*.example.data.json'")
if examples_dir.exists():
    for example_file in examples_dir.glob("*.example.data.json"):
        print(f"  Found: {example_file.name}")
        if contract_id in example_file.stem:
            print(f"    ✓ Contract ID '{contract_id}' found in stem '{example_file.stem}'")
            
            # Step 4: Load the file
            print(f"\nStep 4: Loading file...")
            try:
                with open(example_file) as f:
                    data = json.load(f)
                print(f"  ✓ File loaded successfully")
                
                # Step 5: Check structure
                print(f"\nStep 5: Checking structure...")
                print(f"  Has 'proposal': {'proposal' in data}")
                print(f"  Has 'proposal.parcel': {'parcel' in data.get('proposal', {})}")
                
                if "proposal" in data and "parcel" in data["proposal"]:
                    parcel = data["proposal"]["parcel"]
                    print(f"  Parcel keys: {list(parcel.keys())}")
                    
                    # Step 6: Extract geometry
                    geometry_wkt = parcel.get("geometry")
                    print(f"\nStep 6: Geometry WKT: {geometry_wkt}")
                    
                    if geometry_wkt and geometry_wkt.startswith("POLYGON"):
                        print(f"  ✓ Geometry starts with POLYGON")
                        
                        # Step 7: Parse coordinates
                        print(f"\nStep 7: Parsing coordinates...")
                        coords_str = re.search(r'POLYGON\(\(([^)]+)\)\)', geometry_wkt)
                        if coords_str:
                            print(f"  ✓ Found coordinate string: {coords_str.group(1)[:50]}...")
                            
                            coords = []
                            for point in coords_str.group(1).split(','):
                                x, y = map(float, point.strip().split())
                                coords.append((x, y))
                            
                            print(f"  ✓ Parsed {len(coords)} coordinates")
                            
                            if coords:
                                xs = [c[0] for c in coords]
                                ys = [c[1] for c in coords]
                                bbox = [min(xs), min(ys), max(xs), max(ys)]
                                print(f"\nStep 8: Extracted bbox: {bbox}")
                                print(f"\n✓ SUCCESS: Bbox extraction works!")
                            else:
                                print(f"\n✗ FAILURE: No coordinates parsed")
                        else:
                            print(f"\n✗ FAILURE: Could not parse coordinate string")
                    else:
                        print(f"\n✗ FAILURE: Geometry doesn't start with POLYGON or is None")
                else:
                    print(f"\n✗ FAILURE: Structure doesn't match expected format")
            except Exception as e:
                print(f"\n✗ FAILURE: Exception during loading: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"    ✗ Contract ID '{contract_id}' NOT found in stem '{example_file.stem}'")
else:
    print(f"  ✗ Examples directory does not exist")
