//! Data contract shim configuration types.
//!
//! These structs represent the cross-cutting, operational metadata
//! that cannot be expressed natively in JSON Schema. Users provide
//! a JSON shim file (valid YAML) that maps schema entities to
//! governance, quality, lineage, and other metadata.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

/// Top-level shim configuration for a data contract.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataContractShim {
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(default)]
    pub schema: Option<SchemaRef>,
    pub contract: ContractMeta,
    #[serde(default)]
    pub ownership: Option<OwnershipMeta>,
    #[serde(default)]
    pub quality: Vec<QualityCheck>,
    #[serde(default)]
    pub sla: Vec<SlaDef>,
    #[serde(default)]
    pub lineage: Option<LineageMeta>,
    #[serde(default)]
    pub retention: Option<RetentionPolicy>,
    #[serde(default)]
    pub access: Option<AccessControl>,
    #[serde(default)]
    pub lifecycle: Option<LifecycleMeta>,
    #[serde(default)]
    pub partitioning: Option<PartitioningMeta>,
    #[serde(default)]
    pub cost: Option<CostMeta>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub entities: serde_json::Map<String, serde_json::Value>,
}

fn default_version() -> String {
    "1.0".to_string()
}

/// Reference to the JSON Schema file this shim accompanies.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SchemaRef {
    pub schema: Option<String>,
    pub source: Option<String>,
}

/// Contract-level metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContractMeta {
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    pub version: String,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub domain: Option<String>,
}

/// Ownership and team contact information.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OwnershipMeta {
    #[serde(default)]
    pub team: Option<String>,
    #[serde(default)]
    pub contact: Option<String>,
    #[serde(default)]
    pub slack: Option<String>,
    #[serde(default)]
    pub oncall: Option<String>,
    #[serde(default)]
    pub docs_url: Option<String>,
}

/// Quality SLO check definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityCheck {
    pub metric: String,
    #[serde(default)]
    pub field: Option<String>,
    pub threshold: serde_json::Value,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub rule: Option<String>,
}

/// SLA definition providing runtime guarantees.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlaDef {
    pub name: String,
    pub target: String,
    #[serde(default)]
    pub window: Option<String>,
}

/// Lineage information listing upstream sources and downstream consumers.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LineageMeta {
    #[serde(default)]
    pub upstream: Vec<LineageEntry>,
    #[serde(default)]
    pub downstream: Vec<LineageEntry>,
}

/// A single lineage entry for a source or consumer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineageEntry {
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub consumer: Option<String>,
    #[serde(rename = "type", default)]
    pub entry_type: Option<String>,
    #[serde(default)]
    pub topic: Option<String>,
    #[serde(default)]
    pub format: Option<String>,
    #[serde(default)]
    pub endpoint: Option<String>,
}

/// Data retention and archival policy.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RetentionPolicy {
    #[serde(default)]
    pub policy: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub delete_after: Option<String>,
    #[serde(default)]
    pub archive_after: Option<String>,
    #[serde(default)]
    pub partition_strategy: Option<String>,
}

/// Access control and compliance classification.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AccessControl {
    #[serde(default)]
    pub classification: Option<String>,
    #[serde(default)]
    pub pii_fields: Vec<String>,
    #[serde(default)]
    pub compliance: Vec<ComplianceEntry>,
}

/// Compliance regulation reference.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceEntry {
    pub regulation: String,
    #[serde(default)]
    pub justification: Option<String>,
}

/// Lifecycle timestamps and changelog.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LifecycleMeta {
    #[serde(default)]
    pub created: Option<String>,
    #[serde(default)]
    pub last_modified: Option<String>,
    #[serde(default)]
    pub sunset_date: Option<String>,
    #[serde(default)]
    pub changelog: Vec<ChangelogEntry>,
}

/// A single changelog entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChangelogEntry {
    pub version: String,
    pub date: String,
    #[serde(default)]
    pub summary: Option<String>,
}

/// Data partitioning strategy metadata.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PartitioningMeta {
    #[serde(default)]
    pub strategy: Option<String>,
    #[serde(default)]
    pub column: Option<String>,
    #[serde(default)]
    pub granularity: Option<String>,
    #[serde(default)]
    pub retention_days: Option<u64>,
}

