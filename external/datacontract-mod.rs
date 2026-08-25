//! Data contract YAML generation from JSON Schema.
//!
//! Produces a YAML data contract document by combining structural
//! information from the JSON Schema with optional governance/operational
//! metadata from a shim configuration.

pub mod shim;

use crate::ddl;
use serde_json::Value as JsonValue;
use shim::DataContractShim;

// ── YAML generation helpers ──────────────────────────────────────

/// Escape a scalar value for YAML output.
///
/// Returns the unquoted string when possible, otherwise wraps in
/// double quotes with appropriate escaping.
fn yaml_scalar(value: &str) -> String {
    if value.is_empty() {
        return "\"\"".to_string();
    }

    // Characters that force quoting in YAML
    let needs_quotes = value.starts_with('{')
        || value.starts_with('[')
        || value.starts_with('&')
        || value.starts_with('*')
        || value.starts_with('!')
        || value.starts_with('|')
        || value.starts_with('>')
        || value.starts_with('%')
        || value.starts_with('@')
        || value.starts_with('`')
        || value.starts_with('#')
        || value.contains(": ")
        || value.contains(" #")
        || value.contains('\n')
        || value.contains('\t')
        || value == "true"
        || value == "false"
        || value == "null"
        || value == "yes"
        || value == "no"
        || value == "on"
        || value == "off"
        || value.ends_with(':');

    if needs_quotes {
        let escaped = value.replace('\\', "\\\\").replace('"', "\\\"");
        format!("\"{}\"", escaped)
    } else {
        value.to_string()
    }
}

/// Write a `key: value` line with indentation.
fn yaml_kv(key: &str, value: &str, _level: usize) -> String {
    format!("{}: {}", key, yaml_scalar(value))
}

/// Write the optional key-value pair (omitted when `opt_value` is None).
fn yaml_opt_kv(
    key: &str,
    opt_value: &Option<String>,
    level2: usize,
    out: &mut Vec<(usize, String)>,
) {
    if let Some(ref v) = opt_value {
        out.push((level2, yaml_kv(key, v, level2)));
    }
}

// ── Section generators ───────────────────────────────────────────

/// Generate the top-level contract metadata section.
fn write_contract_section(
    schema: &JsonValue,
    shim: Option<&DataContractShim>,
) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();

    if let Some(s) = shim {
        lines.push((0, format!("name: {}", yaml_scalar(&s.contract.name))));
        lines.push((0, format!("version: {}", yaml_scalar(&s.contract.version))));
        yaml_opt_kv("description", &s.contract.description, 0, &mut lines);
        yaml_opt_kv("status", &s.contract.status, 0, &mut lines);
        yaml_opt_kv("domain", &s.contract.domain, 0, &mut lines);
    } else {
        // Infer from schema
        if let Some(title) = schema.get("title").and_then(|v| v.as_str()) {
            lines.push((0, format!("name: {}", yaml_scalar(title))));
        } else {
            lines.push((0, format!("name: {}", yaml_scalar("Unnamed Contract"))));
        }
        lines.push((0, format!("version: {}", yaml_scalar("0.1.0"))));
        if let Some(desc) = schema.get("description").and_then(|v| v.as_str()) {
            lines.push((0, format!("description: {}", yaml_scalar(desc))));
        }
    }

    lines
}

