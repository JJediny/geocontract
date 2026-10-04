# Agent Guidance, Groton Rhine St. Façade Repair — Worked Example (v2)

The `contract` asset is the ODCS-flatten projection of a v2 canonical
Proposal. It is the PUBLIC projection. Read
`docs/plan-citizen-permitting-standard.md` section 5.8 for the split.

The restricted projection carries `applicant.*`, `proof.*`, and raw
parcel geometry. None of it is in this collection, and no tool in this
tree publishes it. `geocontract-harvest-citizen` refuses the restricted
projection without `--authority-token`.

## Quirks

- The example is fictional. Do not treat the applicant, the parcel
  identifier, or the signatures as real records.
- `accessClass` is `public` in the contract's `customProperties`. A
  proposal whose `accessClass` is anything else must not be published
  into this catalog.
- The bbox is coarsened to about 1.1 km. A spatial query at parcel
  precision will not resolve against this collection. That is intended.
- `parcelAuthority` and `parcelId` are references to an external
  authoritative registry, not the geometry itself. Resolve them at the
  authority to get location.
- `geometryFormat` allows `geojson`, `wkt`, or `h3`. The worked example
  uses `wkt`.
