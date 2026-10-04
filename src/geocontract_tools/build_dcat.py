#!/usr/bin/env python3
"""Build the DCAT-US catalog instance from the generated Portolan tree (plan §11 item 2).

Replaces the curated `examples/dcat-us-catalog.example.data.json` workflow.
Examples drift when the catalog changes; a generated file cannot. The
generator walks `catalog/**/collection.json`, reads the ODCS contract next
to each collection, and renders one DCAT-US `dcat:Catalog` with a
`dcat:Dataset` and `dcat:CatalogRecord` per unique contract.

Output order and content are deterministic: collections sort by id, keys
have a fixed order, and every timestamp comes from a generated collection
rather than from the clock. Re-running the generator on an unchanged tree
is a no-op byte for byte; CI's build-then-diff step proves it.

Rules the repo already fixes elsewhere:
- Contracts carry semantics; this file is derived. Never hand-edit the
  output — change the contract or the manifest and rebuild.
- Catalog facts (host provider, license) live in the manifest; this
  generator reads what the catalog generator already rendered rather than
  re-reading the manifest.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "catalog"
OUT_PATH = ROOT / "examples" / "dcat-us-catalog.example.data.json"

# License codes as the manifest records them → DCAT-US license IRIs.
LICENSE_IRI = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
}

# dcatUsCatalogId custom property on the dcat-us-catalog contract
# (ODCS set the semantics; DCAT renders them).
FALLBACK_CATALOG_ID = "https://geocontract.dev/catalogs/us-federal-geocontract"


def text(value: object) -> str:
    """Flatten a description (possibly an ODCS dict) to readable prose."""
    if isinstance(value, dict):
        parts = [v for k in ("purpose", "usage", "limitations") if (v := value.get(k))]
        value = " ".join(parts)
    return re.sub(r"\s+", " ", str(value or "").strip())


def base_idiri() -> str:
    contract_path = (
        CATALOG_DIR / "mirror" / "geocontract-dcat-us-catalog"
        / "geocontract-dcat-us-catalog.datacontract.yaml"
    )
    contract = yaml.safe_load(contract_path.read_text())
    for prop in contract.get("customProperties", []):
        if prop.get("property") == "dcatUsCatalogId":
            return str(prop["value"])
    return FALLBACK_CATALOG_ID


def load_collections() -> list[dict]:
    out: list[dict] = []
    for path in sorted(CATALOG_DIR.rglob("collection.json")):
        collection = json.loads(path.read_text())
        out.append(
            {
                "collection": collection,
                "contract_path": path.parent / next(
                    p.name for p in path.parent.iterdir() if p.name.endswith(".datacontract.yaml")
                ),
            }
        )
    return out


def issuer(contract: dict) -> str:
    issued = contract.get("contractCreatedTs")
    if isinstance(issued, list) and issued:
        issued = issued[0]
    return str(issued)[:10] if issued else ""


def build_dataset(base: str, entry: dict) -> dict:
    collection = entry["collection"]
    contract: dict = yaml.safe_load(entry["contract_path"].read_text())

    contract_id = collection.get("geocontract:contract_id", contract.get("id", ""))
    providers = collection.get("providers", [])
    producers = [p for p in providers if "producer" in p.get("roles", [])]
    hosts = [p for p in providers if "host" in p.get("roles", [])]
    publisher = producers[0] if producers else hosts[0]
    host = hosts[0] if hosts else publishers_fallback(collection)
    issued = issuer(contract) or collection["updated"][:10]
    modified = collections_updated(collection)
    description = text(contract.get("description")) or text(
        contract.get("description", {}).get("purpose")
        if isinstance(contract.get("description"), dict)
        else ""
    )

    domain = collection.get("geocontract:domain", "")
    primary_entity = collection.get("geocontract:primary_entity")
    dataset_url = f"{base}/datasets/{contract_id.replace('geocontract-', '') or contract_id}"

    dataset: dict = {
        "@id": dataset_url,
        "@type": "Dataset",
        "title": collection.get("title"),
        "description": description,
        "identifier": contract_id,
        "issued": issued,
        "modified": modified,
        "publisher": {"@type": "Agent", "name": publisher["name"]},
        "contactPoint": {
            "@type": "Kind",
            "fn": publisher.get("name", contract_id),
            "hasEmail": f"mailto:{host.get('email', 'permits@innovation.gov')}",
        },
        "keyword": catalog_keywords(contract.get("tags", [])),
        "license": LICENSE_IRI.get(
            collection.get("license", "CC0-1.0"), LICENSE_IRI["CC0-1.0"]
        ),
        "language": ["en"],
        "conformsTo": [
            {
                "@type": "Standard",
                "title": "ODCS v3.1.0",
                "version": "3.1.0",
            }
        ],
        "isPartOf": {"@id": base},
        "distribution": distributions(base, collection, contract),
    }
    if primary_entity:
        theme_word = text(primary_entity) or "Data"
        dataset["theme"] = [{"@type": "Concept", "prefLabel": theme_word.title()}]
    if domain:
        dataset["subject"] = [{"@type": "Concept", "prefLabel": text(domain).title()}]
    return dataset


def publishers_fallback(collection: dict) -> dict:
    return next(iter(collection.get("providers", [])), {"email": "permits@innovation.gov"})


def catalog_keywords(tags: list[object]) -> list[str]:
    return sorted({str(t) for t in tags if t not in ("geocontract",)})


def collections_updated(collection: dict) -> str:
    return str(collection.get("updated", ""))[:10]


def distributions(base: str, collection: dict, contract: dict) -> list[dict]:
    path_repo = entry_repo_path(collection)
    contract_slug = path_repo.name
    raw = f"https://raw.githubusercontent.com/JJediny/geocontract/main/{path_repo}"
    dist: list[dict] = [
        {
            "@id": f"{base}/dist/{path_repo.stem}",
            "@type": "Distribution",
            "title": "ODCS v3.1.0 contract (YAML)",
            "accessURL": f"https://github.com/JJediny/geocontract/blob/main/{path_repo}",
            "downloadURL": raw,
            "mediaType": "application/yaml",
            "format": "YAML",
        }
    ]
    source_url = source_of_record(contract)
    if source_url:
        dist.append(
            {
                "@id": f"{base}/dist/{contract_slug.split('.')[0]}.source",
                "@type": "Distribution",
                "title": "Upstream source (as published by the producer)",
                "accessURL": source_url,
                "downloadURL": source_url,
            }
        )
    return dist


def entry_repo_path(collection: dict) -> Path:
    """Repo-relative contract path for the collection's contract asset."""
    return Path("contracts") / (collection["id"].split("/", 1)[1] + ".datacontract.yaml")


