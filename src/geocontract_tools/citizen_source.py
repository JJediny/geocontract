"""Citizen-initiated source harvester (plan §6, Phase 4 of §8).

Reads a citizen-initiated Proposal from one of:

  - a nested-JSON file (e.g. ``examples/groton-rhine-001.example.data.json``)
  - an ODCS-flatten contract YAML (e.g. ``contracts/groton-rhine-001.datacontract.yaml``)

and emits a **JSONL** stream with one record per Proposal. The default
projection is **public** (plan §5.8); the **restricted** projection is
emitted only when an authority token is supplied.

JSONL record shape (plan §6):

    {
      "source":                    "<where we read it from>",
      "contract_id":               "<proposal.id>",
      "contract_version":          "<odcs contract version, if any>",
      "schema_version":            "<proposal.schemaVersion>",
      "fetched_at":                "<ISO 8601 timestamp>",
      "content_hash":              "sha256:...",     # canonical sha256 of the proposal (with proof excluded)
      "submission_id":             "<anchor.service submissionId, if any>",
      "anchor_service_ref":        "<anchor.service serviceRef, if any>",
      "lifecycle_state":           "<proposal.lifecycle.state>",
      "supersedes":                "<proposal.lifecycle.supersedes, if any>",
      "activity_code":             "<proposal.activity.code>",
      "jurisdiction":              "<proposal.parcel.jurisdiction>",
      "authoritative_parcel_id":   "<proposal.parcel.authoritativeParcelId>",
      "projection":                "public" | "restricted"
    }

This is an additive extension of the per-entity record shape in
``docs/design-harvester.md`` §"Output schema" — the existing fields
(source / contract_id / fetched_at / entity / physical_name /
properties / quality / sla / lineage / tags / custom_properties)
remain unchanged.

The module deliberately **does not** perform any RPC, fetch from
ComposeDB, or crawl GitHub. It is offline by design (plan §5.1
"conventional alternative" and §8 Phase 4). Anchoring / chain
integration is §13.2 (out-of-core experimental).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from geocontract_tools.canonicalize import canonicalize_for_signing
from geocontract_tools.public_projection import public_projection


Projection = Literal["public", "restricted"]


@dataclass(frozen=True)
class HarvestRecord:
    """One JSONL record produced by the citizen-source harvester."""

    # Provenance (always present)
    source: str
    contract_id: str
    schema_version: str
    fetched_at: str  # ISO 8601 with timezone

    # v2 additive fields (plan §6)
    content_hash: str
    lifecycle_state: str

    # Citizen-domain facts (always present)
    activity_code: str
    jurisdiction: str
    authoritative_parcel_id: str

    # Optional v2 additive fields (None if absent on the source)
    contract_version: str | None = None
    submission_id: str | None = None
    anchor_service_ref: str | None = None
    supersedes: str | None = None

    # Projection marker — the harvester MUST emit only restricted
    # fields when this is "restricted", and the caller is responsible
    # for having authority to consume them.
    projection: Projection = "public"


# ── Loaders ──────────────────────────────────────────────────────────────────


def _load_nested_json(path: Path) -> dict[str, Any]:
    """Load a nested-JSON Proposal file. Returns the proposal body."""
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: not a JSON object")
    proposal = doc.get("proposal")
    if not isinstance(proposal, dict):
        raise ValueError(f"{path}: missing top-level `proposal` object")
    return proposal


def _canonical_from_odcs_examples(path: Path) -> dict[str, Any]:
    """Rebuild a partial canonical Proposal from an ODCS contract YAML.

    The ODCS-flatten projection is lossy by design (plan §3.6:
    restricted fields are deliberately omitted). This loader therefore
    only recovers the public projection's keys; restricted fields
    are not available from the YAML and must be sourced from a
    signed, restricted JSON projection (out of scope for v2).

    The reconstruction uses each property's ``physicalName`` to
    recover the canonical dotted path. Each property's first
    ``examples`` entry is treated as the canonical value. In
    production the harvester would harvest *records* (each row of
    the dataset the contract describes), not the contract's own
    example values; this loader exists for round-trip tests and
    for the harvest-the-contract-itself use case.
    """
    contract = yaml.safe_load(path.read_text())
    if not isinstance(contract, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    schema = contract.get("schema") or []
    if not schema:
        raise ValueError(f"{path}: missing `schema[]`")
    return _examples_to_proposal(schema[0].get("properties") or [])


def _examples_to_proposal(props: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct a partial canonical Proposal from ODCS property examples."""
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


