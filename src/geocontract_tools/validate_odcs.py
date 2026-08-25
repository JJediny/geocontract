"""Validate ODCS v3.1.0 data contract YAML files against the canonical schema.

Usage:
    python scripts/validate_odcs.py contracts/*.yaml
    python scripts/validate_odcs.py --shim contracts/shim/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    raise

try:
    from jsonschema import Draft201909Validator, Draft202012Validator
except ImportError:
    print("ERROR: jsonschema required. Install with: pip install jsonschema", file=sys.stderr)
    raise


# This file lives at <repo>/src/geocontract_tools/validate_odcs.py,
# so three .parent walks land us on <repo>.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ODCS_SCHEMA = REPO_ROOT / "external" / "odcs-json-schema-v3.1.0.json"
SHIM_REFERENCE = REPO_ROOT / "external" / "datacontract-shim.rs"


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the geocontract repo root by walking up from a starting path.

    The root is the nearest ancestor containing
    ``external/odcs-json-schema-v3.1.0.json``. Returns ``start`` if not
    found, so tests using tmp_path can still run.
    """
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / "external" / "odcs-json-schema-v3.1.0.json").exists():
            return candidate
    return start or Path.cwd()


def load_odcs_schema() -> dict:
    """Load and return the canonical ODCS v3.1.0 JSON Schema."""
    return json.loads(ODCS_SCHEMA.read_text())


def validate_odcs_yaml(path: Path, schema: dict) -> list[str]:
    """Validate a single ODCS v3.1.0 YAML file. Returns list of error messages."""
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return [f"Top-level YAML must be a mapping, got {type(doc).__name__}"]

    # ODCS v3.1.0 uses draft 2019-09
    v = Draft201909Validator(schema)
    errors: list[str] = []
    for err in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        path_str = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"  {path_str}: {err.message[:200]}")
    return errors


def validate_shim_json(path: Path) -> list[str]:
    """Validate a shim JSON file matches the Rust DataContractShim struct shape.

    The shim is not formally speced; we structurally validate against the
    canonical Rust type definitions in external/datacontract-shim.rs so that
    `jxql --output-format yaml --shim <path>` accepts the file.
    """
    required_top = ["version", "contract"]
    allowed_top = [
        "version", "schema", "contract", "ownership", "quality", "sla",
        "lineage", "retention", "access", "lifecycle", "partitioning",
        "cost", "tags", "entities",
    ]

    errors: list[str] = []
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]

    if not isinstance(doc, dict):
        return ["Shim must be a JSON object"]

    for k in required_top:
        if k not in doc:
            errors.append(f"  missing required key: {k}")
    for k in doc.keys():
        if k not in allowed_top:
            errors.append(f"  unexpected key: {k}")

    c = doc.get("contract")
    if isinstance(c, dict):
        for k in ("name", "version"):
            if k not in c:
                errors.append(f"  contract.{k}: missing required field")

    q = doc.get("quality") or []
    if isinstance(q, list):
        for i, entry in enumerate(q):
            if not isinstance(entry, dict):
                errors.append(f"  quality[{i}]: must be an object")
                continue
            if "metric" not in entry:
                errors.append(f"  quality[{i}]: missing 'metric'")
            if "threshold" not in entry:
                errors.append(f"  quality[{i}]: missing 'threshold'")

    return errors


def validate_paths(paths: Iterable[Path], *, shim: bool = False, quiet: bool = False) -> int:
    """Validate the given files. Returns 0 on success, 1 on any failure."""
    if shim:
        any_fail = False
        for f in paths:
            errors = validate_shim_json(Path(f))
            if errors:
                any_fail = True
                print(f"FAIL {f}")
                for e in errors:
                    print(e)
            elif not quiet:
                print(f"OK   {f}")
        return 1 if any_fail else 0

    schema = load_odcs_schema()
    any_fail = False
    for f in paths:
        errors = validate_odcs_yaml(Path(f), schema)
        if errors:
            any_fail = True
            print(f"FAIL {f}")
            for e in errors:
                print(e)
        elif not quiet:
            print(f"OK   {f}")
    return 1 if any_fail else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="geocontract-validate",
        description="Validate ODCS v3.1.0 YAML data contracts and Rust-shim JSON files.",
    )
    p.add_argument("files", nargs="+", help="YAML or JSON contract files")
    p.add_argument("--shim", action="store_true", help="Treat inputs as shim JSON, not ODCS YAML")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    return validate_paths(args.files, shim=args.shim, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
