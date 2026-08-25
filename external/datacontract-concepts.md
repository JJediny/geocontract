# Data Contract Concepts: JSON Schema vs Shim Configuration

> **Date:** 2026-07-26
> **Scope:** Analysis of which data contract concepts can be natively inferred from JSON Schema (with enhanced validations) vs which require a separate shim configuration YAML file.

---

## Executive Summary

A **data contract** defines the structure, semantics, quality expectations, and governance metadata for data assets. JSON Schema can express structural and validation constraints natively, but many operational, governance, and quality concepts require external metadata. This report categorizes 40+ data contract concepts into four tiers:

| Tier | Description | Count |
|------|-------------|-------|
| **Tier 1 — Native JSON Schema** | Concepts expressible directly in JSON Schema keywords | 14 |
| **Tier 2 — Enhanced `x-*` Extensions** | Concepts expressible via `x-graphql-*` or `x-*` custom properties within the schema | 8 |
| **Tier 3 — Shim Configuration** | Concepts requiring a separate YAML configuration file that references schema paths | 13 |
| **Tier 4 — External System** | Concepts requiring external systems (catalogs, lineage tools, IAM) | 5 |

---

## Tier 1: Native JSON Schema (14 concepts)

These concepts map directly to standard JSON Schema keywords (Draft 2020-12). No extensions or shim needed.

### Structural Concepts

| Concept | JSON Schema Keyword | Example |
|---------|-------------------|---------|
| **Entity/Type Definition** | `$defs`, root object | `{ "$defs": { "User": { ... } } }` |
| **Field Definitions** | `properties` | `{ "properties": { "name": { "type": "string" } } }` |
| **Field Types** | `type` | `"type": "string"` / `"integer"` / `"boolean"` / `"object"` / `"array"` |
| **Required Fields** | `required` | `"required": ["id", "name"]` |
| **Nested Objects** | `type: "object"` + `properties` | Object within properties |
| **Array Fields** | `type: "array"` + `items` | `{ "type": "array", "items": { "type": "string" } }` |
| **References/Composition** | `$ref`, `allOf`, `oneOf`, `anyOf` | `{ "$ref": "#/$defs/Address" }` |

### Validation Concepts

| Concept | JSON Schema Keyword | Example |
|---------|-------------------|---------|
| **String Length** | `minLength`, `maxLength` | `"minLength": 1, "maxLength": 255` |
| **String Pattern** | `pattern` | `"pattern": "^[A-Z]{2}\\d{4}$"` |
| **Numeric Range** | `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` | `"minimum": 0, "maximum": 100` |
| **Numeric Multiple** | `multipleOf` | `"multipleOf": 0.01` |
| **Array Size** | `minItems`, `maxItems` | `"minItems": 1, "maxItems": 10` |
| **Unique Items** | `uniqueItems` | `"uniqueItems": true` |
| **Enum Values** | `enum` | `"enum": ["ACTIVE", "INACTIVE", "PENDING"]` |

### Metadata Concepts

| Concept | JSON Schema Keyword | Example |
|---------|-------------------|---------|
| **Description** | `description` | `"description": "Unique user identifier"` |
| **Title** | `title` | `"title": "User Account"` |
| **Default Value** | `default` | `"default": "ACTIVE"` |
| **Examples** | `examples` | `"examples": ["US1234"]` |
| **Deprecation** | `deprecated` | `"deprecated": true` |
| **Format Hint** | `format` | `"format": "date-time"` / `"email"` / `"uuid"` / `"uri"` |
| **Schema Version** | `$schema` | `"$schema": "https://json-schema.org/draft/2020-12/schema"` |

---

## Tier 2: Enhanced `x-*` Extensions (8 concepts)

These concepts can be expressed within the JSON Schema document using `x-*` custom properties. The converter already supports `x-graphql-*` extensions; additional `x-dc-*` (data contract) extensions would fit naturally.

### Already Supported via `x-graphql-*`

| Concept | Extension | Example |
|---------|-----------|---------|
| **GraphQL Type Name** | `x-graphql-type-name` | `"x-graphql-type-name": "UserProfile"` |
| **GraphQL Field Name** | `x-graphql-field-name` | `"x-graphql-field-name": "createdAt"` |
| **GraphQL Type Override** | `x-graphql-type` | `"x-graphql-type": "ID!"` |
| **Custom Scalars** | `x-graphql-scalars` | `{ "DateTime": { "description": "..." } }` |
| **Federation Keys** | `x-graphql-federation-keys` | `[{ "fields": "id" }]` |
| **Skip Field/Type** | `x-graphql-skip` | `"x-graphql-skip": true` |
| **Directives** | `x-graphql-directives` | `[{ "name": "deprecated", "args": {...} }]` |

