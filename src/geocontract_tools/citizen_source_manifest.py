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
          "content_hash":  "sha256:...",
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
existing ``geocontract_tools.harvester`` design stub. After PR #9
merges, this module can call into ``citizen_source`` directly; for
now it provides the same ``HarvestRecord`` and ``to_jsonl`` helpers
locally to keep this PR independent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from geocontract_tools.canonicalize import canonicalize_for_signing
from geocontract_tools.public_projection import public_projection

Projection = Literal["public", "restricted"]

HARVESTER_VERSION = "geocontract-tools 0.1.0"


@dataclass(frozen=True)
class HarvestRecord:
    """One JSONL record produced by the citizen-source harvester.

    Duplicated here (rather than imported from ``citizen_source``) so
    this module is independent of PR #9. The two definitions will
    collapse once the branches merge.
    """

    source: str
    contract_id: str
    schema_version: str
    fetched_at: str
    content_hash: str
    lifecycle_state: str
    activity_code: str
    jurisdiction: str
    authoritative_parcel_id: str

    contract_version: str | None = None
    submission_id: str | None = None
    anchor_service_ref: str | None = None
    supersedes: str | None = None
    projection: Projection = "public"


@dataclass(frozen=True)
class SourceOutcome:
    """One entry in the manifest's ``sources`` array."""

    location: str
    kind: str
    contract_id: str | None
    schema_version: str | None
    contract_version: str | None
    content_hash: str | None
    lifecycle_state: str | None
    status: Literal["ok", "error"]
    error: str | None = None


# ── Loaders ──────────────────────────────────────────────────────────────────


def _load_nested_json(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text())
    proposal = doc.get("proposal")
    if not isinstance(proposal, dict):
        raise ValueError(f"{path}: missing top-level `proposal` object")
    return proposal


def _load_odcs_yaml(path: Path) -> dict[str, Any]:
    contract = yaml.safe_load(path.read_text())
    if not isinstance(contract, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    schema = contract.get("schema") or []
    if not schema:
        raise ValueError(f"{path}: missing `schema[]`")
    props = schema[0].get("properties") or []
    proposal: dict[str, Any] = {}
    for p in props:
        name = p.get("name")
        ex = (p.get("examples") or [None])[0]
        if ex is None or name is None:
            continue
        physical = p.get("physicalName") or ""
        if physical.startswith("proposal."):
            dotted = physical[len("proposal.") :]
        else:
            dotted = physical
        parts = dotted.split(".") if dotted else [name]
        cur = proposal
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = ex
    return proposal


def load_canonical(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_nested_json(path)
    if suffix in {".yaml", ".yml"}:
        return _load_odcs_yaml(path)
    raise ValueError(f"unsupported source format: {suffix} ({path})")


# ── Record building ──────────────────────────────────────────────────────────


def _record(
    *,
    proposal: dict[str, Any],
    source: str,
    contract_version: str | None,
    fetched_at: str,
    projection: Projection,
) -> HarvestRecord:
    if projection == "public":
        proposal = public_projection(proposal)
    digest = "sha256:" + hashlib.sha256(canonicalize_for_signing(proposal)).hexdigest()
    return HarvestRecord(
        source=source,
        contract_id=str(proposal.get("id", "")),
        schema_version=str(proposal.get("schemaVersion", "")),
        fetched_at=fetched_at,
        content_hash=digest,
        lifecycle_state=str(proposal.get("lifecycle", {}).get("state", "")),
        activity_code=str(proposal.get("activity", {}).get("code", "")),
        jurisdiction=str(proposal.get("parcel", {}).get("jurisdiction", "")),
        authoritative_parcel_id=str(
            proposal.get("parcel", {}).get("authoritativeParcelId", "")
        ),
        contract_version=contract_version,
        submission_id=(proposal.get("anchorReceipt") or {}).get("submissionId"),
        anchor_service_ref=(proposal.get("anchorReceipt") or {}).get("serviceRef"),
        supersedes=(proposal.get("lifecycle") or {}).get("supersedes"),
        projection=projection,
    )


def to_jsonl(records: Iterable[HarvestRecord]) -> str:
    return "\n".join(json.dumps(asdict(r), sort_keys=True) for r in records) + "\n"


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

            record = _record(
                proposal=proposal,
                source=str(src.resolve()),
                contract_version=contract_version,
                fetched_at=timestamp,
                projection=projection,
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
                    lifecycle_state=record.lifecycle_state,
                    status="ok",
                )
            )

            # Copy the source into contracts/ for self-contained output.
            target = contracts_dir / src.name
            shutil.copy2(src, target)
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                SourceOutcome(
                    location=str(src.resolve()),
                    kind="file",
                    contract_id=None,
                    schema_version=None,
                    contract_version=None,
                    content_hash=None,
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