/// Generate the schema section with types and fields.
fn write_schema_section(schema: &JsonValue) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();

    // Schema version
    if let Some(s) = schema.get("$schema").and_then(|v| v.as_str()) {
        lines.push((1, format!("$schema: {}", yaml_scalar(s))));
    }

    // Types from $defs or definitions
    let defs = schema
        .get("$defs")
        .or_else(|| schema.get("definitions"))
        .and_then(|d| d.as_object());

    if let Some(defs_obj) = defs {
        lines.push((1, "types:".to_string()));
        for (type_name, type_def) in defs_obj {
            lines.push((2, format!("{}:", yaml_scalar(type_name))));

            if let Some(desc) = type_def.get("description").and_then(|v| v.as_str()) {
                lines.push((3, format!("description: {}", yaml_scalar(desc))));
            }

            if let Some(props) = type_def.get("properties").and_then(|v| v.as_object()) {
                lines.push((3, "fields:".to_string()));
                let required: Vec<&str> = type_def
                    .get("required")
                    .and_then(|v| v.as_array())
                    .map(|a| a.iter().filter_map(|v| v.as_str()).collect())
                    .unwrap_or_default();

                for (field_name, field_def) in props {
                    let ftype = json_type_display(field_def);
                    let req = if required.contains(&field_name.as_str()) {
                        " (required)"
                    } else {
                        ""
                    };
                    let desc = field_def
                        .get("description")
                        .and_then(|v| v.as_str())
                        .map(|d| format!(" — {}", d))
                        .unwrap_or_default();
                    lines.push((
                        4,
                        format!(
                            "{}: {}{}{}",
                            yaml_scalar(field_name),
                            yaml_scalar(&ftype),
                            req,
                            yaml_scalar(&desc)
                        ),
                    ));

                    // Constraint details
                    write_field_constraints(field_def, 5, &mut lines);
                }
            }

            // x-dc-* extensions at type level
            if let Some(dc_exts) = type_def.as_object() {
                for (key, val) in dc_exts {
                    if key.starts_with("x-dc-") && key != "x-dc-type-name" {
                        let label = key.strip_prefix("x-dc-").unwrap();
                        if let Some(s) = val.as_str() {
                            lines.push((3, format!("{}: {}", yaml_scalar(label), yaml_scalar(s))));
                        }
                    }
                }
            }
        }
    }

    lines
}

/// Write constraint details for a single field.
fn write_field_constraints(
    field_def: &JsonValue,
    indent_level: usize,
    lines: &mut Vec<(usize, String)>,
) {
    let mut constraints: Vec<String> = Vec::new();

    if let Some(v) = field_def.get("minLength").and_then(|n| n.as_u64()) {
        constraints.push(format!("minLength: {}", v));
    }
    if let Some(v) = field_def.get("maxLength").and_then(|n| n.as_u64()) {
        constraints.push(format!("maxLength: {}", v));
    }
    if let Some(v) = field_def.get("pattern").and_then(|n| n.as_str()) {
        constraints.push(format!("pattern: {}", yaml_scalar(v)));
    }
    if let Some(v) = field_def.get("minimum").and_then(|n| n.as_f64()) {
        constraints.push(format!("minimum: {}", v));
    }
    if let Some(v) = field_def.get("maximum").and_then(|n| n.as_f64()) {
        constraints.push(format!("maximum: {}", v));
    }
    if let Some(v) = field_def.get("minItems").and_then(|n| n.as_u64()) {
        constraints.push(format!("minItems: {}", v));
    }
    if let Some(v) = field_def.get("maxItems").and_then(|n| n.as_u64()) {
        constraints.push(format!("maxItems: {}", v));
    }
    if field_def.get("uniqueItems").and_then(|v| v.as_bool()) == Some(true) {
        constraints.push("uniqueItems: true".to_string());
    }
    if let Some(enums) = field_def.get("enum").and_then(|v| v.as_array()) {
        let vals: Vec<String> = enums
            .iter()
            .filter_map(|v| v.as_str().map(yaml_scalar))
            .collect();
        if !vals.is_empty() {
            constraints.push(format!("enum: [{}]", vals.join(", ")));
        }
    }
    if let Some(v) = field_def.get("format").and_then(|v| v.as_str()) {
        constraints.push(format!("format: {}", yaml_scalar(v)));
    }
    if let Some(v) = field_def.get("default") {
        constraints.push(format!("default: {}", yaml_scalar(&value_to_str(v))));
    }
    if field_def.get("deprecated").and_then(|v| v.as_bool()) == Some(true) {
        constraints.push("deprecated: true".to_string());
    }

    if !constraints.is_empty() {
        for c in constraints {
            lines.push((indent_level, format!("- {}", c)));
        }
    }
}