def source_of_record(contract: dict) -> str | None:
    for ref in contract.get("authoritativeDefinitions", []):
        url = ref.get("url", "")
        if url.startswith("http"):
            return url
    return None


def build(base: str) -> None:
    entries = load_collections()
    records: list[dict] = []
    datasets: list[dict] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=lambda e: e["collection"]["id"]):
        contract_id = entry["collection"].get(
            "geocontract:contract_id", yaml.safe_load(entry["contract_path"].read_text()).get("id", "")
        )
        if contract_id in seen:
            continue
        seen.add(contract_id)
        dataset = build_dataset(base, entry)
        datasets.append(dataset)
        contract_version = entry["collection"].get(
            "geocontract:contract_version",
            yaml.safe_load(entry["contract_path"].read_text()).get("version", ""),
        )
        records.append(
            {
                "@id": f"{base}/records/{contract_id}-{contract_version}",
                "@type": "CatalogRecord",
                "title": f"Record for {dataset['title']} v{contract_version}",
                "description": [
                    f"Catalogued registration of the {contract_id} contract v{contract_version}."
                ],
                "issued": [dataset["issued"]],
                "modified": dataset["modified"],
                "primaryTopic": dataset["@id"],
            }
        )

    root = json.loads((CATALOG_DIR / "catalog.json").read_text())
    instance = build_catalog_instance(base, root, datasets, records)
    OUT_PATH.write_text(json.dumps(instance, indent=2, ensure_ascii=False) + "\n")


