"""Tests for the geocontract_tools.harvester design stub."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.harvester import (  # noqa: E402
    HarvestSource,
    discover,
    harvest,
)


def test_discover_classifies_urls() -> None:
    out = discover(["https://example.com/x.yaml", "http://x/y.yaml"])
    assert all(s.kind == "url" for s in out)


def test_discover_classifies_files() -> None:
    out = discover(["./contracts/a.yaml", "/abs/path/b.yaml"])
    assert all(s.kind == "file" for s in out)


def test_discover_classifies_git() -> None:
    out = discover([
        "git@github.com:foo/bar.git",
        "https://github.com/foo/bar.git",
        "git+https://x/y.git",
    ])
    assert all(s.kind == "git" for s in out)


def test_discover_preserves_order() -> None:
    inputs = ["https://a/x", "./b", "git@github.com:x/y.git"]
    out = discover(inputs)
    assert [s.location for s in out] == inputs


def test_harvest_writes_manifest(tmp_path: Path) -> None:
    sources = [
        HarvestSource("https://example.com/x.yaml", "url"),
        HarvestSource("./y.yaml", "file"),
    ]
    harvest(sources, tmp_path)
    manifest = tmp_path / "manifest.json"
    assert manifest.exists()
    assert "example.com/x.yaml" in manifest.read_text()
    assert "./y.yaml" in manifest.read_text()
