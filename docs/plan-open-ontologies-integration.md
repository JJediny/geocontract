# Open Ontologies integration review and acceptance plan

> **Status:** Core integration implemented and validated on 2026-10-26.
> Production change governance, dereferenceable publication, and proposal-level RDF remain separate increments.

## Interpreted end goal

Geocontract needs one governed activity vocabulary for citizen proposals. People and agents must be able to inspect the same concepts, hierarchy, aliases, provenance, and lifecycle state. A proposal must reference only an active concept. The vocabulary must describe activities without implying approval, exemption, or endorsement.

Open Ontologies supplies the validation and query engine. It does not replace the canonical proposal model, the ODCS projection, or the existing Python membership validator. The JSON catalog remains the source of truth. RDF is a deterministic projection of that catalog.

The intended result is a local, reproducible semantic validation path. A municipal deployment, an RDF endpoint, NLP enrichment, and regulatory reasoning are outside this increment.

## Implementation review

| Area | Review finding | Resolution | State |
| --- | --- | --- | --- |
| Source of truth | JSON and Turtle could diverge if both were curated. | Generate Turtle from JSON and test byte equality. | Implemented |
| Proposal validation | Existing code membership checks already serve the proposal pipeline. | Retain `ActivityOntology.validate_code`; do not replace it with SPARQL. | Implemented |
| Semantic model | The catalog is a concept taxonomy, not a class hierarchy of activities. | Use SKOS concepts and `skos:broader`/`skos:narrower`. | Implemented |
| Duplicate codes | Dictionary construction previously hid duplicate rows. | Reject duplicate codes during catalog load. | Implemented |
| Hierarchy integrity | References could be asymmetric, cyclic, or rooted in retired concepts. | Reject these cases in Python and SPARQL. | Implemented |
| Field constraints | JSON Schema did not provide RDF constraints. | Add SHACL cardinality, datatype, class, scheme, pattern, and enum checks, plus negative fixtures. | Implemented |
| Date validation | JSON Schema date formats were not checked at load time. | Enable the JSON Schema format checker. | Implemented |
| Source citations | A free-form string could become malformed or injected Turtle. | Require an absolute URI and reject forbidden IRI characters. | Implemented |
| Domain usefulness | Syntax validation alone cannot answer domain questions. | Add executable coverage, alias, hierarchy, active-count, and integrity queries. | Implemented |
| Regulatory boundary | A source citation could be mistaken for an approval decision. | Keep provenance separate from `regulatoryStatus`; test the descriptive-only baseline. | Implemented |
| Tool setup | The source build stalled in native RocksDB compilation. | Install the documented, pinned release binary; configure MCP separately. | Implemented |
| Evidence | A successful command alone would not preserve semantic results. | Write a deterministic JSON validation report. | Implemented |
| Change governance | A snapshot is not a production review workflow. | Defer plan/apply/drift enforcement to a version-change increment. | Open |
| Publication | The stable IRIs are identifiers, not verified dereferenceable URLs. | Defer publication claims until HTTP behavior is tested. | Open |
| Proposal RDF | The activity ontology is validated, but proposals are not projected into RDF. | Treat this as optional future interoperability, not a hidden dependency. | Open |

## Artifacts and responsibilities

| Artifact | Role | Maintenance |
| --- | --- | --- |
| `ontology/activity-concept-catalog.v1.0.json` | Curated concepts and catalog metadata | Edit by hand |
| `src/geocontract_tools/validate_ontology.py` | JSON Schema, graph, membership, lifecycle, and date checks | Edit with tests |
| `src/geocontract_tools/build_ontology.py` | Deterministic JSON-to-SKOS projection | Edit with generator tests |
| `ontology/activity-concept-catalog.v1.0.ttl` | RDF/OWL and SKOS artifact | Generate only |
| `ontology/activity-concept-catalog.shacl.ttl` | Closed constraints for projected concepts | Curate with validation tests |
| `ontology/queries/*.rq` | Competency and graph-integrity checks | Curate with expected results |
| `scripts/check_ontology.py` | Open Ontologies validate/load/stats/lint/SHACL/query/version workflow | Edit with the CLI contract |
| `ontology/open-ontologies-validation.json` | Machine-readable evidence | Generate only |
| `.mcp.json` | Local MCP server connection | Run `mise run ontology-install` first |
| `mise.toml` | Version pin and reproducible tasks | Update the pin deliberately |

