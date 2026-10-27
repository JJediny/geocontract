#!/usr/bin/env python3
"""Validate the generated activity ontology with the Open Ontologies CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geocontract_tools.build_ontology import CONCEPT_BASE  # noqa: E402

ONTOLOGY_DIR = ROOT / "ontology"
CATALOG_PATH = ONTOLOGY_DIR / "activity-concept-catalog.v1.0.json"
TURTLE_PATH = CATALOG_PATH.with_suffix(".ttl")
SHAPES_PATH = ONTOLOGY_DIR / "activity-concept-catalog.shacl.ttl"
REPORT_PATH = ONTOLOGY_DIR / "open-ontologies-validation.json"
QUERY_DIR = ONTOLOGY_DIR / "queries"
DEFAULT_BINARY = ROOT / ".tools" / "open-ontologies" / "bin" / "open-ontologies"


def decode_term(value: str) -> Any:
    """Decode the literal at the start of the CLI's RDF term notation."""
    return json.JSONDecoder().raw_decode(value)[0]


def decode_node(value: str) -> Any:
    """Decode either an IRI or a literal from the CLI's result notation."""
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    return decode_term(value)


def descendants(catalog: dict[str, Any], root: str) -> set[str]:
    """Return all transitive narrower codes for one root concept."""
    found = {root}
    changed = True
    while changed:
        changed = False
        for concept in catalog["concepts"]:
            code = concept["code"]
            if code not in found and found.intersection(concept.get("broader", [])):
                found.add(code)
                changed = True
    return found - {root}


def replace_once(text: str, old: str, new: str) -> str:
    """Replace one required mutation target and reject missing or ambiguous targets."""
    if text.count(old) != 1:
        raise RuntimeError(f"mutation target must occur exactly once: {old!r}")
    return text.replace(old, new, 1)


def replace_in_concept(text: str, code: str, old: str, new: str) -> str:
    """Apply a mutation inside one concept block only."""
    marker = f"gca:{code} a gc:ActivityConcept, skos:Concept ;"
    start = text.index(marker)
    end = text.find("\n\n", start)
    if end == -1:
        end = len(text)
    block = text[start:end]
    return text[:start] + replace_once(block, old, new) + text[end:]


def shacl_mutations(turtle: str) -> dict[str, str]:
    """Return valid-RDF fixtures that must each produce a SHACL violation."""
    code_line = '    gc:activityCode "housing.rehabilitation.facade" ;'
    return {
        "missing-label": replace_once(turtle, '    skos:prefLabel "Building façade rehabilitation" ;\n', ""),
        "duplicate-code-property": replace_once(
            turtle,
            code_line,
            code_line + "\n" + '    gc:activityCode "duplicate.code" ;',
        ),
        "invalid-code": replace_once(turtle, code_line, '    gc:activityCode "INVALID CODE" ;'),
        "invalid-date-datatype": replace_in_concept(
            turtle,
            "civic.event",
            '    gc:lifecycleStatus "active" ;',
            '    gc:deprecatedAfter "2026-01-01" ;\n    gc:lifecycleStatus "active" ;',
        ),
        "invalid-concept-reference": replace_once(
            turtle,
            "    skos:broader gca:housing.rehabilitation ;",
            "    skos:broader gca:missing.parent ;",
        ),
        "invalid-source-iri": replace_once(
            turtle,
            "    dcterms:source <https://ce.permitting.innovation.gov/data/exclusions.json> ;",
            '    dcterms:source "not-an-iri" ;',
        ),
    }


