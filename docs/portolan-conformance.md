# Portolan conformance register

This file records every `rashid` finding that geocontract accepts without
fixing. An empty register is the goal.

The rule, from `portolan-skills/skills/git-backed-catalog/SKILL.md`: never
widen this list to make CI green. Each accepted finding needs a row here
**and** a tracking issue, or neither. A row without an issue hides debt. An
issue without a row fails CI.

For findings that are answered by design rather than accepted as debt, see
[`portolan-conformance-notes.md`](./portolan-conformance-notes.md). That file
records what the validator enforces and why the generator emits what it does.

---

## How to read a row

| Column | Meaning |
| --- | --- |
| Rule | The `PTL-*` id `rashid` reports |
| Scope | The file or collection the finding lands on |
| Severity | `error`, `warning`, or `info` as reported |
| Why accepted | The reason the finding is not a defect here |
| Tracking issue | The issue that closes the row, as `#N` |

A row is removed when the tracking issue closes. Remove the row and the
`CI_LIGHT`-style exemption in the same change, so the gate tightens again.

---

## Accepted findings

| Rule | Scope | Severity | Why accepted | Tracking issue |
| --- | --- | --- | --- | --- |
| _(none)_ | | | | |

---

## Informational findings that are expected

These are not accepted debt. They are the ceiling for a conformant catalog,
and the specification's own reference catalog reports them too.

| Rule | Scope | Why expected |
| --- | --- | --- |
| `PTL-PRO-002` | mirror collections | Asks for a `rel: canonical` link. Add one only when the upstream publishes its own STAC catalog. The reference catalog reports this 16 times and passes. |

Verify the ceiling yourself:

```bash
mise run portolan-calibrate
```

Expected output:

```text
0 error(s), 0 warning(s), 16 info(s) across 28 files.
```
