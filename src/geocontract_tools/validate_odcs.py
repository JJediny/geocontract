"""Validate ODCS v3.1.0 data contract YAML files against the canonical schema.

Usage:
    python scripts/validate_odcs.py contracts/*.yaml
    python scripts/validate_odcs.py --shim contracts/shim/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

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

try:
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
except ImportError:  # pragma: no cover - referencing ships with jsonschema>=4.18
    Registry = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    DRAFT202012 = None  # type: ignore[assignment]


# This file lives at <repo>/src/geocontract_tools/validate_odcs.py,
# so three .parent walks land us on <repo>.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ODCS_SCHEMA = REPO_ROOT / "external" / "odcs-json-schema-v3.1.0.json"
MASTER_SCHEMA = REPO_ROOT / "external" / "geocontract-master.schema.json"
DCAT_US_SCHEMA = REPO_ROOT / "external" / "dcat-us-catalog.json"
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


def load_master_schema() -> dict:
    """Load and return the geocontract master schema (ODCS + embeddedSchemas).

    Falls back to :func:`load_odcs_schema` if the derivative master schema
    has not been generated yet (e.g. on a fresh checkout before
    ``scripts/build_master_schema.py`` has run).
    """
    if MASTER_SCHEMA.exists():
        return json.loads(MASTER_SCHEMA.read_text())
    return load_odcs_schema()


def load_dcat_us_schema() -> dict:
    """Load and return the pinned DCAT-US 3.0.0 Catalog JSON Schema."""
    return json.loads(DCAT_US_SCHEMA.read_text())


def _dcat_us_registry():
    """Build a referencing.Registry that maps the lowercase DCAT-US
    definition URIs to the locally-pinned JSON Schemas under
    ``external/dcat-us-definitions/``. This avoids any network fetches
    during validation.

    Returns ``None`` if the ``referencing`` package is unavailable
    (older jsonschema installs); callers should fall back to a plain
    validator in that case and accept the network fetch.
    """
    if Registry is None:
        return None
    defs_dir = REPO_ROOT / "external" / "dcat-us-definitions"
    if not defs_dir.is_dir():
        return None
    entries: list[tuple[str, Resource]] = []
    for path in sorted(defs_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        rid = doc.get("$id") or f"https://resources.data.gov/dcat-us/3.0.0/definitions/{path.stem.lower()}"
        entries.append((rid, Resource.from_contents(doc, default_specification=DRAFT202012)))
    return Registry().with_resources(entries)


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


def validate_dcat_us_json(path: Path, schema: dict, registry=None) -> list[str]:
    """Validate a JSON instance against the DCAT-US 3.0.0 Catalog schema.

    Returns a list of human-readable error messages; empty on success.
    Uses Draft 2020-12 (DCAT-US 3 is published against that draft). If
    a ``referencing.Registry`` is supplied, the validator resolves the
    sub-definition ``$ref`` paths (``/dcat-us/3.0.0/definitions/<x>``)
    against it instead of fetching them over the network.
    """
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    if not isinstance(doc, dict):
        return [f"Top-level JSON must be an object, got {type(doc).__name__}"]

    kwargs = {"registry": registry} if registry is not None else {}
    v = Draft202012Validator(schema, **kwargs)
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
    for k in doc:
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


def validate_embedded_schemas(doc: dict) -> list[str]:
    """Structurally validate the ``embeddedSchemas`` block of a contract.

    Each value must be a JSON-Schema-shaped object (the master schema's
    ``anyOf`` already enforces this at the schema level; this function
    reports human-readable errors for the common mistakes, e.g. a value
    that is a data instance rather than a schema).
    """
    errors: list[str] = []
    embedded = doc.get("embeddedSchemas")
    if embedded is None:
        return errors
    if not isinstance(embedded, dict):
        return ["  embeddedSchemas: must be an object (map of name → JSON Schema)"]
    markers = {"type", "$ref", "properties", "allOf", "oneOf", "anyOf", "enum", "const"}
    for name, value in embedded.items():
        if not isinstance(value, dict):
            errors.append(f"  embeddedSchemas.{name}: must be a JSON Schema object, got {type(value).__name__}")
            continue
        if not (markers & set(value.keys())):
            errors.append(
                f"  embeddedSchemas.{name}: does not look like a JSON Schema "
                f"(expected one of {sorted(markers)}; got keys {sorted(value.keys())})"
            )
    return errors


def validate_paths(
    paths: Iterable[Path],
    *,
    shim: bool = False,
    dcat: bool = False,
    master: bool = False,
    quiet: bool = False,
) -> int:
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

    if dcat:
        schema = load_dcat_us_schema()
        registry = _dcat_us_registry()
        any_fail = False
        for f in paths:
            errors = validate_dcat_us_json(Path(f), schema, registry=registry)
            if errors:
                any_fail = True
                print(f"FAIL {f}")
                for e in errors:
                    print(e)
            elif not quiet:
                print(f"OK   {f}")
        return 1 if any_fail else 0

    schema = load_master_schema() if master else load_odcs_schema()
    any_fail = False
    for f in paths:
        path = Path(f)
        errors = validate_odcs_yaml(path, schema)
        if master and not errors:
            # Second pass: human-readable checks on the embeddedSchemas block.
            import yaml as _yaml
            try:
                doc = _yaml.safe_load(path.read_text())
                if isinstance(doc, dict):
                    errors = validate_embedded_schemas(doc)
            except _yaml.YAMLError:
                pass
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
    p.add_argument(
        "--dcat",
        action="store_true",
        help="Treat inputs as DCAT-US Catalog JSON instances (validated against the pinned DCAT-US 3.0.0 schema)",
    )
    p.add_argument(
        "--master",
        action="store_true",
        help="Validate against the geocontract master schema (ODCS v3.1.0 + embeddedSchemas extension). Generates human-readable errors for malformed embedded schemas.",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    return validate_paths(args.files, shim=args.shim, dcat=args.dcat, master=args.master, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