/// Get a human-readable type string from a JSON Schema field definition.
fn json_type_display(field_def: &JsonValue) -> String {
    let jtype = field_def.get("type").and_then(|v| v.as_str());

    match jtype {
        Some("array") => {
            if let Some(items) = field_def.get("items") {
                let item_type = items.get("type").and_then(|v| v.as_str());
                if let Some(ref_name) = items.get("$ref").and_then(|v| v.as_str()) {
                    // Extract basename from $ref
                    let basename = ref_name.rsplit('/').next().unwrap_or(ref_name);
                    format!("array<{}>", basename)
                } else if let Some(it) = item_type {
                    format!("array<{}>", it)
                } else {
                    "array".to_string()
                }
            } else {
                "array".to_string()
            }
        }
        Some("object") => {
            if field_def.get("properties").is_some() {
                "object (inline)".to_string()
            } else if let Some(ref_name) = field_def.get("$ref").and_then(|v| v.as_str()) {
                let basename = ref_name.rsplit('/').next().unwrap_or(ref_name);
                basename.to_string()
            } else {
                "object".to_string()
            }
        }
        Some(t) => t.to_string(),
        None => {
            if field_def.get("$ref").is_some() {
                let ref_name = field_def.get("$ref").and_then(|v| v.as_str()).unwrap();
                let basename = ref_name.rsplit('/').next().unwrap_or(ref_name);
                basename.to_string()
            } else if field_def.get("oneOf").is_some() {
                "oneOf".to_string()
            } else if field_def.get("anyOf").is_some() {
                "anyOf".to_string()
            } else if field_def.get("allOf").is_some() {
                "allOf".to_string()
            } else {
                "unknown".to_string()
            }
        }
    }
}

/// Write the ownership section.
fn write_ownership_section(ownership: &shim::OwnershipMeta) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("team", &ownership.team, 1, &mut lines);
    yaml_opt_kv("contact", &ownership.contact, 1, &mut lines);
    yaml_opt_kv("slack", &ownership.slack, 1, &mut lines);
    yaml_opt_kv("oncall", &ownership.oncall, 1, &mut lines);
    yaml_opt_kv("docs_url", &ownership.docs_url, 1, &mut lines);
    lines
}

/// Write the quality checks section.
fn write_quality_section(checks: &[shim::QualityCheck]) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    for check in checks {
        lines.push((1, format!("- metric: {}", yaml_scalar(&check.metric))));
        if let Some(ref field) = check.field {
            lines.push((2, format!("field: {}", yaml_scalar(field))));
        }
        lines.push((
            2,
            format!(
                "threshold: {}",
                yaml_scalar(&value_to_str(&check.threshold))
            ),
        ));
        if let Some(ref desc) = check.description {
            lines.push((2, format!("description: {}", yaml_scalar(desc))));
        }
        if let Some(ref rule) = check.rule {
            lines.push((2, format!("rule: {}", yaml_scalar(rule))));
        }
    }
    lines
}

/// Write the SLA section.
fn write_sla_section(slas: &[shim::SlaDef]) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    for sla in slas {
        lines.push((1, format!("- name: {}", yaml_scalar(&sla.name))));
        lines.push((2, format!("target: {}", yaml_scalar(&sla.target))));
        if let Some(ref window) = sla.window {
            lines.push((2, format!("window: {}", yaml_scalar(window))));
        }
    }
    lines
}

/// Write the lineage section.
fn write_lineage_section(lineage: &shim::LineageMeta) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();

    if !lineage.upstream.is_empty() {
        lines.push((1, "upstream:".to_string()));
        for entry in &lineage.upstream {
            lines.push((2, "-".to_string()));
            write_lineage_entry(entry, 3, &mut lines);
        }
    }

    if !lineage.downstream.is_empty() {
        lines.push((1, "downstream:".to_string()));
        for entry in &lineage.downstream {
            lines.push((2, "-".to_string()));
            write_lineage_entry(entry, 3, &mut lines);
        }
    }

    lines
}

