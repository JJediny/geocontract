#!/usr/bin/env python3
"""CLI wrapper for the geocontract federated harvester.

Usage:
    uv run python scripts/harvest.py <source1> <source2> ... [options]

Options:
    --out <dir>           Output directory for JSONL sink (default: .harvest)
    --sink <type>         Output sink: jsonl (default) or portolan
    --catalog-dir <dir>   Catalog directory for portolan sink (default: catalog)

Examples:
    # Harvest local contract to JSONL
    uv run python scripts/harvest.py contracts/example.datacontract.yaml

    # Harvest multiple sources to JSONL
    uv run python scripts/harvest.py contracts/*.yaml --out .harvest

    # Harvest to Portolan mirror collections
    uv run python scripts/harvest.py contracts/example.yaml --sink portolan

    # Harvest from URL to Portolan mirror
    uv run python scripts/harvest.py https://example.com/contract.yaml --sink portolan
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.harvester import main

if __name__ == "__main__":
    sys.exit(main())