def query_mutations(turtle: str) -> dict[str, tuple[str, str]]:
    """Return fixtures that must make the named ASK query return true."""
    integrity = "hierarchy-integrity.rq"
    return {
        "unresolved-broader": (
            integrity,
            replace_once(
                turtle,
                "    skos:broader gca:housing.rehabilitation ;",
                "    skos:broader gca:missing.parent ;",
            ),
        ),
        "unresolved-narrower": (
            integrity,
            replace_in_concept(
                turtle,
                "housing.rehabilitation",
                "gca:housing.rehabilitation.facade,",
                "gca:missing.child,",
            ),
        ),
        "missing-narrower-reciprocal": (
            integrity,
            replace_in_concept(turtle, "housing.rehabilitation", "gca:housing.rehabilitation.facade, ", ""),
        ),
        "missing-broader-reciprocal": (
            integrity,
            replace_once(turtle, "    skos:broader gca:housing.rehabilitation ;\n", ""),
        ),
        "non-active-broader": (
            integrity,
            replace_in_concept(
                turtle,
                "housing.rehabilitation",
                '    gc:lifecycleStatus "active" ;',
                '    gc:lifecycleStatus "retired" ;',
            ),
        ),
        "hierarchy-cycle": (
            integrity,
            replace_in_concept(
                turtle,
                "housing.rehabilitation",
                "    skos:topConceptOf gc:activity-concept-catalog .",
                "    skos:broader gca:housing.rehabilitation.facade ;\n"
                "    skos:topConceptOf gc:activity-concept-catalog .",
            ),
        ),
        "duplicate-code": (
            integrity,
            replace_in_concept(
                turtle,
                "civic.event",
                '    gc:activityCode "civic.event" ;',
                '    gc:activityCode "housing.rehabilitation.facade" ;',
            ),
        ),
        "non-descriptive-status": (
            "non-descriptive-status.rq",
            replace_in_concept(
                turtle,
                "civic.event",
                '    gc:regulatoryStatus "descriptive_only" ;',
                '    gc:regulatoryStatus "jurisdictional_advisory" ;',
            ),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        parser.error(f"Open Ontologies not found at {binary}; run 'mise run ontology-install'")

    # A failed run must not leave an earlier ok=true report looking current.
    REPORT_PATH.unlink(missing_ok=True)
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    turtle = TURTLE_PATH.read_text(encoding="utf-8")
    concepts = catalog["concepts"]
    query_expectations: dict[str, tuple[str, Any]] = {
        "active-concepts.rq": (
            "How many concepts have lifecycleStatus active?",
            sum(c["lifecycleStatus"] == "active" for c in concepts),
        ),
        "catalog-coverage.rq": (
            "Which concept IRIs and codes does the complete catalog contain?",
            {CONCEPT_BASE + c["code"]: c["code"] for c in concepts},
        ),
        "facade-by-alias.rq": (
            "Which concept has the alias 'facade repair'?",
            {c["code"] for c in concepts if "facade repair" in c.get("aliases", [])},
        ),
        "rehabilitation-descendants.rq": (
            "Which concepts are descendants of housing.rehabilitation?",
            descendants(catalog, "housing.rehabilitation"),
        ),
        "non-descriptive-status.rq": ("Does any concept claim a non-descriptive regulatory status?", False),
        "hierarchy-integrity.rq": ("Does the hierarchy contain an integrity violation?", False),
    }
    query_files = {path.name for path in QUERY_DIR.glob("*.rq")}
    if query_files != set(query_expectations):
        raise RuntimeError(
            f"query expectations do not match committed queries: files={sorted(query_files)}, "
            f"expectations={sorted(query_expectations)}"
        )

    env = os.environ.copy()
    env["OPEN_ONTOLOGIES_STORAGE_MODE"] = "persistent"
    report: dict[str, Any] = {
        "source": str(CATALOG_PATH.relative_to(ROOT)),
        "ontology": str(TURTLE_PATH.relative_to(ROOT)),
        "shapes": str(SHAPES_PATH.relative_to(ROOT)),
        "ok": False,
    }

    with tempfile.TemporaryDirectory(prefix="geocontract-ontology-") as state_dir:
        def run(
            *command: str,
            data_dir: str = state_dir,
            expect_failure: bool = False,
        ) -> dict[str, Any]:
            completed = subprocess.run(
                [str(binary), "--data-dir", data_dir, "--no-connect", *command],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if expect_failure and completed.returncode == 0:
                raise RuntimeError(f"open-ontologies {' '.join(command)} unexpectedly accepted a negative fixture")
            if not expect_failure and completed.returncode != 0:
                raise RuntimeError(
                    f"open-ontologies {' '.join(command)} failed ({completed.returncode}):\n"
                    f"{completed.stdout}{completed.stderr}"
                )
            try:
                return json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"open-ontologies returned non-JSON output: {completed.stdout!r}") from exc

        status = run("status")
        report["tool"] = {"name": "open-ontologies", "version": status["version"]}
        ontology_arg = str(TURTLE_PATH.relative_to(ROOT))
        shapes_arg = str(SHAPES_PATH.relative_to(ROOT))
        report["validation"] = {
            "ontology": run("validate", ontology_arg),
            "shapes": run("validate", shapes_arg),
        }
        if not all(result["ok"] for result in report["validation"].values()):
            raise RuntimeError("RDF syntax validation failed")
        loaded = run("load", ontology_arg)
        stats = run("stats")
        lint = run("lint", ontology_arg)
        shacl = run("shacl", shapes_arg)
        if stats["triples"] != loaded["triples_loaded"]:
            raise RuntimeError("load and stats report different triple counts")
        if lint["issue_count"] != 0 or lint["suppressed_count"] != 0:
            raise RuntimeError(
                f"ontology lint found {lint['issue_count']} issues and {lint['suppressed_count']} suppressed issues"
            )
        if shacl["conforms"] is not True or shacl["violation_count"] != 0:
            raise RuntimeError("SHACL validation did not conform")
        if shacl["focus_nodes"] != len(concepts) or shacl["unmatched_shapes"]:
            raise RuntimeError("SHACL did not cover every concept with every shape")
        report["validation"].update({"load": loaded, "stats": stats, "lint": lint, "shacl": shacl})

        query_reports = []
        for filename in sorted(query_expectations):
            question, expected = query_expectations[filename]
            path = QUERY_DIR / filename
            result = run("query", path.read_text(encoding="utf-8"))
            if filename == "active-concepts.rq":
                passed = int(decode_term(result["results"][0]["count"])) == expected
            elif filename == "catalog-coverage.rq":
                actual = {decode_node(row["concept"]): decode_term(row["code"]) for row in result["results"]}
                passed = actual == expected and len(result["results"]) == len(concepts)
            elif filename in {"facade-by-alias.rq", "rehabilitation-descendants.rq"}:
                actual = {decode_term(row["code"]) for row in result["results"]}
                passed = actual == expected
            else:
                passed = result["result"] is expected
            query_reports.append(
                {"path": str(path.relative_to(ROOT)), "question": question, "passed": passed, "result": result}
            )
            if not passed:
                raise RuntimeError(f"competency query failed: {filename}; expected {expected!r}, got {result!r}")
        report["queries"] = query_reports

        negative_shacl_reports = []
        for name, mutated in sorted(shacl_mutations(turtle).items()):
            negative_state = str(Path(state_dir) / f"shacl-{name}")
            negative_path = Path(state_dir) / f"shacl-{name}.ttl"
            negative_path.write_text(mutated, encoding="utf-8")
            run("validate", str(negative_path), data_dir=negative_state)
            run("load", str(negative_path), data_dir=negative_state)
            result = run("shacl", shapes_arg, data_dir=negative_state, expect_failure=True)
            if result["conforms"] is not False or result["violation_count"] < 1:
                raise RuntimeError(f"negative SHACL fixture did not produce a violation: {name}")
            negative_shacl_reports.append(
                {"fixture": name, "conforms": result["conforms"], "violation_count": result["violation_count"]}
            )
        report["negative_shacl"] = negative_shacl_reports

        negative_query_reports = []
        for name, (filename, mutated) in sorted(query_mutations(turtle).items()):
            negative_state = str(Path(state_dir) / f"query-{name}")
            negative_path = Path(state_dir) / f"query-{name}.ttl"
            negative_path.write_text(mutated, encoding="utf-8")
            run("validate", str(negative_path), data_dir=negative_state)
            run("load", str(negative_path), data_dir=negative_state)
            result = run("query", (QUERY_DIR / filename).read_text(encoding="utf-8"), data_dir=negative_state)
            if result["result"] is not True:
                raise RuntimeError(f"negative query fixture was not detected: {name}")
            negative_query_reports.append({"fixture": name, "query": filename, "result": True})
        report["negative_queries"] = negative_query_reports

        snapshot = run("version", f"activity-v{catalog['version']}")
        if snapshot["triple_count"] != stats["triples"]:
            raise RuntimeError("snapshot and stats report different triple counts")
        report["snapshot"] = snapshot

    report["ok"] = True
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    temporary_report = REPORT_PATH.with_suffix(".json.tmp")
    temporary_report.write_text(serialized, encoding="utf-8")
    temporary_report.replace(REPORT_PATH)
    print(
        f"OK   Open Ontologies {report['tool']['version']}: {stats['triples']} triples, "
        f"{shacl['focus_nodes']} SHACL focus nodes, {lint['issue_count']} lint issues, "
        f"{len(query_reports)} competency checks, {len(negative_shacl_reports)} SHACL mutations, "
        f"{len(negative_query_reports)} query mutations"
    )
    print(f"OK   wrote {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