fn write_lineage_entry(entry: &shim::LineageEntry, level: usize, lines: &mut Vec<(usize, String)>) {
    if let Some(ref source) = entry.source {
        lines.push((level, format!("source: {}", yaml_scalar(source))));
    }
    if let Some(ref consumer) = entry.consumer {
        lines.push((level, format!("consumer: {}", yaml_scalar(consumer))));
    }
    yaml_opt_kv("type", &entry.entry_type, level, lines);
    yaml_opt_kv("topic", &entry.topic, level, lines);
    yaml_opt_kv("format", &entry.format, level, lines);
    yaml_opt_kv("endpoint", &entry.endpoint, level, lines);
}

/// Write the retention section.
fn write_retention_section(retention: &shim::RetentionPolicy) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("policy", &retention.policy, 1, &mut lines);
    yaml_opt_kv("description", &retention.description, 1, &mut lines);
    yaml_opt_kv("delete_after", &retention.delete_after, 1, &mut lines);
    yaml_opt_kv("archive_after", &retention.archive_after, 1, &mut lines);
    yaml_opt_kv(
        "partition_strategy",
        &retention.partition_strategy,
        1,
        &mut lines,
    );
    lines
}

/// Write the access control section.
fn write_access_section(access: &shim::AccessControl) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("classification", &access.classification, 1, &mut lines);

    if !access.pii_fields.is_empty() {
        lines.push((1, "pii_fields:".to_string()));
        for field in &access.pii_fields {
            lines.push((2, format!("- {}", yaml_scalar(field))));
        }
    }

    if !access.compliance.is_empty() {
        lines.push((1, "compliance:".to_string()));
        for entry in &access.compliance {
            lines.push((
                2,
                format!("- regulation: {}", yaml_scalar(&entry.regulation)),
            ));
            if let Some(ref just) = entry.justification {
                lines.push((3, format!("justification: {}", yaml_scalar(just))));
            }
        }
    }

    lines
}

/// Write the lifecycle section.
fn write_lifecycle_section(lifecycle: &shim::LifecycleMeta) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("created", &lifecycle.created, 1, &mut lines);
    yaml_opt_kv("last_modified", &lifecycle.last_modified, 1, &mut lines);
    yaml_opt_kv("sunset_date", &lifecycle.sunset_date, 1, &mut lines);

    if !lifecycle.changelog.is_empty() {
        lines.push((1, "changelog:".to_string()));
        for entry in &lifecycle.changelog {
            lines.push((2, format!("- version: {}", yaml_scalar(&entry.version))));
            lines.push((3, format!("date: {}", yaml_scalar(&entry.date))));
            if let Some(ref summary) = entry.summary {
                lines.push((3, format!("summary: {}", yaml_scalar(summary))));
            }
        }
    }

    lines
}

/// Write the partitioning section.
fn write_partitioning_section(part: &shim::PartitioningMeta) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("strategy", &part.strategy, 1, &mut lines);
    yaml_opt_kv("column", &part.column, 1, &mut lines);
    yaml_opt_kv("granularity", &part.granularity, 1, &mut lines);
    if let Some(days) = part.retention_days {
        lines.push((1, format!("retention_days: {}", days)));
    }
    lines
}

/// Write the cost section.
fn write_cost_section(cost: &shim::CostMeta) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    yaml_opt_kv("center", &cost.center, 1, &mut lines);
    yaml_opt_kv("budget_code", &cost.budget_code, 1, &mut lines);
    if let Some(amount) = cost.estimated_annual_cost_usd {
        lines.push((1, format!("estimated_annual_cost_usd: {}", amount)));
    }
    lines
}

/// Write the tags section.
fn write_tags_section(tags: &[String]) -> Vec<(usize, String)> {
    tags.iter()
        .map(|t| (1, format!("- {}", yaml_scalar(t))))
        .collect()
}

