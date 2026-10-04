#!/usr/bin/env python3
"""Build the Portolan catalog tree from the ODCS contracts and the manifest.

The catalog under ``catalog/`` is a **generated artifact**. Two inputs drive it:

* ``contracts/*.datacontract.yaml`` — semantics: id, name, description, schema,
  tags, tenant, servers.
* ``catalog/manifests/geocontract.yaml`` — catalog facts: license, bbox, host,
  via landing page, keywords, nested-catalog titles.

Neither input alone is sufficient. ODCS sets ``additionalProperties: false`` and
has no ``license`` field, while Portolan requires a license on every collection
plus an area-of-interest bbox and a host provider. Putting a catalog fact in a
contract YAML fails ``mise run validate-odcs``. So each fact has exactly one
home. See ``docs/portolan-conformance-notes.md`` §F7.

Run it::

    uv run python scripts/build_catalog.py            # write catalog/
    uv run python scripts/build_catalog.py --check    # fail if catalog/ is stale

``--check`` rebuilds in memory and compares against what is committed, so CI can
prove the generated tree matches its inputs. That mirrors how this repo already
treats ``models/*.canonical.graphql``.

The build is deterministic. It writes no timestamp of its own; ``updated`` comes
from the manifest. Rebuilding an unchanged manifest produces no diff.

Provenance is derived, never declared. A collection is a mirror when its
producer differs from the host serving this copy, and ``rashid`` then requires a
``rel: via`` link of type ``text/html``. The generator errors rather than
guessing when a mirror omits provenance. See
``docs/portolan-conformance-notes.md`` §F3 and §F4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG = ROOT / "catalog"
MANIFESTS = CATALOG / "manifests"

# STAC extension URIs. The Portolan profile URI is the single version signal;
# there is no separate version file. Released schemas are immutable, so this
# string is pinned and moves only with a deliberate spec migration.
PORTOLAN_PROFILE = "https://schemas.portolan-sdi.org/portolan/v0.2.0/schema.json"
FILE_EXT = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
TABLE_EXT = "https://stac-extensions.github.io/table/v1.2.0/schema.json"

# ODCS logicalType -> STAC table extension column type. The reference catalog
# uses this vocabulary (varchar, double, timestamp, bigint), so the values below
# are the ones rashid 0.1.8 accepts.
COLUMN_TYPES: dict[str, str] = {
    "string": "varchar",
    "integer": "bigint",
    "number": "double",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "timestamp",
    "time": "time",
    "object": "struct",
    "array": "list",
}


class BuildError(Exception):
    """A manifest or contract fact the generator refuses to guess at."""


# ── validation helpers ────────────────────────────────────────────────────────


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise BuildError(msg)


def validate_bbox(bbox: Any, ctx: str) -> list[float]:
    """Enforce the core.md bounding-box rules.

    Every bbox must carry no NaN or infinite value, no sentinel "effectively
    infinite" value, only WGS84 coordinates in range, and south <= north.
    Garbage here poisons the catalog-level extent union and breaks viewers.
    """
    require(isinstance(bbox, list) and len(bbox) == 4, f"{ctx}: bbox must be a 4-element list [west, south, east, north]")
    vals: list[float] = []
    for v in bbox:
        require(isinstance(v, (int, float)) and not isinstance(v, bool), f"{ctx}: bbox values must be numbers, got {v!r}")
        f = float(v)
        require(not (math.isnan(f) or math.isinf(f)), f"{ctx}: bbox must contain no NaN or infinite value")
        # Guard against the sentinel pattern core.md calls out explicitly.
        require(abs(f) < 1e300, f"{ctx}: bbox must not use a sentinel 'effectively infinite' value ({f})")
        vals.append(f)
    west, south, east, north = vals
    require(-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0, f"{ctx}: longitude out of WGS84 range: {west}, {east}")
    require(-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0, f"{ctx}: latitude out of WGS84 range: {south}, {north}")
    require(south <= north, f"{ctx}: bbox south ({south}) must be <= north ({north})")
    require(west <= east, f"{ctx}: bbox west ({west}) must be <= east ({east})")
    return vals


def validate_updated(value: Any, ctx: str) -> str:
    """An RFC 3339 timestamp string. Required on mirrors as the last sync time."""
    require(isinstance(value, str) and value.strip() != "", f"{ctx}: 'updated' must be a non-empty RFC 3339 string")
    require(value.endswith("Z") or "+" in value or value.count("-") >= 2, f"{ctx}: 'updated' must be RFC 3339, got {value!r}")
    return value


# ── contract reading ──────────────────────────────────────────────────────────


def load_contract(path: Path) -> dict:
    require(path.is_file(), f"contract not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    require(isinstance(data, dict), f"contract is not a mapping: {path}")
    return data


def contract_description(contract: dict) -> str:
    """Collapse the ODCS description object into one collection description.

    ODCS carries purpose, usage, and limitations as separate prose blocks. STAC
    has one description field, so the purpose leads and the rest is preserved in
    the curated README, which the generator seeds from the manifest docs.
    """
    desc = contract.get("description") or {}
    if isinstance(desc, str):
        return " ".join(desc.split())
    parts = []
    for key in ("purpose", "usage", "limitations"):
        val = desc.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(" ".join(val.split()))
    require(bool(parts), "contract description is empty; Portolan requires a non-empty description")
    return parts[0]


def find_entity(contract: dict, name: str, ctx: str) -> dict:
    for ent in contract.get("schema") or []:
        if ent.get("name") == name:
            return ent
    available = [e.get("name") for e in contract.get("schema") or []]
    raise BuildError(f"{ctx}: primary_entity {name!r} not in contract schema; available: {available}")


def build_columns(entity: dict) -> list[dict]:
    """Project ODCS schema properties into STAC table:columns.

    Declaring table:columns is what tells the validator this collection is
    tabular rather than spatial, which removes the thumbnail requirement.
    Without it a non-spatial collection cannot be classified. See
    docs/portolan-conformance-notes.md §F5.
    """
    columns = []
    for prop in entity.get("properties") or []:
        name = prop.get("name")
        if not name:
            continue
        logical = prop.get("logicalType")
        col_type = COLUMN_TYPES.get(str(logical), "varchar")
        desc = prop.get("description")
        columns.append(
            {
                "name": str(name),
                "type": col_type,
                "description": " ".join(str(desc).split()) if desc else f"Field {name} of the contract entity.",
            }
        )
    return columns


# ── asset helpers ─────────────────────────────────────────────────────────────


def multihash_sha256(data: bytes) -> str:
    """A multihash checksum: 0x12 (sha2-256), 0x20 (32-byte digest), then hex."""
    return "1220" + hashlib.sha256(data).hexdigest()


def file_meta(data: bytes) -> dict:
    return {"file:size": len(data), "file:checksum": multihash_sha256(data)}


# ── providers and provenance ──────────────────────────────────────────────────


def build_providers(entry: dict, host: dict) -> tuple[list[dict], bool]:
    """Return (providers, is_mirror).

    Mirror status is derived, not declared. When no producer entry carries a
    host role, the catalog host is appended with role host only and the
    collection is a mirror. When a producer also hosts, the collection is
    official and the host is not appended twice.
    """
    require(isinstance(host, dict) and host.get("name"), "manifest 'host' must name an organisation")
    host_entry: dict[str, Any] = {"name": host["name"]}
    if host.get("url"):
        host_entry["url"] = host["url"]
    if host.get("email"):
        host_entry["email"] = host["email"]

    producers = entry.get("producers") or []
    if not producers:
        # Official: geocontract originates this data, so it produces and hosts.
        host_entry["roles"] = ["producer", "licensor", "host"]
        return [host_entry], False

    out: list[dict] = []
    producer_hosts = False
    for p in producers:
        require(isinstance(p, dict) and p.get("name"), f"manifest producers entry must name an organisation: {p!r}")
        roles = list(p.get("roles") or ["producer"])
        require("producer" in roles, f"producers entry {p['name']!r} must carry the producer role")
        pe: dict[str, Any] = {"name": p["name"]}
        if p.get("url"):
            pe["url"] = p["url"]
        if p.get("email"):
            pe["email"] = p["email"]
        pe["roles"] = roles
        out.append(pe)
        if "host" in roles:
            producer_hosts = True

    if producer_hosts:
        return out, False

    host_entry["roles"] = ["host"]
    out.append(host_entry)
    return out, True


def build_provenance_links(entry: dict, is_mirror: bool, ctx: str) -> list[dict]:
    """The via link a mirror must carry, plus the optional upstream data link."""
    links: list[dict] = []
    prov = entry.get("provenance") or {}

    if is_mirror:
        via = prov.get("via")
        require(bool(via), f"{ctx}: mirror collection requires provenance.via (PTL-PRO-001 is an error without it)")
        require(
            isinstance(via, str) and via.startswith("https://"),
            f"{ctx}: provenance.via must be an https URL, got {via!r}",
        )
        # The via link is a human landing page. A raw data endpoint here fails
        # validation because the type must be text/html.
        links.append({"rel": "via", "href": via, "type": "text/html", "title": "Original source"})

        updated = prov.get("updated")
        require(bool(updated), f"{ctx}: mirror collection requires provenance.updated as the last sync time")
        validate_updated(updated, f"{ctx} provenance")

    upstream = entry.get("upstream_data")
    if upstream:
        require(
            isinstance(upstream, str) and upstream.startswith("https://"),
            f"{ctx}: upstream_data must be an https URL, got {upstream!r}",
        )
        links.append({"rel": "related", "href": upstream, "type": "application/json", "title": "Upstream raw payload"})

    return links


def resolve_updated(entry: dict, contract: dict, is_mirror: bool, ctx: str) -> str:
    """Deterministic 'updated'. Never the build clock, or every rebuild diffs."""
    prov = entry.get("provenance") or {}
    for candidate in (prov.get("updated"), entry.get("updated")):
        if candidate:
            return validate_updated(candidate, ctx)
    if is_mirror:
        raise BuildError(f"{ctx}: mirror requires an 'updated' timestamp; set provenance.updated in the manifest")
    created = contract.get("contractCreatedTs")
    require(bool(created), f"{ctx}: no updated in manifest and no contractCreatedTs in contract")
    return validate_updated(str(created), ctx)


# ── document seeding ──────────────────────────────────────────────────────────


def seed_doc(path: Path, title: str, body: str | None, kind: str) -> bool:
    """Write a curated doc only when absent. Returns True if it created the file.

    README.md and AGENTS.md are curated, not generated. The generator seeds them
    once so the required sections exist, then leaves them alone. Overwriting
    would destroy human prose on every rebuild.
    """
    if path.exists():
        return False
    if body and body.strip():
        content = f"# {title}\n\n{body.strip()}\n"
    else:
        content = (
            f"# {title}\n\n"
            f"Describe this {kind} here. Keep sentences short and state one idea "
            f"each. Mention provenance and license: rashid warns when a README "
            f"omits either (PTL-FIL-005).\n"
        )
    path.write_text(content, encoding="utf-8")
    return True


# ── builders ──────────────────────────────────────────────────────────────────


def build_collection(entry: dict, manifest: dict, out_root: Path) -> tuple[str, dict]:
    """Build one collection.json and stage its assets. Returns (theme, doc)."""
    cid = entry.get("id")
    require(isinstance(cid, str) and cid.count("/") == 1, f"collection id must be '<theme>/<slug>', got {cid!r}")
    theme, slug = cid.split("/", 1)
    require(theme in (manifest.get("catalogs") or {}), f"collection {cid!r}: theme {theme!r} is not declared under manifest 'catalogs'")
    ctx = f"collection {cid}"

    contract_path = ROOT / str(entry.get("contract") or "")
    contract = load_contract(contract_path)

    license_id = entry.get("license")
    require(bool(license_id), f"{ctx}: license is required by Portolan and ODCS has no license field, so it comes from the manifest")
    require(str(license_id).lower() != "proprietary", f"{ctx}: Portolan bans license 'proprietary'")

    bbox = validate_bbox(entry.get("bbox"), ctx)
    providers, is_mirror = build_providers(entry, manifest["host"])
    prov_links = build_provenance_links(entry, is_mirror, ctx)
    updated = resolve_updated(entry, contract, is_mirror, ctx)

    entity_name = entry.get("primary_entity")
    require(bool(entity_name), f"{ctx}: primary_entity is required so table:columns can be derived")
    entity = find_entity(contract, entity_name, ctx)
    columns = build_columns(entity)
    require(bool(columns), f"{ctx}: primary_entity {entity_name!r} has no properties, so table:columns would be empty")

    # Stage the contract as the metadata-role asset. A metadata-only collection
    # is valid: no data-role asset is required. See conformance notes §F1.
    cdir = out_root / theme / slug
    cdir.mkdir(parents=True, exist_ok=True)
    asset_name = contract_path.name
    asset_bytes = contract_path.read_bytes()
    (cdir / asset_name).write_bytes(asset_bytes)

    keywords = list(entry.get("keywords") or [])
    if not keywords:
        keywords = [str(t) for t in (contract.get("tags") or [])]

    temporal = entry.get("temporal") or [str(contract.get("contractCreatedTs") or updated), None]
    require(isinstance(temporal, list) and len(temporal) == 2, f"{ctx}: temporal must be a 2-element interval")

    doc: dict[str, Any] = {
        "type": "Collection",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_PROFILE, FILE_EXT, TABLE_EXT],
        "id": cid,
        "title": str(contract.get("name") or slug),
        "description": contract_description(contract),
        "license": str(license_id),
        "keywords": keywords,
        "providers": providers,
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [temporal]},
        },
        "table:columns": columns,
        "assets": {
            "contract": {
                "href": f"./{asset_name}",
                "type": "application/yaml",
                "title": f"ODCS v3.1.0 data contract ({contract.get('id')})",
                "roles": ["metadata"],
                **file_meta(asset_bytes),
            }
        },
        "links": [
            {"rel": "root", "href": "../../catalog.json", "type": "application/json"},
            {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
            *prov_links,
            {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
            {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
        ],
        "updated": updated,
        # Custom prefixed properties are tolerated by the profile schema. They
        # carry the contract facts a consumer needs without opening the asset.
        # See conformance notes §F2.
        "geocontract:contract_id": str(contract.get("id") or ""),
        "geocontract:contract_version": str(contract.get("version") or ""),
        "geocontract:status": str(contract.get("status") or ""),
        "geocontract:tenant": str(contract.get("tenant") or ""),
        "geocontract:domain": str(contract.get("domain") or ""),
        "geocontract:primary_entity": str(entity_name),
        "geocontract:mirror": is_mirror,
    }

    if str(license_id) == "other":
        license_url = entry.get("license_url")
        require(bool(license_url), f"{ctx}: license 'other' requires license_url so the generator can emit rel=license")
        doc["links"].insert(2, {"rel": "license", "href": str(license_url), "type": "text/html", "title": "License"})

    language = manifest.get("language")
    if isinstance(language, dict) and language.get("code"):
        doc["language"] = {"code": language["code"], "name": language.get("name", language["code"])}

    docs = entry.get("docs") or {}
    seed_doc(cdir / "README.md", doc["title"], docs.get("readme"), "collection")
    seed_doc(cdir / "AGENTS.md", f"Agent Guidance, {doc['title']}", docs.get("agents"), "collection")

    return theme, doc


def build_subcatalog(theme: str, spec: dict, children: list[dict], manifest: dict, out_root: Path) -> dict:
    tdir = out_root / theme
    tdir.mkdir(parents=True, exist_ok=True)
    title = str(spec.get("title") or theme)
    doc: dict[str, Any] = {
        "type": "Catalog",
        "stac_version": "1.1.0",
        "stac_extensions": [PORTOLAN_PROFILE],
        "id": theme,
        "title": title,
        "description": " ".join(str(spec.get("description") or title).split()),
        "links": [
            {"rel": "root", "href": "../catalog.json", "type": "application/json"},
            {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
            *[
                {"rel": "child", "href": f"./{c['id'].split('/', 1)[1]}/collection.json", "type": "application/json", "title": c["title"]}
                for c in children
            ],
            {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
            {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
        ],
        "updated": _catalog_updated(children, manifest),
    }
    language = manifest.get("language")
    if isinstance(language, dict) and language.get("code"):
        doc["language"] = {"code": language["code"], "name": language.get("name", language["code"])}

    seed_doc(tdir / "README.md", title, spec.get("readme"), "sub-catalog")
    seed_doc(tdir / "AGENTS.md", f"Agent Guidance, {title}", spec.get("agents"), "sub-catalog")
    return doc


def _catalog_updated(children: list[dict], manifest: dict) -> str:
    """The newest child timestamp, so a catalog stamp never exceeds its contents."""
    stamps = [str(c.get("updated") or "") for c in children]
    stamps = [s for s in stamps if s]
    if stamps:
        return max(stamps)
    return validate_updated(str(manifest.get("updated") or ""), "manifest")


def build_root(manifest: dict, themes: list[tuple[str, dict]], out_root: Path) -> dict:
    title = str(manifest.get("title") or manifest.get("id"))
    children = []
    for theme, tdoc in themes:
        children.append({"rel": "child", "href": f"./{theme}/catalog.json", "type": "application/json", "title": tdoc["title"]})
    
    # Preserve existing child links that aren't part of the manifest themes
    # (e.g., mirror sub-catalog added by the harvester)
    existing_catalog = out_root / "catalog.json"
    if existing_catalog.exists():
        existing_data = json.loads(existing_catalog.read_text())
        theme_hrefs = {f"./{theme}/catalog.json" for theme, _ in themes}
        for link in existing_data.get("links", []):
            if link.get("rel") == "child" and link.get("href") not in theme_hrefs:
                # This is an additional child link (e.g., mirror), preserve it
                children.append(link)
    
    doc: dict[str, Any] = {
        "type": "Catalog",
        "stac_version": "1.1.0",
        "stac_extensions": [manifest.get("schema_uri") or PORTOLAN_PROFILE],
        "id": str(manifest.get("id")),
        "title": title,
        "description": " ".join(str(manifest.get("description") or title).split()),
        "links": [
            {"rel": "root", "href": "./catalog.json", "type": "application/json"},
            *children,
            {"rel": "agents", "href": "./AGENTS.md", "type": "text/markdown", "title": "Guidance for AI agents", "hreflang": "en"},
            {"rel": "describedby", "href": "./README.md", "type": "text/markdown", "title": "Human-readable documentation", "hreflang": "en"},
        ],
        "updated": _catalog_updated([t for _, t in themes], manifest),
    }
    language = manifest.get("language")
    if isinstance(language, dict) and language.get("code"):
        doc["language"] = {"code": language["code"], "name": language.get("name", language["code"])}

    seed_doc(out_root / "README.md", title, manifest.get("readme"), "catalog")
    seed_doc(out_root / "AGENTS.md", f"Agent Guidance, {title}", manifest.get("agents"), "catalog")
    return doc


# ── driver ────────────────────────────────────────────────────────────────────


def render(doc: dict) -> str:
    """Stable JSON text. Insertion order is semantic, so keys are not sorted."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def build(manifest_path: Path, out_root: Path) -> dict[str, str]:
    """Build the whole tree under out_root. Returns {relative path: text}."""
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), f"manifest is not a mapping: {manifest_path}")
    require(bool(manifest.get("id")), "manifest must declare an id")
    require(isinstance(manifest.get("host"), dict), "manifest must declare a host provider")

    collections = manifest.get("collections") or []
    require(bool(collections), "manifest declares no collections")

    seen: set[str] = set()
    by_theme: dict[str, list[dict]] = {}
    written: dict[str, str] = {}

    for entry in collections:
        require(isinstance(entry, dict) and entry.get("id"), f"collection entry must be a mapping with an id: {entry!r}")
        cid = str(entry["id"])
        require(cid not in seen, f"duplicate collection id: {cid}")
        seen.add(cid)
        theme, doc = build_collection(entry, manifest, out_root)
        by_theme.setdefault(theme, []).append(doc)
        written[f"{theme}/{doc['id'].split('/', 1)[1]}/collection.json"] = render(doc)

    themes: list[tuple[str, dict]] = []
    catalog_specs = manifest.get("catalogs") or {}
    for theme in sorted(by_theme):
        tdoc = build_subcatalog(theme, catalog_specs[theme], by_theme[theme], manifest, out_root)
        themes.append((theme, tdoc))
        written[f"{theme}/catalog.json"] = render(tdoc)

    root = build_root(manifest, themes, out_root)
    written["catalog.json"] = render(root)
    return written


