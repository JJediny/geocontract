"""Federated harvester — design stub for geocontract discovery.

Goal (future): walk a list of remote geocontract.yaml URLs (and local
files), fetch each one, validate it against the canonical ODCS v3.1.0
schema, normalise it into the canonical `Exclusion` / `Project` / etc.
view, and emit a unified record stream (JSON Lines) for downstream
consumers (e.g. the mesh-gateway).

This module currently exposes only the CLI surface and a hand-typed
exception hierarchy. Concrete discovery, fetch, and validation
orchestration is intentionally deferred — see the project README's
"Future Planning" section for the design discussion.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HarvestSource:
    """One source to harvest: a URL or local path + its kind."""
    location: str
    kind: str  # "url" | "file" | "git"


class HarvestError(RuntimeError):
    """Raised when a source cannot be fetched or validated."""


def discover(paths: Iterable[str]) -> list[HarvestSource]:
    """Classify each input string as a URL, file path, or git URL.

    Order matters: we check ``git`` first because ``https://...foo.git``
    is a Git URL, not a plain HTTPS endpoint. Real fetching/validation
    is future work — see docs/design-harvester.md.
    """
    out: list[HarvestSource] = []
    for p in paths:
        if p.startswith(("git://", "git@", "git+")) or p.endswith(".git"):
            kind = "git"
        elif p.startswith(("http://", "https://")):
            kind = "url"
        else:
            kind = "file"
        out.append(HarvestSource(location=p, kind=kind))
    return out


def harvest(sources: Iterable[HarvestSource], out_dir: Path) -> None:
    """Stub: write a manifest of discovered sources without fetching them.

    Real implementation will:
      1. Fetch each source (URL → tmpfile; git → shallow clone)
      2. Locate the geocontract.yaml inside (root or `contracts/` subtree)
      3. Run geocontract_tools.validate_odcs against it
      4. Parse `schema[]` into per-entity JSONL records
      5. Append to out_dir/records.jsonl
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.json"
    manifest.write_text(
        "[stub] Harvest not yet implemented. Discovered sources:\n"
        + "\n".join(f"  - {s.kind}: {s.location}" for s in sources)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="geocontract-harvest",
        description="Federated harvester for geocontract.yaml files (stub).",
    )
    p.add_argument("sources", nargs="+", help="URL, file path, or git URL of a geocontract.yaml")
    p.add_argument("--out", default=".harvest", help="Output directory (default: ./.harvest)")
    args = p.parse_args(argv)

    sources = discover(args.sources)
    harvest(sources, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
