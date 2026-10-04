#!/usr/bin/env python3
"""Thin wrapper that invokes the geocontract_tools package entry point.

The actual implementation lives at
src/geocontract_tools/build_catalog.py. This wrapper exists
so scripts can call `python scripts/build_catalog.py` directly
without a `uv run` prefix.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the src/ layout importable when run from a checkout without `uv sync`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.build_catalog import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
