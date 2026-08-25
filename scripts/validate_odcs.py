#!/usr/bin/env python3
"""Thin wrapper that invokes the geocontract_tools package entry point.

The actual implementation lives at
src/geocontract_tools/validate_odcs.py and is installed as the console
script `geocontract-validate` (see pyproject.toml). This wrapper exists
so the hook config in prek.toml can call
`python scripts/validate_odcs.py` directly without a `uv run` prefix.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the src/ layout importable when run from a checkout without `uv sync`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.validate_odcs import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
