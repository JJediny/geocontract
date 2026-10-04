# Agent Guidance, Harvested Mirrors

This sub-catalog contains mirror collections harvested from external sources.

## Structure

Each mirror collection has:
- `collection.json`: STAC collection with mirror metadata
- `source` asset: The original contract YAML
- `README.md`: Human-readable description
- `AGENTS.md`: Agent guidance

## Harvesting

Mirrors are created by the federated harvester:

```bash
uv run geocontract-harvest --sink portolan <source-url>
```

See `docs/design-harvester.md` for details.
