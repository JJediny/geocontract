"""Citizen-source harvest manifest (plan §6 + docs/design-harvester.md).

The harvester's output directory layout is::

    <out-dir>/
        manifest.json          # provenance + per-source metadata
        records.jsonl          # one record per Proposal (per §6)
        contracts/             # a copy of every successfully-harvested
                               # source file (with its on-disk name)

The ``manifest.json`` shape is:

    {
      "harvester_version":  "geocontract-tools 0.1.0",
      "fetched_at":         "<ISO 8601 UTC>",
      "projection":         "public" | "restricted",
      "records_count":      <int>,
      "sources": [
        {
          "location":      "<absolute path or URI>",
          "kind":          "file" | "url" | "git",
          "contract_id":   "<proposal.id>",
          "schema_version":"<proposal.schemaVersion>",
          "content_hash":  "sha256:...",       # canonical proposal hash
          "source_hash":   "sha256:...",       # exact source-file hash
          "lifecycle_state":"<proposal.lifecycle.state>",
          "status":        "ok" | "error",
          "error":         "<message>"   # only on error
        },
        ...
      ]
    }

The ``records.jsonl`` is one record per line; see
``citizen_source.HarvestRecord`` for the per-record shape.

This module is deliberately additive: it does not modify the
existing ``geocontract_tools.harvester`` design stub. It delegates
loading, projection, validation, and JSONL serialization to the shared
``citizen_source`` implementation; PR #9 is therefore a required
predecessor rather than a duplicated implementation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from geocontract_tools.citizen_source import (
    HarvestRecord,
    harvest_one,
    load_canonical,
    to_jsonl,
)

Projection = Literal["public", "restricted"]

HARVESTER_VERSION = "geocontract-tools 0.1.0"



@dataclass(frozen=True)
class SourceOutcome:
    """One entry in the manifest's ``sources`` array."""

    location: str
    kind: str
    contract_id: str | None
    schema_version: str | None
    contract_version: str | None
    content_hash: str | None
    source_hash: str | None
    lifecycle_state: str | None
    status: Literal["ok", "error"]
    error: str | None = None



# ── Manifest + directory layout ─────────────────────────────────────────────


def harvest_directory(
    sources: list[Path],
    *,
    out_dir: Path,
    projection: Projection = "public",
    authority_token: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Harvest every source into ``out_dir`` and write a manifest.

    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    Per source, writes a copy of the file to ``out_dir/contracts/<basename>``
    so the harvest output is self-contained.
    """
    if projection == "restricted" and not authority_token:
        raise PermissionError(
            "restricted projection requires authority_token (plan §5.8)"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir = out_dir / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    records: list[HarvestRecord] = []
    outcomes: list[SourceOutcome] = []
    copied_names: set[str] = set()
    timestamp = fetched_at or dt.datetime.now(dt.timezone.utc).isoformat()

    for src in sources:
        try:
            proposal = load_canonical(src)
            contract_version: str | None = None
            if src.suffix.lower() in {".yaml", ".yml"}:
                try:
                    contract_version = yaml.safe_load(src.read_text()).get("version")
                except Exception:  # noqa: BLE001
                    contract_version = None

            # A basename collision would make the self-contained copy
            # ambiguous and could silently replace an earlier source.
            if src.name in copied_names:
                raise ValueError(
                    f"source basename collision in output: {src.name!r}; "
                    "use unique source filenames"
                )

            source_hash = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()
            # Copy the source before publishing its record. A failed copy
            # must not leave a successful record in records.jsonl.
            target = contracts_dir / src.name
            shutil.copy2(src, target)
            copied_names.add(src.name)

            record = harvest_one(
                src,
                projection=projection,
                authority_token=authority_token,
                fetched_at=timestamp,
            )
            records.append(record)
            outcomes.append(
                SourceOutcome(
                    location=str(src.resolve()),
                    kind="file",
                    contract_id=record.contract_id,
                    schema_version=record.schema_version,
                    contract_version=record.contract_version,
                    content_hash=record.content_hash,
                    source_hash=source_hash,
                    lifecycle_state=record.lifecycle_state,
                    status="ok",
                )
            )
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                SourceOutcome(
                    location=str(src.resolve()),
                    kind="file",
                    contract_id=None,
                    schema_version=None,
                    contract_version=None,
                    content_hash=None,
                    source_hash=None,
                    lifecycle_state=None,
                    status="error",
                    error=str(exc),
                )
            )

    records_path = out_dir / "records.jsonl"
    records_path.write_text(to_jsonl(records))

    manifest = {
        "harvester_version": HARVESTER_VERSION,
        "fetched_at": timestamp,
        "projection": projection,
        "records_count": len(records),
        "sources": [asdict(o) for o in outcomes],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return manifest


# ── CLI surface ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="geocontract-harvest-citizen-dir",
        description=(
            "Harvest citizen-initiated Proposal sources into a directory "
            "(plan §6 / docs/design-harvester.md). Writes manifest.json, "
            "records.jsonl, and a contracts/ copy of every source."
        ),
    )
    p.add_argument("sources", nargs="+", help="Paths to Proposal files.")
    p.add_argument(
        "--out",
        default=".harvest/citizen",
        help="Output directory (default: ./.harvest/citizen)",
    )
    p.add_argument(
        "--projection",
        choices=("public", "restricted"),
        default="public",
    )
    p.add_argument("--authority-token", default=None)
    args = p.parse_args(argv)

    if args.projection == "restricted" and not args.authority_token:
        p.error("--authority-token is required for --projection=restricted")

    harvest_directory(
        [Path(s) for s in args.sources],
        out_dir=Path(args.out),
        projection=args.projection,  # type: ignore[arg-type]
        authority_token=args.authority_token,
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())