/// Write the relational DDL section, derived from the schema.
fn write_relational_section(schema: &JsonValue) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();

    // Pick the first $defs key as root_def, or "contract" as fallback
    let root_def = schema
        .get("$defs")
        .or_else(|| schema.get("definitions"))
        .and_then(|d| d.as_object())
        .and_then(|obj| obj.keys().next().map(|s| s.as_str()))
        .unwrap_or("contract");

    let relational = ddl::schema_to_relational(schema, root_def);

    if relational.tables.is_empty() {
        return lines;
    }

    lines.push((1, "tables:".to_string()));
    for table in &relational.tables {
        let pk = if table.columns.is_empty() {
            " (empty)".to_string()
        } else {
            String::new()
        };
        lines.push((2, format!("{}:{}", yaml_scalar(&table.name), pk)));
        for col in &table.columns {
            let mut flags = String::new();
            if !col.nullable {
                flags.push_str(" NOT NULL");
            }
            if let Some(ref pk_name) = table.primary_key {
                if col.name == *pk_name {
                    flags.push_str(" PK");
                }
            }
            lines.push((
                3,
                format!(
                    "- {}: {}{}",
                    yaml_scalar(&col.name),
                    yaml_scalar(&col.sql_type),
                    flags
                ),
            ));
        }
    }

    if !relational.relations.is_empty() {
        lines.push((1, "relations:".to_string()));
        for rel in &relational.relations {
            lines.push((2, format!("- parent: {}", yaml_scalar(&rel.parent_table))));
            lines.push((3, format!("child: {}", yaml_scalar(&rel.child_table))));
            lines.push((3, format!("fk_column: {}", yaml_scalar(&rel.fk_column))));
        }
    }

    // Add sample DDL
    let ddl_text = ddl::generate_ddl(&relational, false);
    if !ddl_text.is_empty() {
        lines.push((1, "sample_ddl: |".to_string()));
        for ddl_line in ddl_text.lines() {
            lines.push((2, ddl_line.to_string()));
        }
    }

    lines
}

// ── Utility helpers ──────────────────────────────────────────────

/// Convert a JSON value to a display string.
fn value_to_str(val: &JsonValue) -> String {
    match val {
        JsonValue::String(s) => s.clone(),
        JsonValue::Number(n) => n.to_string(),
        JsonValue::Bool(b) => b.to_string(),
        JsonValue::Null => "null".to_string(),
        JsonValue::Array(arr) => {
            let items: Vec<String> = arr.iter().map(value_to_str).collect();
            format!("[{}]", items.join(", "))
        }
        JsonValue::Object(_) => serde_json::to_string(val).unwrap_or_default(),
    }
}

/// Build the YAML output from line tuples (indent_level, content).
fn build_yaml(lines: &[(usize, String)]) -> String {
    lines
        .iter()
        .map(|(level, content)| {
            let prefix = " ".repeat(level * 2);
            format!("{}{}", prefix, content)
        })
        .collect::<Vec<_>>()
        .join("\n")
}

// ── Main entry point ─────────────────────────────────────────────