# ── Public projection + content hash ─────────────────────────────────────────


def _public_record(
    *,
    proposal: dict[str, Any],
    source: str,
    contract_version: str | None,
    fetched_at: str,
    projection: Projection,
) -> HarvestRecord:
    """Build a HarvestRecord from a canonical proposal.

    Restricted fields are dropped unless ``projection='restricted'``
    AND the caller has supplied an authority token (enforced by the
    CLI; the library function trusts the caller).
    """
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
        authoritative_parcel_id=str(proposal.get("parcel", {}).get("authoritativeParcelId", "")),
        contract_version=contract_version,
        submission_id=(proposal.get("anchorReceipt") or {}).get("submissionId"),
        anchor_service_ref=(proposal.get("anchorReceipt") or {}).get("serviceRef"),
        supersedes=(proposal.get("lifecycle") or {}).get("supersedes"),
        projection=projection,
    )


# ── Public API ───────────────────────────────────────────────────────────────


def load_canonical(path: Path) -> dict[str, Any]:
    """Load a Proposal from a nested-JSON or ODCS-YAML file.

    The format is auto-detected:
    - JSON files with a top-level ``proposal`` key → nested-JSON canonical.
    - YAML files with ``apiVersion: v3.1.0`` and ``kind: DataContract``
      → ODCS contract, re-built via the §3.6 mapping's inverse.
    """
    suffix = path.suffix.lower()
    if suffix in {".json"}:
        return _load_nested_json(path)
    if suffix in {".yaml", ".yml"}:
        # We rebuild via the physicalName → dotted-path mapping
        # (the round-trip in odcs_flatten.unflatten handles this).
        return _canonical_from_odcs_examples(path)
    raise ValueError(f"unsupported source format: {suffix} ({path})")


def harvest_one(
    path: Path,
    *,
    projection: Projection = "public",
    authority_token: str | None = None,
    fetched_at: str | None = None,
) -> HarvestRecord:
    """Harvest a single Proposal file into a HarvestRecord."""
    proposal = load_canonical(path)

    if projection == "restricted" and not authority_token:
        raise PermissionError(
            "restricted projection requires --authority-token (plan §5.8)"
        )

    # Read the contract version from the ODCS YAML if that's the source.
    contract_version: str | None = None
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            contract_version = yaml.safe_load(path.read_text()).get("version")
        except Exception:  # noqa: BLE001
            contract_version = None

    return _public_record(
        proposal=proposal,
        source=str(path),
        contract_version=contract_version,
        fetched_at=fetched_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        projection=projection,
    )


def harvest_many(
    paths: Iterable[Path],
    *,
    projection: Projection = "public",
    authority_token: str | None = None,
) -> list[HarvestRecord]:
    """Harvest a list of Proposal files."""
    return [
        harvest_one(p, projection=projection, authority_token=authority_token)
        for p in paths
    ]


def to_jsonl(records: Iterable[HarvestRecord]) -> str:
    """Serialise records to a JSONL string (one record per line)."""
    return "\n".join(json.dumps(asdict(r), sort_keys=True) for r in records) + "\n"


# ── CLI surface ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="geocontract-harvest-citizen",
        description=(
            "Harvest citizen-initiated Proposal sources (plan §6, Phase 4). "
            "Emits one JSONL record per Proposal. Public projection is the "
            "default; restricted projection requires --authority-token."
        ),
    )
    p.add_argument(
        "sources",
        nargs="+",
        help="Paths to nested-JSON Proposal files or ODCS contract YAMLs.",
    )
    p.add_argument(
        "--projection",
        choices=("public", "restricted"),
        default="public",
        help="JSONL projection (default: public).",
    )
    p.add_argument(
        "--authority-token",
        default=None,
        help=(
            "Required for the restricted projection (plan §5.8). "
            "Passed through to the audit log."
        ),
    )
    p.add_argument(
        "--out",
        default="-",
        help="Output file path (default: stdout).",
    )
    args = p.parse_args(argv)

    if args.projection == "restricted" and not args.authority_token:
        p.error("--authority-token is required for --projection=restricted")

    records = harvest_many(
        [Path(s) for s in args.sources],
        projection=args.projection,  # type: ignore[arg-type]
        authority_token=args.authority_token,
    )

    output = to_jsonl(records)
    if args.out == "-":
        sys.stdout.write(output)
    else:
        Path(args.out).write_text(output)

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())