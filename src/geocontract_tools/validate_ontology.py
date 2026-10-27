"""ActivityConcept catalog membership validator (plan §4.3).

Validates that a proposal's `activity.code` is an active row of the
hand-curated ontology catalog at
`ontology/activity-concept-catalog.v1.0.json`. The catalog itself
is JSON-validated against
`ontology/activity-concept-catalog.schema.json`.

Out-of-core: NLP / corpus ingestion (§13.3) is NOT performed here.
The catalog is hand-curated; this module only enforces membership.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class OntologyError(ValueError):
    """Raised when the catalog or a code is invalid."""


class ActivityOntology:
    """Read-only view of an ActivityConcept catalog."""

    def __init__(self, catalog: dict[str, Any]):
        self.version: str = catalog["version"]
        self._by_code: dict[str, dict[str, Any]] = {c["code"]: c for c in catalog["concepts"]}
        self._codes: set[str] = set(self._by_code)

    @classmethod
    def load(cls, path: str | Path) -> ActivityOntology:
        path = Path(path)
        with path.open(encoding="utf-8") as fh:
            catalog = json.load(fh)
        # Validate the catalog itself.
        schema_path = path.with_name("activity-concept-catalog.schema.json")
        with schema_path.open(encoding="utf-8") as fh:
            schema = json.load(fh)
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(catalog)
        concepts = catalog["concepts"]
        codes = [c["code"] for c in concepts]
        duplicates = sorted(code for code, count in Counter(codes).items() if count > 1)
        if duplicates:
            raise OntologyError(f"duplicate activity concept codes: {duplicates}")
        by_code = {c["code"]: c for c in concepts}

        # Keep both JSON hierarchy views complete and consistent. The RDF
        # projection exposes the same relations as skos:broader/narrower.
        for c in concepts:
            for ref in c.get("broader", []):
                if ref not in by_code:
                    raise OntologyError(f"concept {c['code']!r} has unresolved broader {ref!r}")
                if by_code[ref]["lifecycleStatus"] != "active":
                    raise OntologyError(f"concept {c['code']!r} has non-active broader {ref!r}")
                if c["code"] not in by_code[ref].get("narrower", []):
                    raise OntologyError(f"concept {c['code']!r} is missing from narrower on broader {ref!r}")
            for ref in c.get("narrower", []):
                if ref not in by_code:
                    raise OntologyError(f"concept {c['code']!r} has unresolved narrower {ref!r}")
                if c["code"] not in by_code[ref].get("broader", []):
                    raise OntologyError(f"concept {c['code']!r} is missing from broader on narrower {ref!r}")

        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(code: str) -> None:
            if code in visiting:
                raise OntologyError(f"activity concept hierarchy contains a cycle at {code!r}")
            if code in visited:
                return
            visiting.add(code)
            for parent in by_code[code].get("broader", []):
                visit(parent)
            visiting.remove(code)
            visited.add(code)

        for code in by_code:
            visit(code)
        return cls(catalog)

    @property
    def codes(self) -> set[str]:
        return set(self._codes)

    def validate_code(self, code: str, *, today: date | None = None) -> dict[str, Any]:
        """Validate that `code` is an active row of the catalog.

        Returns the row dict. Raises OntologyError otherwise.
        """
        if code not in self._by_code:
            raise OntologyError(f"activity.code {code!r} not found in ontology catalog")
        row = self._by_code[code]
        if row["lifecycleStatus"] != "active":
            raise OntologyError(
                f"activity.code {code!r} is {row['lifecycleStatus']!r}, "
                f"not active"
            )
        deprecated_after = row.get("deprecatedAfter")
        if deprecated_after:
            check = today or date.today()
            try:
                dep = datetime.strptime(deprecated_after, "%Y-%m-%d").date()
            except ValueError as exc:
                raise OntologyError(
                    f"activity.code {code!r}: malformed deprecatedAfter {deprecated_after!r}"
                ) from exc
            if check >= dep:
                raise OntologyError(
                    f"activity.code {code!r} was deprecated on {deprecated_after}"
                )
        return row