def build_catalog_instance(
    base: str, root: dict, datasets: list[dict], records: list[dict]
) -> dict:
    keywords = sorted({kw for d in datasets for kw in d.get("keyword", [])})
    now_date = max(d["modified"] for d in datasets)
    return {
        "@id": base,
        "@type": "Catalog",
        "title": root.get("title", "geocontract Data Contract Catalog"),
        "description": text(root.get("description")),
        "publisher": {
            "@type": "Agent",
            "name": "geocontract",
            "url": "https://github.com/JJediny/geocontract",
        },
        "creator": [
            {
                "@id": "https://github.com/JJediny",
                "@type": "Agent",
                "name": "geocontract",
            }
        ],
        "contactPoint": [
            {
                "@type": "Kind",
                "fn": "geocontract maintainers",
                "hasEmail": "mailto:permits@innovation.gov",
            }
        ],
        "keyword": keywords,
        "theme": catalog_themes(),
        "themeTaxonomy": [
            {
                "@id": "https://resources.data.gov/keywords",
                "@type": "ConceptScheme",
                "title": "data.gov Subject Taxonomy",
            }
        ],
        "subject": [
            {"@type": "Concept", "prefLabel": "National Environmental Policy Act"},
            {"@type": "Concept", "prefLabel": "Permitting"},
        ],
        "spatial": [{"@type": "Location", "prefLabel": "United States"}],
        "language": ["en"],
        "license": LICENSE_IRI["CC0-1.0"],
        "rights": [
            "The catalog metadata is dedicated to the public domain under CC0 1.0.",
            "Individual datasets inherit the license of their upstream publisher.",
        ],
        "accessRights": "Public access with no restrictions.",
        "issued": min(d["issued"] for d in datasets),
        "modified": now_date,
        "identifier": base,
        "homepage": {
            "@id": "https://github.com/JJediny/geocontract",
            "@type": "Document",
            "title": "geocontract — Project Homepage",
            "accessURL": "https://github.com/JJediny/geocontract",
        },
        "conformsTo": {
            "@id": "https://resources.data.gov/dcat-us/3.0.0",
            "@type": "Standard",
            "title": "DCAT-US 3.0",
            "description": "U.S. Government Data Catalog Vocabulary, version 3.0",
            "version": "3.0.0",
        },
        "qualifiedAttribution": [
            {
                "@type": "Attribution",
                "agent": {"@type": "Agent", "name": "geocontract"},
                "hadRole": "publisher",
            }
        ],
        "record": records,
        "dataset": datasets,
        "service": [
            {
                "@id": "https://geocontract.dev/services/harvester",
                "@type": "DataService",
                "id": "geocontract-harvester",
                "title": "geocontract Federated Harvester",
                "description": "Federated harvester that walks published ODCS data contracts, validates each against the canonical ODCS v3.1.0 schema, normalises them into a canonical record view, and emits a unified JSONL stream.",
                "endpointURL": [
                    "https://github.com/JJediny/geocontract/blob/main/src/geocontract_tools/harvester.py"
                ],
                "publisher": {"@type": "Agent", "name": "geocontract"},
                "contactPoint": [
                    {
                        "@type": "Kind",
                        "fn": "geocontract maintainers",
                        "hasEmail": "mailto:permits@innovation.gov",
                    }
                ],
            }
        ],
    }


def catalog_themes() -> list[dict]:
    return [
        {
            "@id": "https://resources.data.gov/subject/E3B98B73-F57A-4684-A16C-21F0F45DC5B8",
            "@type": "Concept",
            "prefLabel": "Environmental monitoring and forecasting",
        },
        {
            "@id": "https://resources.data.gov/subject/06F9D685-3D2E-4DD5-8C76-0F2C18A61C58",
            "@type": "Concept",
            "prefLabel": "Government operations and accountability",
        },
    ]


def main() -> int:
    base = base_idiri()
    build(base)
    print(f"OK  built {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
