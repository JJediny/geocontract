# geocontract

**ODCS v3.1.0 data contracts bridging the federal CATEX catalogue and
the PIC NEPA Data Standard.**

> Sources:
> - [`https://ce.permitting.innovation.gov/data/exclusions.json`](https://ce.permitting.innovation.gov/data/exclusions.json) — federal Categorical Exclusion (CATEX) catalogue.
> - [`../pic-standards`](https://github.com/permits/pyper/tree/main/pic-standards) — Permitting Innovation Center NEPA Data & Technology Standard v1.2.
>
> Canonical schemas:
> - [datacontract.com](https://datacontract.com/) — the data-contract standard's homepage and docs.
> - [ODCS v3.1.0 JSON Schema](https://github.com/bitol-io/open-data-contract-standard/blob/main/schema/odcs-json-schema-v3.1.0.json) — the **canonical data source** for everything in this repo.
> - [`../json-schema-x-graphql`](https://github.com/json-schema-x-graphql/json-schema-x-graphql) — the upstream project (the `feature/phase5a-datacontracts-mermaid` branch ships the `DataContractShim` struct and YAML emitter that we extend here).

---

## What's in this repo

| Path                                                       | Purpose                                                                |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| `templates/*.template.schema.json`                         | json-schema-x-graphql annotated JSON Schemas (one per source).         |
| `examples/*.{schema,data,graphql}.json`                    | Filled-in working examples + SDL previews.                              |
| `maps/*.field-mapping.json`                                | `FieldMapping` consumed by `parse_field_mapping`.                       |
| `models/*.canonical.graphql`                               | Canonical subgraph SDL with `@mapFrom(path: …)` annotations.            |
| **`contracts/odcs-v3.1.0-template.yaml`**                  | **The primitive ODCS v3.1.0 template** (this PR's headline file).      |
| **`contracts/nepa-exclusions.datacontract.yaml`**          | **ODCS instance record for the CATEX catalogue.**                       |
| **`contracts/pic-standards.datacontract.yaml`**            | **ODCS instance record for the PIC NEPA Data Standard (13 entities).** |
| `contracts/shim/*.datacontract-shim.json`                  | Companion shims matching the Rust `DataContractShim` struct.          |
| `contracts/examples/odcs-v3.1.0-template.minimal.json`     | Minimal JSON example (ODCS-required fields only).                      |
| `src/geocontract_tools/validate_odcs.py`                  | Python validator (CLI + library).                                       |
| `src/geocontract_tools/harvester.py`                      | Federated-harvester design stub.                                        |
| `scripts/validate_odcs.py`                                 | Thin wrapper invoked by the `prek` hooks.                               |
| `scripts/vendor.sh`                                        | Vendors `jxql`, `datacontract`, and `dprint` into `.tools/`.            |
| `scripts/tests/`                                          | `pytest` test suite.                                                    |
| `mise.toml`                                                | Toolchain (uv, Python 3.13, Rust 1.85, datacontract-cli, dprint).       |
| `pyproject.toml`                                           | uv-managed Python project (deps, console scripts, ruff, pytest).       |
| `dprint.json`                                              | Formatter config (JSON + YAML + Markdown + TOML).                       |
| `prek.toml`                                                | Pre-commit / pre-push hook config.                                      |
| `docs/design-harvester.md`                                 | Future-planning design notes for the federated harvester.              |
| `external/exclusions.json`                                 | Snapshot of the federal CATEX catalogue (4 MB).                         |
| `external/odcs-json-schema-v3.1.0.json`                    | Pinned copy of the ODCS v3.1.0 canonical JSON Schema.                   |
| `external/datacontract-mod.rs`                             | Pinned copy of the json-schema-x-graphql `datacontract::mod` source.    |
| `external/datacontract-shim.rs`                            | Pinned copy of the json-schema-x-graphql `datacontract::shim` source.   |
| `external/datacontract-shim.example.json`                  | Reference shim from the upstream project.                               |
| `external/datacontract-sample-contract.json`               | Reference sample schema from the upstream project.                      |
| `external/datacontract-concepts.md`                        | Reference data-contract concepts report from the upstream project.      |

---

## Design use case

> Produce multiple `*.geocontract.yaml` that can reside anywhere; build
> a federated harvester that gathers, validates, and dumps records.

The end-state is that any agency can publish a `*.geocontract.yaml` in
their own repo or on their own server, and `geocontract-harvest` will
walk those sources, validate each one against the canonical ODCS
schema, normalise it into the canonical record view (`Exclusion`,
`Project`, `ProcessInstance`, …), and emit a unified JSONL stream for
downstream consumers (mesh-gateway, search index, dashboards).

See [`docs/design-harvester.md`](docs/design-harvester.md) for the full
design notes (phasing, open questions, output schema).

---

## Quick start

### One-time setup

```bash
mise trust             # accept mise.toml
mise install           # install python, rust, node, datacontract-cli, dprint
uv sync                # install Python deps
prek install           # install pre-commit + pre-push hooks
mise run vendor-jxql   # build jxql from ../json-schema-x-graphql into .tools/
```

### Validate everything

```bash
mise run validate-odcs    # validate every contract against the canonical schema
mise run fmt              # run dprint on JSON/YAML/Markdown/TOML
mise run fmt-check        # CI variant of fmt (no writes)
mise run test             # run pytest
mise run ci               # all three
```

### Validate a single contract

```bash
uv run geocontract-validate contracts/nepa-exclusions.datacontract.yaml
uv run geocontract-validate --shim contracts/shim/pic-standards.datacontract-shim.json
```

### Convert a JSON Schema into a data contract (when the upstream feature ships)

```bash
# Once json-schema-x-graphql/feature/phase5a-datacontracts-mermaid is
# vendored and built, the following emits a YAML data contract from
# any annotated JSON Schema:
.tools/bin/jxql \
    --input templates/nepa-exclusions.template.schema.json \
    --output /tmp/nepa-exclusions.datacontract.yaml \
    --output-format yaml \
    --shim contracts/shim/nepa-exclusions.datacontract-shim.json
```

---

## Toolchain summary

| Tool                   | Pinned in         | Used by                                  |
| ---------------------- | ----------------- | ---------------------------------------- |
| Python 3.13            | `mise.toml`       | uv, ruff, pytest                         |
| uv                     | (system PATH)     | Python project + deps                    |
| Rust 1.85              | `mise.toml`       | building `jxql` from source              |
| Node 22                | `mise.toml`       | pnpm                                     |
| pnpm                   | (system PATH)     | installing dprint                        |
| `pipx:datacontract-cli` 0.10.21 | `mise.toml`  | cross-validating YAML contracts          |
| `npm:dprint` 0.47.5    | `mise.toml`       | formatting JSON/YAML/Markdown/TOML       |
| `prek`                 | (system PATH)     | pre-commit hooks                         |
| `pyyaml`, `jsonschema` | `pyproject.toml`  | the validator                            |

---

## Why this is PR-ready

- All JSON files are syntactically valid (`check-json` passes).
- Every ODCS YAML contract validates against the canonical
  `external/odcs-json-schema-v3.1.0.json` schema via `Draft201909Validator`.
- Every shim JSON validates against the structural shape of the
  Rust `DataContractShim` struct (defined in
  `external/datacontract-shim.rs`).
- The validator has a `pytest` test suite with positive + negative tests.
- The harvester has a `pytest` test suite.
- `dprint.json` keeps the YAML/JSON/Markdown consistent across CI runs.
- `prek.toml` runs the validator, formatter, and linters on every commit.

---

## License

This contract metadata is dedicated to the public domain under [CC0 1.0](./LICENSE).

- The federal CATEX catalogue is a U.S. Government work and is in the public domain.
- The PIC NEPA Data Standard is published under the terms of the pic-standards repository.
- The ODCS v3.1.0 schema is licensed by the bitol-io project.
