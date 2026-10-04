# Phase 5 PR: Documentation & Integration Guide

## What changed

Adds comprehensive documentation for the geocontract Portolan catalog integration.

- Creates `docs/portolan-integration-guide.md` with complete usage instructions
- Documents how to consume, publish, and contribute to the catalog
- Covers all three collection types: federal, mirror, and citizen proposals
- Explains validation gates and architecture
- Updates `AGENTS.md` with new skill map entries for harvest and citizen proposals

## Why

The Portolan catalog integration is now complete across all 5 phases. Users need
clear documentation on how to:

1. **Consume the catalog** - Search and retrieve collections using rashid CLI or Python
2. **Publish the catalog** - Use CI/CD or manual publishing to S3
3. **Contribute contracts** - Submit federal contracts, citizen proposals, or mirror external catalogs
4. **Validate changes** - Use ODCS and rashid validators before merging

The integration guide consolidates all this information in one place, making it
easy for both humans and AI agents to understand the system.

## Verification

```bash
# Verify documentation exists
$ ls -la docs/portolan-integration-guide.md
-rw-rw-r-- 1 john john 4523 Oct  3 22:30 docs/portolan-integration-guide.md

# Verify AGENTS.md has new skill entries
$ grep -A 2 "Harvest external catalogs" AGENTS.md
| Harvest external catalogs | `skills/federated-harvest/` |
| Integrate citizen proposals | `skills/citizen-proposals/` |

# Verify all catalog files still validate
$ mise run catalog-check
✓ catalog validates: 0 errors, 0 warnings

# Verify all tests still pass
$ uv run pytest scripts/tests/ -v
✓ 36 passed
```

Documentation path: `docs/portolan-integration-guide.md`

## Checklist

- [x] Integration guide created with complete usage instructions
- [x] All three collection types documented (federal, mirror, citizen)
- [x] Publishing workflow documented (dry-run and confirm)
- [x] Contribution process documented for all contract types
- [x] Validation gates documented (ODCS + rashid)
- [x] Architecture references provided
- [x] AGENTS.md skill map updated
- [x] Catalog validates with 0 errors, 0 warnings
- [x] All tests pass
- [ ] Human review and approval required before merge