/// Generate a complete data contract YAML document from a JSON Schema
/// and an optional shim configuration.
///
/// # Arguments
///
/// * `schema` — The parsed JSON Schema value.
/// * `shim` — Optional shim configuration with governance/operational metadata.
/// * `schema_path` — Optional path to the original schema file for metadata.
pub fn generate_data_contract_yaml(
    schema: &JsonValue,
    shim: Option<&DataContractShim>,
    schema_path: Option<&str>,
) -> String {
    let mut lines: Vec<(usize, String)> = Vec::new();

    // Document header
    lines.push((0, "# Data Contract".to_string()));
    if let Some(path) = schema_path {
        lines.push((0, format!("# Source: {}", path)));
    }
    lines.push((0, String::new()));

    // Version of the shim format
    let shim_version = shim.map(|s| s.version.as_str()).unwrap_or("1.0");
    lines.push((
        0,
        format!("data_contract_version: {}", yaml_scalar(shim_version)),
    ));
    lines.push((0, String::new()));

    // Contract metadata
    let contract_lines = write_contract_section(schema, shim);
    if !contract_lines.is_empty() {
        lines.extend(contract_lines);
        lines.push((0, String::new()));
    }

    // Schema types and fields
    let schema_lines = write_schema_section(schema);
    if !schema_lines.is_empty() {
        lines.push((0, "schema:".to_string()));
        lines.extend(schema_lines);
        lines.push((0, String::new()));
    }

    if let Some(s) = shim {
        // Ownership
        if let Some(ref ownership) = s.ownership {
            let own_lines = write_ownership_section(ownership);
            if !own_lines.is_empty() {
                lines.push((0, "ownership:".to_string()));
                lines.extend(own_lines);
                lines.push((0, String::new()));
            }
        }

        // Quality
        if !s.quality.is_empty() {
            lines.push((0, "quality:".to_string()));
            let q_lines = write_quality_section(&s.quality);
            lines.extend(q_lines);
            lines.push((0, String::new()));
        }

        // SLA
        if !s.sla.is_empty() {
            lines.push((0, "sla:".to_string()));
            let sla_lines = write_sla_section(&s.sla);
            lines.extend(sla_lines);
            lines.push((0, String::new()));
        }

        // Lineage
        if let Some(ref lineage) = s.lineage {
            let lin_lines = write_lineage_section(lineage);
            if !lin_lines.is_empty() {
                lines.push((0, "lineage:".to_string()));
                lines.extend(lin_lines);
                lines.push((0, String::new()));
            }
        }

        // Retention
        if let Some(ref retention) = s.retention {
            let ret_lines = write_retention_section(retention);
            if !ret_lines.is_empty() {
                lines.push((0, "retention:".to_string()));
                lines.extend(ret_lines);
                lines.push((0, String::new()));
            }
        }

        // Access
        if let Some(ref access) = s.access {
            let acc_lines = write_access_section(access);
            if !acc_lines.is_empty() {
                lines.push((0, "access:".to_string()));
                lines.extend(acc_lines);
                lines.push((0, String::new()));
            }
        }

        // Lifecycle
        if let Some(ref lifecycle) = s.lifecycle {
            let lc_lines = write_lifecycle_section(lifecycle);
            if !lc_lines.is_empty() {
                lines.push((0, "lifecycle:".to_string()));
                lines.extend(lc_lines);
                lines.push((0, String::new()));
            }
        }

        // Partitioning
        if let Some(ref part) = s.partitioning {
            let part_lines = write_partitioning_section(part);
            if !part_lines.is_empty() {
                lines.push((0, "partitioning:".to_string()));
                lines.extend(part_lines);
                lines.push((0, String::new()));
            }
        }

        // Cost
        if let Some(ref cost) = s.cost {
            let cost_lines = write_cost_section(cost);
            if !cost_lines.is_empty() {
                lines.push((0, "cost:".to_string()));
                lines.extend(cost_lines);
                lines.push((0, String::new()));
            }
        }

        // Tags
        if !s.tags.is_empty() {
            lines.push((0, "tags:".to_string()));
            let tag_lines = write_tags_section(&s.tags);
            lines.extend(tag_lines);
            lines.push((0, String::new()));
        }
    }

    // Relational DDL derived from schema
    let rel_lines = write_relational_section(schema);
    if !rel_lines.is_empty() {
        lines.push((0, "relational:".to_string()));
        lines.extend(rel_lines);
        lines.push((0, String::new()));
    }

    // x-dc-* extensions at schema level
    if let Some(obj) = schema.as_object() {
        let dc_exts: Vec<(String, String)> = obj
            .iter()
            .filter(|(k, _)| k.starts_with("x-dc-"))
            .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
            .collect();
        if !dc_exts.is_empty() {
            lines.push((0, "extensions:".to_string()));
            for (key, val) in dc_exts {
                let label = key.strip_prefix("x-dc-").unwrap_or(&key);
                lines.push((1, format!("{}: {}", yaml_scalar(label), yaml_scalar(&val))));
            }
            lines.push((0, String::new()));
        }
    }

    build_yaml(&lines)
}