The generated report records Open Ontologies 2.1.0, 248 loaded triples, 17 conforming SHACL focus nodes, zero lint issues, six passing queries, six rejected SHACL mutations, eight detected query mutations, and the `activity-v1.0.0` snapshot. These counts describe the reviewed catalog. The checks derive expected concept counts, coverage, and descendants from the JSON source instead of fixing them in the queries.

The active-concepts query counts lifecycle-active concepts. It does not decide proposal eligibility. `ActivityOntology.validate_code` remains the proposal gate and also applies the effective `deprecatedAfter` date.

## Current acceptance criteria

The integration is acceptable only while every criterion below passes.

### AC-01: One source of truth

- Edit only the JSON catalog for concept content.
- `mise run ontology-build` must regenerate the Turtle without unrelated changes.
- `uv run python scripts/build_ontology.py --check` must fail when the Turtle is absent or stale.
- Two builds from identical input must produce identical bytes.

### AC-02: Complete and stable projection

- Every JSON concept must produce exactly one `gc:ActivityConcept` and one `skos:Concept` at its stable code-based IRI.
- Labels, definitions, aliases, hierarchy, jurisdiction, source, lifecycle, deprecation, and regulatory fields must survive projection.
- Concept IRIs must not contain the catalog version.
- `test_every_catalog_row_has_an_rdf_projection` and `test_committed_turtle_matches_catalog` must pass.

### AC-03: RDF syntax, loading, and lint

- Open Ontologies must accept both the ontology and shapes as valid Turtle.
- The loaded triple count must equal the stats triple count.
- Ontology lint must report zero issues and zero suppressed issues.
- The check must save a snapshot named `activity-v<catalog version>` with the same triple count.

### AC-04: SHACL conformance

- Every projected concept must be a SHACL focus node, and the focus-node count must equal the JSON concept count.
- Required code, label, definition, scheme, lifecycle, and regulatory fields must have exactly one value.
- Codes must match the dotted-lowercase pattern.
- Dates, status enums, concept references, and source IRIs must have the declared types.
- The report must contain `conforms: true`, `violation_count: 0`, and no unmatched shapes.
- Each negative SHACL fixture must produce at least one violation: missing label, duplicate property, invalid code, invalid date datatype, invalid concept reference, and invalid source node kind.

### AC-05: Source-graph integrity

Catalog load must reject all of these cases:

- a duplicate code;
- an unresolved broader or narrower reference;
- a missing reciprocal broader or narrower reference;
- a broader concept whose lifecycle is not active;
- a hierarchy cycle;
- a malformed `deprecatedAfter` date;
- a single-segment activity code;
- a relative source citation.

The proposal validator must continue to reject unknown, inactive, and effectively deprecated codes. It must accept a concept on the day before `deprecatedAfter` and reject it from that date onward.

### AC-06: Competency questions

All committed query files must be discovered and run. A file without an expectation, or an expectation without a file, must fail the check. Each result must derive from the JSON source:

- the lifecycle-active concept count equals the number of active JSON rows;
- the coverage query returns every expected concept IRI and code, with one row per concept;
- `facade repair` resolves to `housing.rehabilitation.facade`;
- `housing.rehabilitation` returns all and only its transitive descendants;
- the hierarchy-integrity and non-descriptive-status `ASK` queries return `false`.

Mutation checks must prove the hierarchy query detects unresolved references in both directions, missing reciprocal links, a non-active parent, a cycle, and a duplicate code. A mutation must also prove the non-descriptive-status query detects a jurisdictional advisory row.

### AC-07: No regulatory inference

- Every concept in the reviewed v1.0 baseline must retain `regulatoryStatus: descriptive_only`.
- The non-descriptive-status `ASK` query must return `false` for this baseline.
- Source citations must remain `dcterms:source` provenance, not approval predicates.
- No rule may infer approval, exemption, endorsement, or a municipal decision from concept membership.