### Proposed `x-dc-*` Extensions (within JSON Schema)

| Concept | Proposed Extension | Example |
|---------|-------------------|---------|
| **Logical Type** | `x-dc-logical-type` | `"x-dc-logical-type": "currency_usd"` |
| **Business Name** | `x-dc-business-name` | `"x-dc-business-name": "Customer Identifier"` |
| **Classification** | `x-dc-classification` | `"x-dc-classification": "pii"` / `"internal"` / `"restricted"` |
| **Glossary Term** | `x-dc-glossary-term` | `"x-dc-glossary-term": "customer_id"` |
| **Sample Values** | `x-dc-samples` | `"x-dc-samples": ["US-1234", "EU-5678"]` |
| **Field Level Tags** | `x-dc-tags` | `"x-dc-tags": ["pci", "audit-log"]` |
| **Nullable Indicator** | `x-dc-nullable` | `"x-dc-nullable": true` (explicit, even when not in `required`) |
| **Deprecation Reason** | `x-dc-deprecation-reason` | `"x-dc-deprecation-reason": "Migrated to v2 API"` |

---

## Tier 3: Shim Configuration (13 concepts)

These concepts are cross-cutting, operational, or governance-related. They reference schema entities but cannot be cleanly expressed within the schema itself. The **shim configuration YAML** bridges this gap.

### Shim YAML Schema

```yaml
# datacontract-shim.yaml
# Maps JSON Schema entities to data contract metadata

version: "1.0"
schema:
  $schema: "https://json-schema.org/draft/2020-12/schema"
  # Optional: path to the JSON Schema file this shim references
  source: "./user-service.json"

contract:
  # Contract-level metadata
  name: "User Service Contract"
  description: "Data contract for the User Service domain"
  version: "2.1.0"
  status: active          # active | deprecated | sunset
  domain: identity        # business domain

ownership:
  team: "platform-identity"
  contact: "identity-team@example.com"
  slack: "#identity-platform"
  oncall: "identity-oncall"
  docs_url: "https://wiki.example.com/identity"

quality:
  - metric: freshness
    field: "#/$defs/User/properties/updatedAt"
    threshold: "24h"
    description: "User records must be updated within 24 hours"
  - metric: completeness
    field: "#/$defs/User/properties/email"
    threshold: 0.95
    description: "95% of users must have email populated"
  - metric: uniqueness
    field: "#/$defs/User/properties/id"
    threshold: 1.0
    description: "User IDs must be unique"
  - metric: accuracy
    field: "#/$defs/User/properties/email"
    threshold: 0.99
    rule: "pattern: ^[^@]+@[^@]+\\.[^@]+$"
    description: "Email format validation accuracy"

sla:
  - name: "read-latency"
    target: "p95 < 100ms"
    window: "rolling-7d"
  - name: "availability"
    target: "99.95%"
    window: "monthly"

lineage:
  upstream:
    - source: "event://identity.user.created"
      type: kafka
      topic: "identity.events"
      format: avro
  downstream:
    - consumer: "notification-service"
      type: api
      endpoint: "graphql://notification/internal"
    - consumer: "analytics-pipeline"
      type: kafka
      topic: "analytics.users.cdc"
      format: avro

retention:
  policy: "GDPR-7y"
  description: "Retain 7 years per GDPR, then anonymize"
  delete_after: "7y"
  archive_after: "2y"
  partition_strategy: "date(createdAt)"

access:
  classification: restricted     # public | internal | confidential | restricted
  pii_fields:
    - "#/$defs/User/properties/email"
    - "#/$defs/User/properties/phone"
  compliance:
    - regulation: GDPR
      justification: "Contains EU citizen PII"
    - regulation: SOC2
      justification: "Part of audited platform"

lifecycle:
  created: "2024-01-15"
  last_modified: "2026-06-01"
  sunset_date: null
  changelog:
    - version: "2.1.0"
      date: "2026-06-01"
      summary: "Added phone field, updated retention policy"
    - version: "2.0.0"
      date: "2025-03-15"
      summary: "Major refactor for Federation v2"

partitioning:
  strategy: time
  column: "createdAt"
  granularity: day
  retention_days: 730

cost:
  center: "platform-1234"
  budget_code: "PLATFORM-CORE"
  estimated_annual_cost_usd: 15000

tags:
  - "pci-dss"
  - "customer-data"
  - "tier-1"

# Cross-entity overrides: per-field or per-type metadata that augments JSON Schema
entities:
  "$defs/User":
    classification: restricted
    pii: true
    lifecycle:
      sunset_date: null
    quality:
      - metric: freshness
        field: "properties/updatedAt"
        threshold: "24h"

  "$defs/User/properties/email":
    classification: pii
    masking: "sha256-hash"
    quality:
      - metric: completeness
        threshold: 0.99

  "$defs/User/properties/ssn":
    classification: restricted
    masking: "last4"
    retention: "delete-after-ingest"
```