def write_tree(written: dict[str, str], out_root: Path) -> None:
    for rel, text in sorted(written.items()):
        path = out_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def check_tree(written: dict[str, str], out_root: Path) -> int:
    """Compare the build against what is committed. Returns a process exit code."""
    drift = []
    for rel, text in sorted(written.items()):
        path = out_root / rel
        if not path.exists():
            drift.append(f"missing: catalog/{rel}")
        elif path.read_text(encoding="utf-8") != text:
            drift.append(f"stale:   catalog/{rel}")
    if drift:
        print("catalog/ is out of date with its inputs:", file=sys.stderr)
        for line in drift:
            print(f"  {line}", file=sys.stderr)
        print("\nRun `mise run catalog-build` and commit the result.", file=sys.stderr)
        return 1
    print(f"OK   catalog/ is current ({len(written)} generated files)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default=str(MANIFESTS / "geocontract.yaml"), help="catalog manifest to build from")
    parser.add_argument("--check", action="store_true", help="fail if catalog/ does not match the build, without writing")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    require(manifest_path.is_file(), f"manifest not found: {manifest_path}")

    if args.check:
        # Build into a throwaway tree so seeded docs and staged assets do not
        # touch the committed catalog.
        tmp = CATALOG.parent / ".catalog-build-check"
        if tmp.exists():
            shutil.rmtree(tmp)
        try:
            written = build(manifest_path, tmp)
            return check_tree(written, CATALOG)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)

    written = build(manifest_path, CATALOG)
    write_tree(written, CATALOG)
    for rel in sorted(written):
        print(f"OK   wrote catalog/{rel}")
    print(f"\n{len(written)} generated files. Validate with `mise run catalog-check`.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
