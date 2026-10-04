#!/usr/bin/env python3
"""Publish the Portolan catalog to the configured destination.

This script syncs the catalog/ directory to a destination (local directory or
S3-compatible bucket) with a dry-run/confirm pattern. It validates the catalog
with rashid before publishing and never deletes files by default.

Usage:
    python3 tools/publish.py            # dry run, shows what would be published
    python3 tools/publish.py --confirm  # actually publish; needs credentials

Configuration is read from catalog.publish.yaml. The destination can be:
- A local directory (for testing): destination: file:///path/to/dir
- An S3-compatible bucket: destination: s3://bucket-name/prefix

The script compares local files against the destination and only uploads
changed files. Change detection uses file size and MD5 checksum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "catalog"
CONFIG_FILE = ROOT / "catalog.publish.yaml"


class PublishError(Exception):
    """Configuration or validation error that blocks publishing."""


def load_config() -> dict[str, Any]:
    """Load and validate the publish configuration."""
    if not CONFIG_FILE.exists():
        raise PublishError(
            f"Configuration file not found: {CONFIG_FILE}\n"
            "Create catalog.publish.yaml with destination and public_base."
        )
    
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    
    if not isinstance(config, dict):
        raise PublishError("catalog.publish.yaml must be a YAML mapping")
    
    # Check for sentinel values that indicate incomplete setup
    for key in ("destination", "public_base"):
        value = config.get(key, "")
        if isinstance(value, str) and "TODO" in value:
            raise PublishError(
                f"Configuration has placeholder value for '{key}': {value}\n"
                "Edit catalog.publish.yaml before publishing."
            )
    
    required = ["destination", "public_base"]
    for key in required:
        if key not in config:
            raise PublishError(f"catalog.publish.yaml missing required key: {key}")
    
    return config


def validate_catalog() -> None:
    """Run rashid to validate the catalog before publishing."""
    import subprocess
    
    print("Validating catalog with rashid...")
    result = subprocess.run(
        ["uvx", "--from", "rashid>=0.1.8,<0.2.0", "rashid", "check", str(CATALOG_DIR), "--no-data", "--summary"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise PublishError("Catalog validation failed. Fix errors before publishing.")
    
    # Print validation summary
    for line in result.stdout.split("\n"):
        if "error(s)" in line or "warning(s)" in line:
            print(f"  {line.strip()}")


def file_checksum(path: Path) -> str:
    """Compute MD5 checksum of a file."""
    md5 = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def content_type_for(path: Path) -> str:
    """Determine Content-Type from file extension."""
    suffix = path.suffix.lower()
    types = {
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".md": "text/markdown",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".parquet": "application/vnd.apache.parquet",
        ".cog": "image/tiff; application=geotiff",
        ".pmtiles": "application/vnd.pmtiles",
    }
    return types.get(suffix, "application/octet-stream")


class LocalPublisher:
    """Publish to a local directory (for testing)."""
    
    def __init__(self, dest_path: Path, public_base: str):
        self.dest_path = dest_path
        self.public_base = public_base.rstrip("/")
        self.dest_path.mkdir(parents=True, exist_ok=True)
    
    def list_remote(self) -> dict[str, dict[str, Any]]:
        """List files in destination with size and checksum."""
        files = {}
        for path in self.dest_path.rglob("*"):
            if path.is_file():
                rel = path.relative_to(self.dest_path)
                files[str(rel)] = {
                    "size": path.stat().st_size,
                    "checksum": file_checksum(path),
                }
        return files
    
    def upload(self, local_path: Path, remote_key: str, dry_run: bool) -> bool:
        """Upload a file. Returns True if uploaded, False if skipped."""
        dest_file = self.dest_path / remote_key
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        
        if not dry_run:
            dest_file.write_bytes(local_path.read_bytes())
        
        return True
    
    def public_url(self, remote_key: str) -> str:
        """Return the public URL for a remote key."""
        return f"{self.public_base}/{remote_key}"


class S3Publisher:
    """Publish to an S3-compatible bucket."""
    
    def __init__(self, bucket: str, prefix: str, public_base: str, region: str | None = None):
        if boto3 is None:
            raise PublishError("boto3 not installed. Run: pip install boto3")
        
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.public_base = public_base.rstrip("/")
        self.region = region
        
        session_kwargs = {}
        if region:
            session_kwargs["region_name"] = region
        
        self.s3 = boto3.client("s3", **session_kwargs)
    
    def _key(self, remote_path: str) -> str:
        """Build the S3 key from a relative path."""
        if self.prefix:
            return f"{self.prefix}/{remote_path}"
        return remote_path
    
    def list_remote(self) -> dict[str, dict[str, Any]]:
        """List files in bucket with size and ETag (checksum)."""
        files = {}
        paginator = self.s3.get_paginator("list_objects_v2")
        
        params = {"Bucket": self.bucket}
        if self.prefix:
            params["Prefix"] = self.prefix + "/"
        
        for page in paginator.paginate(**params):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Remove prefix to get relative path
                if self.prefix and key.startswith(self.prefix + "/"):
                    rel = key[len(self.prefix) + 1:]
                else:
                    rel = key
                
                # ETag is the MD5 checksum (without quotes)
                etag = obj.get("ETag", "").strip('"')
                files[rel] = {
                    "size": obj["Size"],
                    "checksum": etag,
                }
        
        return files
    
    def upload(self, local_path: Path, remote_key: str, dry_run: bool) -> bool:
        """Upload a file to S3. Returns True if uploaded, False if skipped."""
        key = self._key(remote_key)
        content_type = content_type_for(local_path)
        
        if not dry_run:
            with open(local_path, "rb") as fh:
                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=fh,
                    ContentType=content_type,
                )
        
        return True
    
    def public_url(self, remote_key: str) -> str:
        """Return the public URL for a remote key."""
        key = self._key(remote_key)
        return f"{self.public_base}/{key}"


def get_publisher(config: dict[str, Any]) -> LocalPublisher | S3Publisher:
    """Create a publisher from the configuration."""
    destination = config["destination"]
    public_base = config["public_base"]
    
    if destination.startswith("file://"):
        path = Path(destination[7:])
        return LocalPublisher(path, public_base)
    elif destination.startswith("s3://"):
        # Parse s3://bucket/prefix
        parts = destination[5:].split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        region = config.get("region")
        return S3Publisher(bucket, prefix, public_base, region)
    else:
        raise PublishError(f"Unsupported destination scheme: {destination}")


def list_local_files() -> dict[str, Path]:
    """List all files in catalog/ directory."""
    files = {}
    for path in CATALOG_DIR.rglob("*"):
        if path.is_file():
            rel = path.relative_to(CATALOG_DIR)
            files[str(rel)] = path
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually publish. Without this flag, performs a dry run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Upload even if size matches (content type may have changed).",
    )
    args = parser.parse_args(argv)
    
    try:
        # Load configuration
        config = load_config()
        print(f"Publishing to: {config['destination']}")
        
        # Validate catalog
        validate_catalog()
        
        # Create publisher
        publisher = get_publisher(config)
        
        # List local and remote files
        local_files = list_local_files()
        remote_files = publisher.list_remote()
        
        print(f"\nLocal files: {len(local_files)}")
        print(f"Remote files: {len(remote_files)}")
        
        # Determine what to upload
        to_upload = []
        for rel_path, local_path in sorted(local_files.items()):
            local_size = local_path.stat().st_size
            local_checksum = file_checksum(local_path)
            
            remote = remote_files.get(rel_path)
            if remote is None:
                # New file
                to_upload.append((rel_path, local_path, "new"))
            elif args.force or remote["size"] != local_size or remote["checksum"] != local_checksum:
                # Changed file
                to_upload.append((rel_path, local_path, "changed"))
            # else: unchanged, skip
        
        if not to_upload:
            print("\nNo changes to publish.")
            return 0
        
        print(f"\nFiles to publish: {len(to_upload)}")
        for rel_path, local_path, status in to_upload:
            size = local_path.stat().st_size
            print(f"  {status:7s}  {rel_path:50s}  ({size:,} bytes)")
        
        if not args.confirm:
            print("\nDry run. Use --confirm to actually publish.")
            return 0
        
        # Upload files
        print(f"\nPublishing {len(to_upload)} files...")
        for rel_path, local_path, status in to_upload:
            publisher.upload(local_path, rel_path, dry_run=False)
            print(f"  ✓ {rel_path}")
        
        print(f"\nPublished {len(to_upload)} files to {config['destination']}")
        return 0
    
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ClientError as exc:
        print(f"error: S3 error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