// ── Tests ────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample_schema() -> JsonValue {
        json!({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "User Service",
            "description": "User domain schema",
            "$defs": {
                "User": {
                    "type": "object",
                    "description": "A user account",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique identifier",
                            "minLength": 1,
                            "maxLength": 36
                        },
                        "name": {
                            "type": "string",
                            "minLength": 1
                        },
                        "email": {
                            "type": "string",
                            "format": "email"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["ACTIVE", "INACTIVE", "PENDING"],
                            "default": "ACTIVE"
                        },
                        "tags": {
                            "type": "array",
                            "items": { "type": "string" }
                        }
                    },
                    "required": ["id", "name", "email"]
                }
            }
        })
    }

    fn sample_shim() -> DataContractShim {
        let json = serde_json::json!({
            "contract": {
                "name": "User Service Contract",
                "version": "2.1.0",
                "status": "active",
                "domain": "identity"
            },
            "ownership": {
                "team": "platform-identity",
                "contact": "team@example.com"
            },
            "quality": [
                {
                    "metric": "completeness",
                    "field": "#/$defs/User/properties/email",
                    "threshold": 0.95
                }
            ],
            "tags": ["customer-data", "tier-1"]
        });
        serde_json::from_value(json).unwrap()
    }

    #[test]
    fn test_yaml_scalar() {
        assert_eq!(yaml_scalar("hello"), "hello");
        assert_eq!(yaml_scalar(""), "\"\"");
        assert_eq!(yaml_scalar("true"), "\"true\"");
        assert_eq!(yaml_scalar("key: value"), "\"key: value\"");
        // Newlines are handled by wrapping in quotes (literal newline preserved)
        let result = yaml_scalar("has\nnewline");
        assert!(result.starts_with('"'));
        assert!(result.ends_with('"'));
        assert!(result.contains("has"));
        assert!(result.contains("newline"));
    }

    #[test]
    fn test_json_type_display() {
        let string_field = json!({"type": "string"});
        assert_eq!(json_type_display(&string_field), "string");

        let array_field = json!({"type": "array", "items": {"type": "string"}});
        assert_eq!(json_type_display(&array_field), "array<string>");

        let ref_array = json!({"type": "array", "items": {"$ref": "#/$defs/Tag"}});
        assert_eq!(json_type_display(&ref_array), "array<Tag>");
    }

    #[test]
    fn test_generate_without_shim() {
        let yaml = generate_data_contract_yaml(&sample_schema(), None, None);
        assert!(yaml.contains("data_contract_version: 1.0"));
        assert!(yaml.contains("name: User Service"));
        assert!(yaml.contains("schema:"));
        assert!(yaml.contains("User:"));
        assert!(yaml.contains("id: string (required)"));
        assert!(yaml.contains("email: string"));
        assert!(yaml.contains("format: email"));
        assert!(yaml.contains("status: string"));
        assert!(yaml.contains("enum: [ACTIVE, INACTIVE, PENDING]"));
        assert!(yaml.contains("relational:"));
    }

    #[test]
    fn test_generate_with_shim() {
        let shim = sample_shim();
        let yaml = generate_data_contract_yaml(&sample_schema(), Some(&shim), None);
        assert!(yaml.contains("name: User Service Contract"));
        assert!(yaml.contains("version: 2.1.0"));
        assert!(yaml.contains("ownership:"));
        assert!(yaml.contains("team: platform-identity"));
        assert!(yaml.contains("quality:"));
        assert!(yaml.contains("metric: completeness"));
        assert!(yaml.contains("threshold: 0.95"));
        assert!(yaml.contains("tags:"));
        assert!(yaml.contains("- customer-data"));
    }

    #[test]
    fn test_generate_with_schema_path() {
        let yaml =
            generate_data_contract_yaml(&sample_schema(), None, Some("/path/to/schema.json"));
        assert!(yaml.contains("# Source: /path/to/schema.json"));
    }

    #[test]
    fn test_empty_schema() {
        let empty = json!({});
        let yaml = generate_data_contract_yaml(&empty, None, None);
        assert!(yaml.contains("data_contract_version: 1.0"));
        assert!(yaml.contains("name: Unnamed Contract"));
    }
}