/// Cost and budget attribution metadata.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CostMeta {
    #[serde(default)]
    pub center: Option<String>,
    #[serde(default)]
    pub budget_code: Option<String>,
    #[serde(default)]
    pub estimated_annual_cost_usd: Option<u64>,
}

/// Load a data contract shim from a JSON file path.
///
/// JSON is a subset of YAML, so JSON files are valid YAML.
/// This avoids adding a `serde_yaml` dependency.
pub fn load_shim(path: &str) -> Result<DataContractShim, String> {
    let contents = fs::read_to_string(Path::new(path))
        .map_err(|e| format!("Failed to read shim file '{}': {}", path, e))?;
    serde_json::from_str(&contents)
        .map_err(|e| format!("Failed to parse shim file '{}': {}", path, e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_minimal_shim() {
        let json = r#"{
            "contract": {
                "name": "Test Contract",
                "version": "1.0.0"
            }
        }"#;
        let shim: DataContractShim = serde_json::from_str(json).unwrap();
        assert_eq!(shim.contract.name, "Test Contract");
        assert_eq!(shim.contract.version, "1.0.0");
        assert_eq!(shim.version, "1.0");
        assert!(shim.ownership.is_none());
    }

    #[test]
    fn test_deserialize_full_shim() {
        let json = r##"{
            "version": "1.0",
            "contract": {
                "name": "User Service",
                "description": "User domain contract",
                "version": "2.1.0",
                "status": "active",
                "domain": "identity"
            },
            "ownership": {
                "team": "platform-identity",
                "contact": "team@example.com",
                "slack": "#identity-platform"
            },
            "quality": [
                {
                    "metric": "freshness",
                    "field": "#/$defs/User/properties/updatedAt",
                    "threshold": "24h",
                    "description": "Updated within 24h"
                }
            ],
            "sla": [
                {
                    "name": "read-latency",
                    "target": "p95 < 100ms",
                    "window": "rolling-7d"
                }
            ],
            "lineage": {
                "upstream": [
                    {
                        "source": "event://identity.user.created",
                        "type": "kafka",
                        "topic": "identity.events",
                        "format": "avro"
                    }
                ],
                "downstream": []
            },
            "retention": {
                "policy": "GDPR-7y",
                "delete_after": "7y"
            },
            "access": {
                "classification": "restricted",
                "pii_fields": ["#/$defs/User/properties/email"],
                "compliance": [
                    {
                        "regulation": "GDPR",
                        "justification": "Contains EU citizen PII"
                    }
                ]
            },
            "lifecycle": {
                "created": "2024-01-15",
                "changelog": [
                    {
                        "version": "2.1.0",
                        "date": "2026-06-01",
                        "summary": "Added phone field"
                    }
                ]
            },
            "partitioning": {
                "strategy": "time",
                "column": "createdAt",
                "granularity": "day",
                "retention_days": 730
            },
            "cost": {
                "center": "platform-1234",
                "budget_code": "PLATFORM-CORE",
                "estimated_annual_cost_usd": 15000
            },
            "tags": ["pci-dss", "tier-1"],
            "entities": {
                "$defs/User": {
                    "classification": "restricted",
                    "pii": true
                }
            }
        }"##;
        let shim: DataContractShim = serde_json::from_str(json).unwrap();
        assert_eq!(shim.contract.name, "User Service");
        assert_eq!(shim.ownership.unwrap().team.unwrap(), "platform-identity");
        assert_eq!(shim.quality.len(), 1);
        assert_eq!(shim.sla.len(), 1);
        assert_eq!(shim.tags.len(), 2);
    }

    #[test]
    fn test_load_shim_file() {
        // Test loading from the test-data directory
        // Tests run from the crate root (converters/rust/)
        let path = "../test-data/datacontract-shim.json";
        let shim = load_shim(path).unwrap();
        assert_eq!(shim.contract.name, "Sample Contract");
        assert_eq!(shim.contract.version, "1.0.0");
        assert!(shim.ownership.is_some());
        assert_eq!(shim.quality.len(), 3);
    }
}
