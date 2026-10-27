#!/usr/bin/env python3
"""Build the activity SKOS ontology from the curated JSON catalog."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.build_ontology import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
