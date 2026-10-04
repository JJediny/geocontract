#!/usr/bin/env python3
"""Build DataCite v4.3 JSON records from the generated Portolan tree (issue #21).

Mirrors `build_dcat.py`, one record per unique contract instead of one
catalog instance. The generator walks `catalog/**/collection.json`,
reads the ODCS contract beside each collection, and writes one DataCite
v4.3 record per unique contract id to
`examples/datacite4.3/<contract_id>.json`. Mirror duplicates collapse by
contract id like the DCAT build.

Determinism: records sort by collection id, keys follow the DataCite
schema's required order, and every timestamp derives from a generated
collection or the contract's own `contractCreatedTs`. Re-running the
generator on an unchanged tree is a byte-for-byte no-op.

Mapping choices, settled in docs/datacite-validation-notes.md:

- `identifiers` use canonical source URLs (git raw) rather than invented
  DOI-bearing IRIs. Minting DOIs is a later step; the `datacite`
  PyPI package (inveniosoftware) is the wrapper for it, and a local
  Invenio RDM docker-compose stack is the full ingest-validation
  harness.
- `fundingReferences` are omitted unless a contract carries funding
  facts. True on-chain payment evidence stays outside DataCite
  (`relatedIdentifiers` points at a separate artifact), per issue #21.

Validation: `mise run datacite-check` rebuilds then validates every
record against the vendored DataCite 4.3 JSON Schema (see
`scripts/validate_odcs.py --datacite`).
"""
from __future__ import annotations

import json
import sys

import yaml

from geocontract_tools.build_dcat import (
    LICENSE_IRI,
    ROOT,
    base_idiri,
    catalog_keywords,
    collections_updated,
    entry_repo_path,
    issuer,
    load_collections,
    source_of_record,
    text,
)

OUT_DIR = ROOT / "examples" / "datacite4.3"
CDC_SCHEMA_VERSION = "http://datacite.org/schema/kernel-4"
RAW_BASE = "https://raw.githubusercontent.com/JJediny/geocontract/main"


def build_record(entry: dict) -> dict:
    collection = entry["collection"]
    contract: dict = yaml.safe_load(entry["contract_path"].read_text())

    contract_id = collection.get("geocontract:contract_id", contract.get("id", ""))
    contract_version = collection.get("geocontract:contract_version", contract.get("version", ""))
    providers = collection.get("providers", [])
    producers = [p for p in providers if "producer" in p.get("roles", [])]
    hosts = [p for p in providers if "host" in p.get("roles", [])]
    publisher_name = hosts[0]["name"] if hosts else "geocontract"

    issued = issuer(contract) or collections_updated(collection)
    updated = collections_updated(collection)
    repo_path = entry_repo_path(collection)
    identifier = f"{RAW_BASE}/{repo_path}"

    creators = [
        {"name": p["name"], "nameType": "Organizational"}
        for p in (producers or [{"name": publisher_name}])
    ]

    dates: list[dict] = []
    if issued:
        dates.append({"date": issued, "dateType": "Created"})
    if updated and updated != issued:
        dates.append({"date": updated, "dateType": "Updated"})

    related: list[dict] = []
    source_url = source_of_record(contract)
    if source_url:
        related.append(
            {
                "relatedIdentifier": source_url,
                "relatedIdentifierType": "URL",
                "relationType": "IsDerivedFrom",
            }
        )
    related.append(
        {
            "relatedIdentifier": f"{RAW_BASE}/examples/dcat-us-catalog.example.data.json",
            "relatedIdentifierType": "URL",
            "relationType": "IsDescribedBy",
        }
    )

    record: dict = {
        "identifiers": [
            {"identifier": identifier, "identifierType": "URL"},
        ],
        "creators": creators,
        "titles": [{"title": collection.get("title", contract_id)}],
        "publisher": publisher_name,
        "publicationYear": issued[:4],
        "types": {
            "resourceType": "ODCS v3.1.0 data contract",
            "resourceTypeGeneral": "Dataset",
        },
        "subjects": [
            {"subject": str(t)} for t in catalog_keywords(contract.get("tags", []))
        ],
        "dates": dates,
        "language": "en",
        "formats": ["YAML"],
        "version": str(contract_version),
        "rightsList": [
            {
                "rights": "CC0 1.0 Universal",
                "rightsUri": LICENSE_IRI["CC0-1.0"],
                "rightsIdentifier": "CC0-1.0",
                "rightsIdentifierScheme": "SPDX",
                "schemeUri": "https://spdx.org/licenses/",
            }
        ],
        "descriptions": [
            {"description": text(contract.get("description")), "descriptionType": "Abstract"}
        ],
        "geoLocations": geo_locations(collection),
        "relatedIdentifiers": related,
    }

    # place the funder list only where the contract carries funding facts
    funding = build_funding_references(contract)
    if funding:
        record["fundingReferences"] = funding

    return {**record, "schemaVersion": CDC_SCHEMA_VERSION}


def geo_locations(collection: dict) -> list[dict]:
    try:
        bbox = collection["extent"]["spatial"]["bbox"][0]
    except (KeyError, IndexError, TypeError):
        return []
    if bbox == [-180.0, -90.0, 180.0, 90.0]:
        return []
    west, south, east, north = (float(x) for x in bbox)
    return [
        {
            "geoLocationBox": {
                "westBoundLongitude": west,
                "eastBoundLongitude": east,
                "southBoundLatitude": south,
                "northBoundLatitude": north,
            }
        }
    ]


def build_funding_references(contract: dict) -> list[dict]:
    """Emit funding references only from real contract facts.

    Respect the customProperties block; nothing synthetic. On-chain
    evidence (wallets, transactions) does not belong here — issue #21
    records that it must travel in a separate artifact referenced via
    relatedIdentifiers.
    """
    funding: list[dict] = []
    for prop in contract.get("customProperties", []):
        name = prop.get("property", "")
        if name.startswith("fundingReference:"):
            funding.append(
                {
                    "funderName": str(prop.get("value", "")),
                }
            )
    return funding


def build(base: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict] = {}
    for entry in sorted(load_collections(), key=lambda e: e["collection"]["id"]):
        contract = yaml.safe_load(entry["contract_path"].read_text())
        contract_id = entry["collection"].get(
            "geocontract:contract_id", contract.get("id", "")
        )
        if contract_id in records:
            continue
        records[contract_id] = build_record(entry)

    # Clean out stale files so removed collections do not leave orphan records.
    for stale in OUT_DIR.glob("*.json"):
        if stale.stem not in records:
            stale.unlink()

    for contract_id, record in records.items():
        (OUT_DIR / f"{contract_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
    print(f"OK  built {len(records)} record(s) in {OUT_DIR.relative_to(ROOT)} (catalog: {base})")


def main() -> int:
    build(base_idiri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
