"""Federated harvester for geocontract discovery.

Walks a list of remote geocontract.yaml URLs (and local files), fetches each one,
validates it against the canonical ODCS v3.1.0 schema, and emits output to the
configured sink (JSONL records or Portolan mirror collections).

Supports multiple source types:
- Local files: file:// or plain paths
- HTTP/HTTPS: fetched via httpx
- Git repos: shallow cloned (requires git CLI)
- S3: fetched via boto3 (requires AWS credentials)

Output sinks:
- jsonl: Writes records to .harvest/records.jsonl (default)
- portolan: Writes mirror collections to catalog/mirror/<slug>/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import yaml

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None


@dataclass(frozen=True)
class HarvestSource:
    """One source to harvest: a URL or local path + its kind."""
    location: str
    kind: Literal["url", "file", "git", "s3"]


@dataclass(frozen=True)
class HarvestResult:
    """One successfully harvested contract."""
    source: HarvestSource
    contract: dict
    contract_data: bytes
    contract_checksum: str
    fetched_at: str


class HarvestError(RuntimeError):
    """Raised when a source cannot be fetched or validated."""


def discover(paths: Iterable[str]) -> list[HarvestSource]:
    """Classify each input string as a URL, file path, git URL, or S3 URI.

    Order matters: we check git first because https://...foo.git is a Git URL,
    not a plain HTTPS endpoint. Then S3 URIs, then HTTP(S), then local files.
    """
    out: list[HarvestSource] = []
    for p in paths:
        if p.startswith(("git://", "git@", "git+")) or p.endswith(".git"):
            kind = "git"
        elif p.startswith("s3://"):
            kind = "s3"
        elif p.startswith(("http://", "https://")):
            kind = "url"
        elif p.startswith("file://"):
            kind = "file"
            p = p[7:]  # Strip file:// prefix
        else:
            kind = "file"
        out.append(HarvestSource(location=p, kind=kind))
    return out


def fetch_source(source: HarvestSource) -> bytes:
    """Fetch the contract data from a source.

    Returns the raw bytes of the contract file.
    """
    if source.kind == "file":
        path = Path(source.location)
        if not path.exists():
            raise HarvestError(f"File not found: {path}")
        return path.read_bytes()

    elif source.kind == "url":
        try:
            response = httpx.get(source.location, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as e:
            raise HarvestError(f"Failed to fetch {source.location}: {e}") from e

    elif source.kind == "git":
        # Shallow clone to a temp directory and find the contract
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", source.location, str(tmpdir_path)],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            except subprocess.CalledProcessError as e:
                raise HarvestError(f"Failed to clone {source.location}: {e.stderr.decode()}") from e

            # Look for contract files in common locations
            for candidate in [
                tmpdir_path / "contract.yaml",
                tmpdir_path / "contracts" / "contract.yaml",
                *tmpdir_path.glob("*.datacontract.yaml"),
                *tmpdir_path.glob("contracts/*.datacontract.yaml"),
            ]:
                if candidate.exists():
                    return candidate.read_bytes()

            raise HarvestError(f"No contract file found in git repo: {source.location}")

    elif source.kind == "s3":
        if boto3 is None:
            raise HarvestError("boto3 not installed; cannot fetch from S3")

        # Parse s3://bucket/key
        parts = source.location[5:].split("/", 1)
        if len(parts) != 2:
            raise HarvestError(f"Invalid S3 URI: {source.location}")
        bucket, key = parts

        try:
            s3 = boto3.client("s3")
            response = s3.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            raise HarvestError(f"Failed to fetch from S3: {e}") from e

    else:
        raise HarvestError(f"Unknown source kind: {source.kind}")


def parse_contract(data: bytes, source: HarvestSource) -> dict:
    """Parse and validate a contract from raw bytes.

    Returns the parsed contract dict.
    """
    try:
        contract = yaml.safe_load(data)
    except yaml.YAMLError as e:
        raise HarvestError(f"Failed to parse YAML from {source.location}: {e}") from e

    if not isinstance(contract, dict):
        raise HarvestError(f"Contract is not a YAML mapping: {source.location}")

    # Basic validation: must have required ODCS fields
    required = ["apiVersion", "kind", "id", "name", "version"]
    missing = [f for f in required if f not in contract]
    if missing:
        raise HarvestError(
            f"Contract {source.location} missing required fields: {', '.join(missing)}"
        )

    return contract


def harvest_source(source: HarvestSource) -> HarvestResult:
    """Harvest a single source: fetch, parse, and return the result."""
    # Format as ISO 8601 with Z suffix (not +00:00)
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch the contract data
    contract_data = fetch_source(source)

    # Compute checksum
    contract_checksum = "sha256:" + hashlib.sha256(contract_data).hexdigest()

    # Parse the contract
    contract = parse_contract(contract_data, source)

    return HarvestResult(
        source=source,
        contract=contract,
        contract_data=contract_data,
        contract_checksum=contract_checksum,
        fetched_at=fetched_at,
    )


def harvest(sources: Iterable[HarvestSource], out_dir: Path) -> list[HarvestResult]:
    """Harvest multiple sources and write results to the output directory.

    Returns the list of successful harvest results.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []

    for source in sources:
        try:
            result = harvest_source(source)
            results.append(result)
            print(f"✓ Harvested {source.location}", file=sys.stderr)
        except HarvestError as e:
            errors.append((source, str(e)))
            print(f"✗ Failed to harvest {source.location}: {e}", file=sys.stderr)

    # Write manifest
    manifest = {
        "harvested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources_count": len(list(sources)),
        "success_count": len(results),
        "error_count": len(errors),
        "results": [
            {
                "source": r.source.location,
                "kind": r.source.kind,
                "contract_id": r.contract.get("id"),
                "contract_version": r.contract.get("version"),
                "checksum": r.contract_checksum,
                "fetched_at": r.fetched_at,
            }
            for r in results
        ],
        "errors": [
            {
                "source": s.location,
                "kind": s.kind,
                "error": e,
            }
            for s, e in errors
        ],
    }

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # Copy contract files
    contracts_dir = out_dir / "contracts"
    contracts_dir.mkdir(exist_ok=True)
    for result in results:
        # Use contract id as filename
        contract_id = result.contract.get("id", "unknown")
        # Sanitize for filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in contract_id)
        contract_path = contracts_dir / f"{safe_id}.datacontract.yaml"
        contract_path.write_bytes(result.contract_data)

    return results