### Concept Mapping — Shim Required

| # | Concept | Shim Key | Why Not JSON Schema |
|---|---------|----------|---------------------|
| 1 | **Ownership** | `ownership` | Team/contact/slack are operational metadata, not structural |
| 2 | **Quality SLOs** | `quality` | Freshness/completeness thresholds reference fields but aren't schema constraints |
| 3 | **SLA Definitions** | `sla` | Latency/availability targets are runtime guarantees, not structural |
| 4 | **Lineage** | `lineage` | Upstream/downstream dependencies span systems, not schemas |
| 5 | **Retention Policy** | `retention` | Business policy, not structural constraint |
| 6 | **Access Classification** | `access` | PII classification and compliance are governance metadata |
| 7 | **Lifecycle/Dates** | `lifecycle` | Created/modified/sunset are operational timestamps |
| 8 | **Partitioning** | `partitioning` | Storage strategy, not schema structure |
| 9 | **Cost Metadata** | `cost` | Budget/financial metadata |
| 10 | **Tags** | `tags` | Free-form organizational tags |
| 11 | **Compliance** | `access.compliance` | Regulatory requirements reference external regulations |
| 12 | **Data Masking** | `entities.*.masking` | Per-field security policy, not a schema constraint |
| 13 | **Changelog** | `lifecycle.changelog` | Historical record of changes |

---

## Tier 4: External Systems (5 concepts)

These concepts live in dedicated external tools. The shim can store references/pointers but not the authoritative data.

| Concept | External System | Shim Reference |
|---------|----------------|----------------|
| **Data Catalog** | DataHub, Amundsen, Collibra | `catalog.urn` |
| **Lineage Graph** | Marquez, OpenLineage | `lineage.job_id` |
| **IAM/Policy** | AWS IAM, OPA, Cerbos | `access.policy_arn` |
| **Monitoring** | Datadog, Prometheus | `sla.monitor_url` |
| **Schema Registry** | Confluent, Apicurio | `schema.registry_id` |

---

## Implementation Strategy

### Phase 5A: Mermaid .mmd Output + Data Contract YAML Shim

1. **Add `OutputFormat::Mermaid` and `OutputFormat::DataContractYaml`** to `types.rs`
2. **Create shim configuration YAML schema** with all Tier 3 concepts
3. **Implement Mermaid .mmd generator** — wraps existing `diagram::to_mermaid_er` through the converter pipeline
4. **Implement YAML data contract generator** — reads JSON Schema + optional shim, produces complete data contract YAML
5. **Add CLI support** for `--output-format mermaid` and `--output-format yaml`
6. **Node.js parity** — port the output format support to Node converter
7. **Add `x-dc-*` extension support** — recognize Tier 2 extensions in both converters

### Future Phases

| Phase | Scope |
|-------|-------|
| Phase 5B | Quality validation engine (run SLO checks against actual data) |
| Phase 5C | Lineage integration (OpenLineage/Marquez hooks) |
| Phase 5D | Catalog integration (DataHub/Amundsen API) |

---

## Appendix: Full Shim YAML Schema (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DataContractShim",
  "type": "object",
  "properties": {
    "version": { "type": "string", "default": "1.0" },
    "schema": {
      "type": "object",
      "properties": {
        "$schema": { "type": "string" },
        "source": { "type": "string", "description": "Path to the JSON Schema file" }
      }
    },
    "contract": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "description": { "type": "string" },
        "version": { "type": "string" },
        "status": { "enum": ["active", "deprecated", "sunset"] },
        "domain": { "type": "string" }
      },
      "required": ["name", "version"]
    },
    "ownership": {
      "type": "object",
      "properties": {
        "team": { "type": "string" },
        "contact": { "type": "string" },
        "slack": { "type": "string" },
        "oncall": { "type": "string" },
        "docs_url": { "type": "string", "format": "uri" }
      },
      "required": ["team"]
    },
    "quality": { "type": "array" },
    "sla": { "type": "array" },
    "lineage": {
      "type": "object",
      "properties": {
        "upstream": { "type": "array" },
        "downstream": { "type": "array" }
      }
    },
    "retention": { "type": "object" },
    "access": { "type": "object" },
    "lifecycle": { "type": "object" },
    "partitioning": { "type": "object" },
    "cost": { "type": "object" },
    "tags": { "type": "array", "items": { "type": "string" } },
    "entities": { "type": "object" }
  },
  "required": ["contract"]
}
```
