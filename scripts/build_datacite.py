#!/usr/bin/env python3
"""Thin wrapper that invokes the geocontract_tools build_datacite entry point.

Mirrors scripts/build_catalog.py and scripts/build_dcat.py: the
implementation lives in src/geocontract_tools/build_datacite.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.build_datacite import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
