# PIC NEPA Data Standard v1.2

The PIC NEPA Data and Technology Standard v1.2, a structured schema for
environmental-review data collected during review. Producers and
consumers agree on the entity shape so that records from different
agencies can be compared and federated.

The standard defines 13 entities. This collection publishes the data
contract that governs all of them:

`Project`, `ProcessInstance`, `Document`, `Comment`, `Engagement`,
`CaseEvent`, `GisData`, `GisDataElement`, `UserRole`,
`DecisionElement`, `ProcessModel`, `ProcessDecisionPayload`,
`LegalStructure`.

## Provenance

The Permitting Innovation Center produces the standard at
<https://permitting.innovation.gov/resources/data-standard/>.
geocontract hosts this copy and did not produce the standard, so this
collection is a mirror.

The contract's own `customProperties` cite
`https://github.com/permits/pyper` as the source repository. That URL
returned 404 when checked on 3 October 2026, so the verified PIC
landing page is cited here instead. The contract is left as authored.

## License

CC0-1.0. See <https://spdx.org/licenses/CC0-1.0.html>.

## Scope note

v1.2 deliberately does not prescribe a wire format. Sample payloads are
published as JSON, YAML, OpenAPI, and SQL DDL, so the contract governs
the entity shape rather than one encoding of it. Top-level container
keys use the standard's own spelling, including `processe_instances`.