A later jurisdictional-advisory concept requires a reviewed query and documentation change. It must not be forced into the v1.0 assertion.

### AC-08: Reproducible setup and MCP connection

- `mise run ontology-install` must install the version pinned by `OPEN_ONTOLOGIES_VERSION`.
- The download must match the release `SHASUMS.txt` entry and report the exact pinned version.
- The installer must be idempotent and must reject a missing version pin.
- `.mcp.json` must launch that binary with `serve`.
- Core validation must need no credentials and no remote ontology service.
- Network access is limited to the initial release-binary download unless a user explicitly requests another operation.

### AC-09: Regression gates

- `mise run ontology-check` must run generation, installation, validation, loading, stats, lint, SHACL, queries, negative fixtures, and snapshotting.
- A failed check must remove any prior `ok: true` report before it starts and must replace the report atomically on success.
- `mise run test` must cover the generator, invalid source-graph fixtures, deprecation boundaries, and IRI injection.
- `mise run ci` must include the ontology check and all pre-existing validation gates.
- CI must fail when `ontology/` is dirty after the full suite, which rejects stale generated evidence.

## Verification evidence

Reviewed input: `ontology/activity-concept-catalog.v1.0.json`, 17 concepts.

```console
$ uv run python scripts/build_ontology.py --check
OK   ontology/activity-concept-catalog.v1.0.ttl matches ontology/activity-concept-catalog.v1.0.json

$ uv run python scripts/check_ontology.py
OK   Open Ontologies 2.1.0: 248 triples, 17 SHACL focus nodes, 0 lint issues, 6 competency checks, 6 SHACL mutations, 8 query mutations
OK   wrote ontology/open-ontologies-validation.json
```

The full machine-readable output is in `ontology/open-ontologies-validation.json`.

## Next increments and their acceptance criteria

These items are not required for the current local ontology integration. Each needs its own review before implementation.

### Govern a version change

**Objective:** Use the Open Ontologies lifecycle without treating a local snapshot as production approval.

**Acceptance criteria:**

1. A named pre-change snapshot exists before the proposed graph is loaded.
2. `plan` records added and removed terms, blast radius, risk, and conservativity results.
3. Every removed or renamed concept IRI has an explicit human-reviewed migration decision.
4. Protected concept IRIs cannot be removed by `apply`.
5. The post-change graph passes every current acceptance criterion.
6. `drift` and `lineage` outputs are attached to the change review.
7. A rollback drill restores the prior graph and passes the same queries.
8. A human approves the plan before any shared or published graph changes.

### Publish dereferenceable semantic assets

**Objective:** Make the stable identifiers useful outside the git checkout.

**Acceptance criteria:**

1. Each published ontology and concept IRI returns the documented HTTPS response.
2. Turtle content matches the generated artifact byte for byte, or a documented content-negotiation rule applies.
3. No private proposal field enters a public RDF document.
4. Catalog links live in the catalog manifest, while concept semantics stay in the ontology source.
5. An external client can load the published ontology and run all six queries with identical results.
6. Publication documentation states the version, persistence policy, and replacement policy.

### Add proposal-level RDF interoperability

**Objective:** Exchange proposals as RDF without changing the canonical nested JSON model.

**Acceptance criteria:**

1. An explicit mapping defines every projected proposal field and every omission.
2. Round-trip tests preserve all fields claimed by the mapping.
3. A known active activity code conforms; an unknown or inactive code produces a SHACL violation.
4. Public RDF omits every restricted field, with tests that inspect triples rather than only keys.
5. RDF validation never infers municipal approval from concept membership, provenance, signatures, or anchors.
6. JSON remains canonical unless a separately reviewed governance decision changes that rule.

## Definition of done for the current increment

The current increment is done when AC-01 through AC-09 pass in a clean checkout, the generated artifacts are committed, and the full pre-existing suite remains green. Future increments must not weaken the regulatory boundary or create a second curated source of concept content.
