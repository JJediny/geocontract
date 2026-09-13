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
    def load(cls, path: str | Path) -> "ActivityOntology":
        path = Path(path)
        with path.open(encoding="utf-8") as fh:
            catalog = json.load(fh)
        # Validate the catalog itself.
        schema_path = path.with_name("activity-concept-catalog.schema.json")
        with schema_path.open(encoding="utf-8") as fh:
            schema = json.load(fh)
        Draft202012Validator(schema).validate(catalog)
        # Cross-check that broader / narrower references resolve.
        for c in catalog["concepts"]:
            for ref in c.get("broader", []):
                if ref not in {x["code"] for x in catalog["concepts"]}:
                    raise OntologyError(
                        f"concept {c['code']!r} has unresolved broader {ref!r}"
                    )
            for ref in c.get("narrower", []):
                if ref not in {x["code"] for x in catalog["concepts"]}:
                    raise OntologyError(
                        f"concept {c['code']!r} has unresolved narrower {ref!r}"
                    )
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