def harvest_to_portolan(
    results: Iterable[HarvestResult],
    catalog_dir: Path,
) -> None:
    """Write harvest results as Portolan collections.
    
    Routes citizen proposals to catalog/citizen/ as official collections,
    and other contracts to catalog/mirror/ as mirror collections.
    """
    from geocontract_tools.portolan_sink import (
        ensure_mirror_catalog,
        update_mirror_catalog,
        update_root_catalog,
        write_mirror_collection,
        write_citizen_collection,
        ensure_citizen_catalog,
        update_citizen_catalog,
    )

    citizen_results = []
    mirror_results = []

    # Separate citizen proposals from mirrors
    for result in results:
        if _is_citizen_proposal(result.contract):
            citizen_results.append(result)
        else:
            mirror_results.append(result)

    # Process citizen proposals
    if citizen_results:
        ensure_citizen_catalog(catalog_dir)
        for result in citizen_results:
            slug = slugify(result.contract.get("id", "unknown"))
            source_info = {
                "source_url": result.source.location,
                "jurisdiction": _extract_custom_property(result.contract, "jurisdiction"),
                "access_class": _extract_custom_property(result.contract, "accessClass"),
            }

            class SinkResult:
                def __init__(self, result: HarvestResult, source_info: dict):
                    self.contract = result.contract
                    self.source_data = result.contract_data
                    self.source_info = source_info

            sink_result = SinkResult(result, source_info)
            collection_path = write_citizen_collection(
                sink_result,
                catalog_dir,
                result.fetched_at,
            )
            print(f"✓ Wrote citizen collection: {collection_path.relative_to(catalog_dir.parent)}", file=sys.stderr)

        update_citizen_catalog(catalog_dir)

    # Process mirror collections
    if mirror_results:
        ensure_mirror_catalog(catalog_dir)
        for result in mirror_results:
            slug = slugify(result.contract.get("id", "unknown"))
            via_url = _extract_source_url(result.contract_data)
            source_info = {
                "source_url": result.source.location,
                "upstream_name": result.contract.get("tenant", "Unknown"),
                "upstream_url": via_url or "",
                "via_url": via_url or result.source.location if result.source.kind == "url" else via_url or "",
            }

            class SinkResult:
                def __init__(self, result: HarvestResult, source_info: dict):
                    self.contract = result.contract
                    self.source_data = result.contract_data
                    self.source_info = source_info

            sink_result = SinkResult(result, source_info)
            collection_path = write_mirror_collection(
                sink_result,
                catalog_dir,
                result.fetched_at,
            )
            print(f"✓ Wrote mirror collection: {collection_path.relative_to(catalog_dir.parent)}", file=sys.stderr)

        update_mirror_catalog(catalog_dir)
        update_root_catalog(catalog_dir)


def _is_citizen_proposal(contract: dict) -> bool:
    """Check if a contract is a citizen-initiated proposal."""
    custom_props = contract.get("customProperties") or []
    for prop in custom_props:
        if prop.get("property") == "isCitizenInitiated" and prop.get("value") is True:
            return True
    return False


def _extract_custom_property(contract: dict, property_name: str) -> str | None:
    """Extract a value from customProperties by property name."""
    custom_props = contract.get("customProperties") or []
    for prop in custom_props:
        if prop.get("property") == property_name:
            return str(prop.get("value", ""))
    return None


def slugify(s: str) -> str:
    """Convert a string to a valid slug for collection IDs."""
    import re
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "unknown"


def _extract_source_url(contract_data: bytes) -> str | None:
    """Extract source URL from contract file comments.
    
    Looks for lines like:
        # Source: https://example.com/data.json
    """
    import re
    try:
        text = contract_data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    
    # Look for Source: comment
    match = re.search(r"^#\s*Source:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if match:
        url = match.group(1).strip()
        # Validate it looks like a URL
        if url.startswith(("http://", "https://", "ftp://")):
            return url
    
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="geocontract-harvest",
        description="Federated harvester for geocontract.yaml files.",
    )
    p.add_argument(
        "sources",
        nargs="+",
        help="URL, file path, git URL, or S3 URI of a geocontract.yaml",
    )
    p.add_argument(
        "--out",
        default=".harvest",
        help="Output directory for JSONL sink (default: ./.harvest)",
    )
    p.add_argument(
        "--sink",
        choices=["jsonl", "portolan"],
        default="jsonl",
        help="Output sink: 'jsonl' (default) writes records to .harvest/, 'portolan' writes mirror collections to catalog/mirror/",
    )
    p.add_argument(
        "--catalog-dir",
        default="catalog",
        help="Catalog directory for portolan sink (default: catalog)",
    )
    args = p.parse_args(argv)

    sources = discover(args.sources)

    if args.sink == "portolan":
        # Harvest and write directly to Portolan mirror collections
        results = harvest(sources, Path(args.out))
        harvest_to_portolan(results, Path(args.catalog_dir))
    else:
        # Default JSONL sink
        harvest(sources, Path(args.out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
