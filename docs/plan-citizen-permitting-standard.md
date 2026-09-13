# Implementation Plan — Citizen-Permitting Geocontract Standard

> **Status:** Draft for review. Not yet implemented.
> **Author:** geocontract agent, in response to the user's request to
> "create an implementation plan for a full standard to support
> activities whereby any citizen can create a minimal geocontract for a
> proposed action on denoted lands."
> **Companion docs:** `docs/design-harvester.md` (Phase 1–4 harvester
> design), `templates/*.template.schema.json` (existing x-graphql-annotated
> templates), `contracts/odcs-v3.1.0-template.yaml` (existing primitive).

---

## 1. Problem statement (one paragraph)

Today the geocontract repo produces ODCS v3.1.0 contracts for **federal
catalogue** records — exclusions lists, NEPA data standards, DCAT-US
federated catalogs. The producer is always an agency. The user wants
the same machinery to support a **bottom-up, citizen-initiated** flow:

1. A resident of a municipality (worked example: **Groton, CT**,
   via the **Groton Housing Authority**) drafts a minimal
   `*.geocontract.yaml` describing a *proposed action* on a *denoted
   parcel* (housing rehabilitation, zoning change, road work, etc.).
2. The draft is hashed and submitted to a public approval registry
   that issues an **approval code** recorded on a **crypto ledger**
   (smart contract).
3. Once approved, the project can also be **funded** through a
   project-specific **coin/issuance** issued on the same ledger, so
   that residents, NGOs, and municipal agencies can all participate
   in capital formation under a single, auditable artifact.
4. The contract is then harvested by the existing
   `geocontract-harvest` machinery as just another `*.geocontract.yaml`
   source — citizen and agency contracts flow through the same
   pipeline.

### 1.1 The federal permitting catalogue is a vocabulary source, not a regulatory gate

Per the user's clarification: the
[`https://ce.permitting.innovation.gov/data/exclusions.json`](https://ce.permitting.innovation.gov/data/exclusions.json)
catalogue is consumed **only as a corpus of pre-reviewed generic
activities**. Its role is to seed the **activity ontology** that the
citizen form's `activityCode` field draws from. It is **not** used at
runtime to decide whether NEPA review applies, what federal
exemptions cover, or whether the action is environmentally
permissible.

This is a critical scope decision because it:

- Decouples the citizen flow from federal NEPA gating — a Groton
  resident filing a permit has no need to know whether the action is
  federally excluded; that's the municipal reviewer's problem.
- Lets the activity ontology reuse **CATEX short-labels** as canonical
  activity names (e.g. *"Routine administrative activities..."*) while
  the ontology itself organizes them under citizen-facing categories
  (housing, infrastructure, land-use, …).
- Means we do **not** add `nepa.catexStatus` or any other federal
  regulatory field to `ProposedAction`. The federal catalogue is
  upstream; we don't surface its decisions downstream.
- Keeps compliance surface small — the token / ledger layer never
  consults the federal catalogue, so no regulatory coupling between
  the chain and federal NEPA rules.

---

## 2. Scope

### 2.1 In scope

- A **generic activity ontology** — seeded by the federal CATEX
  catalogue as a vocabulary source, then broadened via a corpus scan
  of the user's starred projects and other public sources (see §4).
- A **minimal contract shape** — `MinimalProposedAction` ODCS object —
  that a citizen (no GIS expertise, no JSON-Schema knowledge) can fill
  in via a guided form and have it serialize to a valid
  `*.geocontract.yaml`.
- **Ledger integration design** — three sub-questions:
  - Which chain(s)?
  - Which **smart-contract pattern** for the approval registry?
  - Which **token standard** for fundraising?
- **Conflict / overlap** with the existing `ExclusionsVersion`,
  `Exclusion`, `Project`, `ProcessInstance` entities already in
  `templates/nepa-exclusions.template.schema.json` and
  `templates/pic-standards.template.schema.json`.
- **Alternatives analysis** for every tool selection (see §5).
- **Steering questions** for the user before code is written
  (see §11).

### 2.2 Out of scope (today)

- Building a hosted web form (the deliverable is the **schema and the
  ledger integration design**; UI is a future PR).
- Selecting a specific municipal government as a launch partner
  beyond the worked Groton example.
- Replacing `geocontract-harvest` — the existing Phase 1–4 design
  already accommodates additional contract sources without change.
- Implementing actual smart contracts (Solidity / Move / PyTeal
  source). The deliverable is the **interface, ABI, and event
  schema**, not deployed bytecode.

---

## 3. The "minimal" contract — what a citizen fills in

Derived from the existing primitive `contracts/odcs-v3.1.0-template.yaml`
plus the new citizen use case, the minimum input a citizen form
should produce is:

| Field                    | Type             | Example                          | Source          |
|--------------------------|------------------|----------------------------------|-----------------|
| `apiVersion`             | const `v3.1.0`   | —                                | ODCS            |
| `kind`                   | const `DataContract` | —                            | ODCS            |
| `id`                     | string           | `groton-pha-2026-rhine-001`      | citizen         |
| `version`                | semver           | `0.1.0`                          | citizen         |
| `name`                   | string           | "Rhine St. façade repair"        | citizen         |
| `description.purpose`    | string           | free text ≤ 500 chars            | citizen         |
| `tenant`                 | enum             | `us-ct-groton`                   | derived from address |
| `domain`                 | enum (activity ontology) | `housing-rehabilitation` | form            |
| `tags`                   | string[]         | `["citizen-initiated","groton"]` | form            |
| `servers[0]`             | object           | `null` (no public endpoint)      | implicit        |
| `schema[0].name`         | const `ProposedAction` | —                          | new             |
| `schema[0].properties`   | object           | see §3.1                         | form            |

### 3.1 `ProposedAction` schema

```yaml
- name: ProposedAction
  logicalType: object
  physicalType: JSON
  physicalName: proposed_action
  required: true
  classification: public
  properties:
    - name: parcel
      logicalType: object
      required: true
      properties:
        - name: parcelId
          logicalType: string
          required: true
          examples: ["M:123 B:45 L:678"]
        - name: address
          logicalType: string
          required: true
          examples: ["42 Rhine Street, Groton, CT 06340"]
        - name: geometry
          logicalType: string           # GeoJSON, WKT, or H3 cell id
          physicalType: TEXT
          required: false
    - name: activityCode
      logicalType: string
      required: true
      # value drawn from ActivityOntology (see §4)
      examples: ["housing.rehabilitation.facade"]
    - name: estimatedCostUsd
      logicalType: number
      physicalType: NUMERIC(12,2)
      required: false
    - name: fundingGoal
      logicalType: object
      required: false
      properties:
        - name: raiseTarget
          logicalType: number
          physicalType: NUMERIC(12,2)
        - name: tokenSymbol       # proposed ERC-20 / SUI coin symbol
          logicalType: string
          pattern: "^[A-Z]{3,5}$"
        - name: acceptChainIds
          logicalType: array
          items: { logicalType: integer }
    - name: citizenClaim
      logicalType: object
      required: true
      properties:
        - name: claimantAddress   # municipal residency proof (w3c-vc)
          logicalType: string
        - name: residencyProofUri
          logicalType: string     # ipfs:// or https:// VC document
        - name: signature         # EIP-191 / Ed25519 sig over canonical hash
          logicalType: string
```

This is intentionally **ODCS-compliant** (every property above maps to
an existing ODCS v3.1.0 `SchemaProperty` field) so the citizen contract
passes through `scripts/validate_odcs.py --master` unchanged.

---

## 4. Activity ontology — built from the federal corpus + broader public sources

### 4.1 The federal permitting catalogue is input, not output

The user's clarification reframes §4:

> *"federal permitting in this case is only as a source of pre-reviewed
> generic activities"*

Read in full, this means:

- The CATEX catalogue
  (`https://ce.permitting.innovation.gov/data/exclusions.json`) is
  consumed **as a corpus of generic activity descriptions**, not as a
  regulator's "what's exempt from NEPA" answer.
- Its role is to **seed the activity ontology** with human-readable
  short labels (each `catexId` is already a brief generic-activity
  description, e.g. *"Routine administrative activities..."*).
- The **consumer** of the citizen contract is a **municipal**
  permitting office, not a federal reviewer. Federal NEPA review is
  not surfaced in `ProposedAction`, the harvester output, or the
  ledger.
- This also collapses a class of compliance risk: the token / ledger
  layer never consults the federal catalogue, so no regulatory
  coupling between the chain and NEPA.

### 4.2 What the exclusions list actually contributes

Each CATEX entry has the shape:

```json
{
  "agency": "USDA",
  "citation": "7 CFR 1b.3(a)",
  "catexId": "Routine administrative activities...",
  "context": "...",
  "extraordinaryCircumstances": "..."
}
```

For ontology purposes we only extract:

| Field      | Used as                  | Notes                                  |
|------------|--------------------------|----------------------------------------|
| `catexId`  | **activity short label** | Lower-cased, snake-cased → ontology key |
| `agency`   | jurisdictional seed      | Optional routing hint                  |
| `citation` | provenance citation      | Cross-reference, not a regulatory gate |

Two structural facts matter:

1. Each entry is keyed by a `(agency, citation, catexId)` triple —
   there is no clean activity taxonomy embedded.
2. The `catexId` field is human-readable text. We parse and bucket
   them into ontology leaves with NLP heuristics (see §4.4).

### 4.3 Why we still need something broader than the federal catalogue

The citizen use case includes **actions that are not in the CATEX
catalogue at all** — building a deck, paving a driveway, opening a
food-truck lot, a community garden plot. The federal catalogue
covers federal-agency-only actions; municipal permitting sees a
much wider universe. So:

- **Seed corpus:** the federal CATEX catalogue (≈2,105 entries
  spanning 78 federal agency units).
- **Enrichment corpus:** the additional sources in the table below.

### 4.4 Enrichment sources to consult

The user requested "an ontology scan of the text reviewing my starred
projects for graph-like tagging of a corpus." After `gh auth` was
restored, the actual starred-projects corpus was enumerated. From it,
the following repos are most relevant to the activity-ontology scan:

**Geospatial & GIS (high relevance to activity ontology)**

| Repo                                                  | Why it matters for the ontology |
|-------------------------------------------------------|---------------------------------|
| `apache/sedona`                                       | Cluster computing for geospatial data — drives large-scale activity clustering. |
| `opengeos/GeoAgent`                                   | Multimodal AI agent for geospatial data — the citizen form's UX precedent. |
| `opengeos/GeoLibre`                                   | Lightweight cloud-native GIS — the canonical viewer for `ProposedAction.geometry`. |
| `opengeos/geolibre-rust`                              | Rust geospatial tools — re-usable code for parcel geometry handling. |
| `geoparquet/geoparquet-io`                            | GeoParquet tooling — bulk activity catalogue export format. |
| `komoot/photon`                                       | Open-source OSM geocoder — address↔geometry binding for the `parcel.address` field. |
| `felixpalmer/a5`                                      | Pentagonal DGGS indexing — alternative to H3 for `geometry` representation. |
| `c2g-dev/city2graph` + `city2graph-workshop`          | Geo relations → GNN graphs — the *graph* framing the user explicitly requested. |
| `manaakiwhenua/raster2dggs`                           | Raster-to-DGGS — bulk ingestion of municipal land-use rasters. |
| `dekart-xyz/geosql`                                   | Geospatial skill for AI agents — precedent for AI-assisted form UX. |
| `maplibre/martin` / `awesome-maplibre` / `maputnik`   | Tile-server + style editor — harvester visualisation layer. |
| `radiantearth/stac-browser` / `stac-collection-discovery` | STAC catalogue browser — precedent for harvesting activity records. |
| `OvertureMaps/overture-tiles`                         | Overture Maps tiles — global reference geometry. |
| `NVIDIA/earth2studio`                                 | Earth/climate workflows — environmental-activity context. |
| `developmentseed/contributor-network`                 | Contributor-graph tooling — provenance pattern for activity ontologies. |

**Ontology, knowledge graphs & semantic web (high relevance)**

| Repo                                                  | Why it matters |
|-------------------------------------------------------|----------------|
| `wlsdks/ontology-atlas`                               | "One shared Markdown ontology for humans and coding agents." Direct precedent for a Markdown-based activity ontology committed to git. |
| `growgraph/ontocast`                                  | "Agentic Ontology Assisted Framework for Semantic Triple Extraction." Direct tooling candidate for the NLP/clustering pipeline. |
| `aws/context-ontology-accelerator`                    | "Ontology-based semantic context accelerator for AI agents." Pattern reference. |
| `semantica-agi/semantica`                             | "Graph-Native Infrastructure for Context and Accountable AI Systems." |
| `SemanticDataCharter/sdcgovernance`                   | Standards-based governance execution — precedent for `description.governance` on activity leaves. |
| `kstrieder/jsonLdSPA`                                 | JSON-LD SPA tooling — W3C ADR-style address publishing pattern. |
| `lumina-ai-inc/chunkr`                                | Document → RAG-ready — the citizen form's intake pipeline pattern. |
| `0xPlaygrounds/rig` / `awesome-rig`                   | LLM orchestration framework — for the ontology-clustering pipeline. |
| `awslabs/oscal-content-for-aws-services` / `oscal-content` | OSCAL content — controls/governance catalogue parallel. |
| `compliance-framework/{ui,api}`                       | Compliance framework — precedent for `description.regulatoryLimits`. |

**Standards / contracts / data catalogues**

| Repo                                                  | Why it matters |
|-------------------------------------------------------|----------------|
| `bitol-io/open-data-contract-standard`                | The canonical schema this entire repo extends. |
| `datacontract/datacontract-cli`                       | The validator CLI. |
| `awslabs/open-data-registry`                          | Federated open-data registry — harvester design precedent. |
| `app-sre/qontract-schemas`                            | App-SRE contract schemas — precedent for cataloguing contract schemas. |

**Public-sector / civic infrastructure**

| Repo                                                  | Why it matters |
|-------------------------------------------------------|----------------|
| `GSA/threat-analysis`                                 | Federal threat-analysis patterns. |
| `GSA-TTS/agentic-coding-quickstart`                   | GSA TTS pattern library. |
| `GSA-TTS/svelte-ui`                                   | UI pattern library. |
| `compliance-framework/{ui,api}`                       | Compliance API patterns. |
| `karakeep-app/karakeep`                               | Bookmarking pattern — provenance trail. |
| `zalando/tech-radar`                                  | Public tech-radar pattern (visualisation of allowed activities). |
| `logto-io/logto`                                      | Identity provider — strong fit for citizen claim (§5.3). |
| `korbin-ai/...`                                       | (etc — see full corpus in §4.4.1) |

#### 4.4.1 Correlating starred projects with ontology activities

Sampling the corpus's top-level categories yields the following
**candidate activity buckets**, which are stronger than the initial
NAICS-derived draft because they reflect the user's *actual* tagged
interests:

1. **Geospatial data engineering** — `apache/sedona`,
   `opengeos/*`, `geoparquet/*`, `komoot/photon`, `manaakiwhenua/*`
   → ontology leaf: `data_engineering.geospatial.{ingest,transform,
   serve}`.
2. **Ontology / knowledge-graph tooling** — `wlsdks/ontology-atlas`,
   `growgraph/ontocast`, `aws/context-ontology-accelerator`,
   `semantica-agi/semantica`, `kstrieder/jsonLdSPA`,
   `c2g-dev/city2graph` → leaf: `data_engineering.semantic.{triple,
   embedding,rdf,kg}`.
3. **Standards / cataloguing** — `bitol-io/open-data-contract-standard`,
   `datacontract/datacontract-cli`, `awslabs/open-data-registry`,
   `app-sre/qontract-schemas`, `radiantearth/stac-browser` →
   leaf: `standards.{contract,registry,catalog}`.
4. **Compliance / governance** — `compliance-framework/*`,
   `awslabs/oscal-content-for-aws-services`, `SemanticDataCharter/*` →
   leaf: `governance.{controls,evidence,attestation}`.
5. **Civic / public-sector data engineering** — `GSA/*`,
   `GSA-TTS/*` → leaf: `civic.federal.{publishing,registry,api}`.
6. **Identity & credentialing** — `logto-io/logto`, `voidauth/voidauth`,
   `Infisical/infisical`, `infisical/cli` →
   leaf: `identity.{oidc,credential,residency_proof}`.

The §4.6 top-level draft taxonomy is preserved (it's citizen-facing,
not corpus-internal), but the §4.5 ingestion pipeline's enrichment
corpus is now grounded in the user's actual starred projects.

**Public-domain enrichment sources** (still relevant, even though
not starred):

| Source                                                | Type                          | Coverage                          | License        |
|-------------------------------------------------------|-------------------------------|-----------------------------------|----------------|
| `https://schema.org/Action`                           | schema.org Action             | generic web actions               | CC-BY-SA 3.0   |
| `https://www.w3.org/TR/vocab-adr/#acties`             | W3C ADR (Address)             | real-estate actions               | W3C            |
| `http://vocab.linkeddata.es/dcat-ap-es/`              | Spain DCAT-AP profile         | public-sector activities          | CC-BY 4.0      |
| NAICS (https://www.census.gov/naics/)                 | North American Industry Class | economic activities               | Public domain  |
| UN ISIC Rev. 4                                        | UN Industrial Classification  | economic activities (global)      | Public domain  |
| Local municipal code corpuses                         | ordinances.csv (Groton, Hartford, …) | hyperlocal activities    | varies         |

### 4.5 Ontology construction — proposed pipeline

```
1. INGEST
   - Federal CATEX catalogue (JSON, 4 MB)
   - Each starred project's README/docs (after Q1)
   - NAICS divisions + descriptions
   - Municipal ordinances corpus (Groton, peer towns)

2. NLP / GRAPH TAGGING
   - Lower-case, snake-case each catexId into a candidate leaf key
   - Cluster candidates with sentence-transformers (all-MiniLM-L6-v2)
     using cosine similarity ≥ 0.78 to merge near-duplicates
   - Hand-label clusters with one of the bucket labels in §4.6
   - Embed cluster centroids into a SQLite FTS5 + sqlite-vec index for
     the citizen form's autocomplete

3. EMIT ONTOLOGY
   contracts/activity-ontology.datacontract.yaml
     — an ODCS instance with one Object schema whose properties are
       the leaves; each leaf carries
       (code, humanReadableName, sourceCitation, deprecatedAfter)
```

The ontology is itself a **`*.geocontract.yaml`**, harvested by the
same machinery. The federal CATEX catalogue contributes the
`sourceCitation` provenance on each leaf.

### 4.6 Proposed top-level activity taxonomy (initial draft)

Until the corpus scan can be run, here is a draft skeleton based on
the NAICS divisions + schema.org Action, which is the closest fit:

```
Activity
├── Construction & Infrastructure
│   ├── housing.rehabilitation.{roof,facade,foundation,systems}
│   ├── housing.new.{single_family,multi_family,accessory_dwelling}
│   ├── infrastructure.road.{new,resurfacing,bridge}
│   └── infrastructure.utilities.{water,sewer,electric,gas,fiber}
├── Land Use & Environment
│   ├── landuse.zoning.{change,variance,subdivision}
│   ├── environment.remediation.{soil,groundwater,asbestos,lead}
│   └── environment.conservation.{easement,restoration}
├── Commercial & Economic
│   ├── commercial.retail.{new,expansion,change_of_use}
│   ├── commercial.food.{restaurant,food_truck,mobile_vendor}
│   └── commercial.industrial.{manufacturing,warehouse}
├── Civic & Community
│   ├── civic.event.{public_assembly,parade,block_party}
│   ├── civic.institution.{school,library,place_of_worship}
│   └── civic.transportation.{transit_stop,bike_lane,sidewalk}
└── Other
    └── other.{unspecified,see_description}
```

Each leaf carries `(code, humanReadableName, typicalReviewPath,
estimatedReviewDays, sourceCitation, deprecatedAfter)`. The contract
only requires `code`; the rest is enrichment for the harvester and
municipal reviewer.

### 4.7 What does NOT appear in the citizen contract

Because the federal catalogue is now purely a vocabulary source, the
following fields are **explicitly absent** from `ProposedAction`:

- ~~`nepa.catexStatus`~~
- ~~`nepa.citation`~~
- ~~`nepa.agency`~~
- Any field starting with `nepa.*`
- Any field that could be read as a *federal regulatory status*

The contract is municipal from edge to edge. Federal review is the
municipal reviewer's downstream problem; the geocontract pipeline
does not encode it.

---

## 5. Alternatives analysis

Every tool selection below includes 2–4 candidates with the same
dimensions: **fit / risk / maturity / cost**. Each cell carries a
grade on a 1–5 scale, and a brief justification.

### 5.1 Smart-contract platform for the approval registry

The registry is the ledger that mints an *approval code* for each
submitted citizen contract. It is **write-once, read-many**, public,
append-only. The requirements are:

- Cheapest possible cost per submission (citizens pay gas).
- Strong read-tooling (indexers, GraphQL endpoints).
- Mature smart-contract languages.
- No MEV exposure on the approval function (must be deterministic and
  front-running resistant).

| Platform              | Fit | Maturity | Cost   | Indexing | Verdict |
|-----------------------|----:|---------:|-------:|---------:|---------|
| Ethereum L1           |  4  |  5       |  1 ($$$)| 5        | Rejected: gas prohibitive for sub-$10 submissions. |
| EVM L2 (Base, Optimism)| 4  |  4       |  4 ($) | 4        | **Strong candidate.** Cheap, mature, EVM toolchain. |
| Polygon PoS           |  4  |  3       |  4 ($) | 3        | Acceptable; centralization concerns. |
| Solana                |  5  |  4       |  5 (¢) | 4        | **Strong candidate.** Cheapest, fast; SDF tooling strong. |
| Sui                   |  5  |  3       |  5 (¢) | 3        | Strong technically (object model fits approval-registry); ecosystem younger. |
| Aptos                 |  4  |  3       |  5 (¢) | 3        | Similar to Sui; ecosystem smaller. |
| Bitcoin (OP_RETURN)   |  3  |  5       |  3     | 2        | Rejected: limited scripting, poor query. |
| Filecoin / IPFS only  |  2  |  4       |  5 (¢) | 3        | **Storage only**, not a registry. Pair with one of the above. |
| Ceramic / ComposeDB  |  4  |  2       |  4     | 4        | **Strong candidate** for off-chain registry with on-chain anchor. |

> **Recommended:** A **two-layer** design:
> 1. **Off-chain registry** — Ceramic ComposeDB (or Tableland /
>    Postgres+IPFS) for the rich contract document with full-text
>    search, GraphQL, and row-level updates.
> 2. **On-chain anchor** — an EVM L2 (Base) or Solana program that
>    stores only the `sha256(canonical_yaml) → approvalCode` mapping,
>    plus a timestamp. Cost per anchor ≈ $0.001–$0.01.

This **separates concerns** and gives us best-of-breed: cheap reads
(Ceramic ComposeDB GraphQL), strong immutability (chain anchor),
low cost (L2).

### 5.2 Token standard for project fundraising

Each approved project can have its own coin. Requirements:

- Per-project issuance (one coin per contract, not a shared platform
  coin).
- Mint to a multisig the project owner controls.
- Tradable on DEXes after launch (optional).
- Compliant with US securities where possible — see §5.2.1.

| Standard                  | Platform   | Verdict |
|---------------------------|------------|---------|
| ERC-20 (fixed supply)     | EVM        | **Strong.** Most DEXes support it. |
| ERC-20 (mintable)         | EVM        | Strong if mint authority is renounced or multisig'd. |
| ERC-4626 (vault)          | EVM        | Specialized for yield-bearing; not needed here. |
| SPL Token                 | Solana     | Strong if Solana chosen. |
| SUI Coin (Coin<T>)        | Sui        | Strong if Sui chosen; mature. |
| Regulated / Permissioned  | EVM (ERC-1404, ERC-3643) | **Strong if securities compliance is needed.** |
| Bond-style (Olympus-style)| EVM        | Rejected — too complex for citizen use. |

#### 5.2.1 Securities-law note

A per-project coin sold to US residents in exchange for value is, in
most cases, a **security** and falls under SEC regulation. Two
practical paths:

1. **Reg D 506(c)** — accredited investors only; file Form D; no
   general solicitation. Token is freely tradable among accredited
   holders.
2. **Reg A+ (mini-IPO)** — up to $75M / 12 mo; non-accredited
   permitted; expensive and slow (~$75k filing).
3. **Utility-only framing** — token grants access to project outputs
   (e.g. a community garden plot, a coworking day-pass) rather than
   equity / profit-share. *Much* easier legally but constrains
   fundraising shape.

> **Steering question Q2:** Which compliance posture does the user
> want? Plan defaults to **utility-only** with a recommendation note
> to consult counsel before any equity-style launch.

### 5.3 Identity / residency-proof for the citizen claim

The `citizenClaimantAddress` and `residencyProofUri` need a real-world
identity binding. Options:

| Approach                                    | Verdict |
|--------------------------------------------|---------|
| Email + utility-bill upload (manual KYC)    | Strong baseline; slow. |
| Civic Pass / ID.me / Plaid ID-verification | Strong; SaaS cost. |
| W3C Verifiable Credentials (utility-issued)| **Strong.** Privacy-preserving, reusable. |
| zkPassport / Privado ID                     | Strong for residency, weak for address binding. |
| Worldcoin / Proof of Personhood             | Too coarse; doesn't prove *municipal residency*. |
| Self-sovereign ENS / did:pkh                | Rejected — proves wallet control, not residency. |

> **Recommended:** **W3C VC issued by the municipal clerk** (e.g.
> Groton Town Clerk signs a credential that says
> *"this wallet address controls a credential of a person residing
> at <parcel>"*). Reusable across projects, privacy-preserving,
> revocable.

### 5.4 Storage of the canonical YAML

| Option                            | Verdict |
|-----------------------------------|---------|
| GitHub (per project repo)         | **Strong.** Free, audit-trail via commits, signed. |
| IPFS + Pinata                     | Strong for censorship-resistance. |
| Ceramic ComposeDB                 | Tied to §5.1. |
| AWS S3 / GCS                      | Strong for harvester but vendor lock-in. |
| Local file                        | Strong for the local harvester test path. |

> **Recommended:** **GitHub as primary**, **IPFS as mirror**, hash
> anchored on chain. Existing `geocontract-harvest` already supports
> both (`https://github.com/...` and `s3://...` in §docs/design-harvester.md).

### 5.5 Form UX (future)

The deliverable here is the **schema**, not the form. But the
alternatives analysis for future form work:

| Tool          | Verdict |
|---------------|---------|
| Static HTML + json-schema-form | **Strong.** No backend, schema-driven. |
| React + react-jsonschema-form  | Strong for richer UX. |
| SurveyJS / Typeform            | Rejected — vendor lock-in, weak schema export. |
| Docassemble (guided interview)| **Strong** for legal/permits UX; open source. |

### 5.6 Metrics for grading the alternatives

For each tool selection above we score on:

- **Fit** (1–5): how well it matches requirements
- **Maturity** (1–5): ecosystem, audit history
- **Cost** (1–5): inverse scale — 5 = cheapest
- **Risk** (1–5): 5 = lowest regulatory/security risk

Recommended choices have a mean ≥ 4.0 across all four. The §11
**Steering questions** include asking the user to either accept the
recommendation or rerun with weighted priorities.

---

## 6. End-to-end flow (citizen → approval code → token)

```
1. CITIZEN FILLS FORM
   groton-pha.org/permit/new
   fields: parcel, activityCode, description, cost, optional funding goal
   ──▶ validates against MinimalProposedAction JSON Schema
   ──▶ produces canonical YAML  contracts/<id>.geocontract.yaml

2. CITIZEN SIGNS
   wallet signs EIP-191 / Ed25519 message:
     sha256(canonical_yaml_bytes)
   ──▶ citizenClaim.signature populated

3. ANCHOR ON CHAIN
   AnchorRegistry.submit(hash, parcelId, activityCode)
   ──▶ tx emits  ApprovalCodeCreated(hash, code, timestamp, chainId)
   ──▶ approval code = first 8 bytes of keccak256(hash || chainId || nonce)

4. STORE OFF-CHAIN
   canonical_yaml pinned to IPFS → CID returned
   CID stored as cidApprovalMap in ComposeDB row keyed by hash
   ──▶ yields  records.jsonl  via geocontract-harvest

5. (OPTIONAL) ISSUE PROJECT TOKEN
   ProjectTokenFactory.deploy(symbol, raiseTarget, multisig)
   ──▶ returns ERC-20 / SPL token address
   ──▶ token address stored in contract.fundingGoal.tokenAddress

6. HARVESTER PICKUP
   geocontract-harvest discovers contracts/<id>.geocontract.yaml
   (or the IPFS mirror, or the ComposeDB row)
   ──▶ validates against ODCS v3.1.0
   ──▶ emits { ..., "schema_hash":"sha256:...",
              "approval_code":"0xABCDEF...",
              "chain_id":8453,
              "token_address":"0x..." }  → records.jsonl
```

The harvester output schema in `docs/design-harvester.md` §"Output
schema" needs **two new fields** on the per-entity JSONL record:

| Field            | Required | Example                         |
|-----------------|----------|---------------------------------|
| `approval_code` | yes if anchored | `0xABCDEF…`               |
| `chain_id`      | yes if anchored | `8453` (Base)              |
| `token_address` | no       | `0x1234…` (if fundraising on)   |

This is a strictly additive change to the harvest output and does not
break existing pipelines.

---

## 7. Compatibility with existing geocontract machinery

| Existing piece                                 | Impact of citizen flow |
|------------------------------------------------|------------------------|
| `templates/*.template.schema.json`             | Add `templates/proposed-action.template.schema.json` (new file, no change to existing). |
| `contracts/*.datacontract.yaml`               | Add `contracts/groton-rhine-001.datacontract.yaml` as first instance. |
| `contracts/shim/*.datacontract-shim.json`     | Add a matching shim; pattern identical to `nepa-exclusions`. |
| `models/*.canonical.graphql`                  | Regenerate; new type `ProposedAction`, `Parcel`, `FundingGoal`, `CitizenClaim`. |
| `external/geocontract-master.schema.json`     | No change — `embeddedSchemas` extension already supports any nested schema. |
| `scripts/validate_odcs.py`                    | No change — same `--master` mode works. |
| `scripts/generate_graphql.sh`                 | Add `proposed-action` to the jxql loop. |
| `docs/design-harvester.md`                    | Add a §"Citizen-initiated sources" subsection; new fields on JSONL output. |
| `mise.toml`, `prek.toml`, `dprint.json`       | No change. |

**Zero breaking changes** to the existing repo.

---

## 8. Phasing

### Phase A — Design (this document, no code yet)

- Finalize §4 ontology.
- Resolve §11 steering questions with the user.
- File any new upstream jxql issues that the new template surfaces
  (likely: more `x-graphql-field-type` overrides for
  `["null","object"]` unions — see jxql #237).

### Phase B — Schema + example (no smart contracts yet)

- `templates/proposed-action.template.schema.json` (new).
- `contracts/odcs-v3.1.0-template.yaml` extended with a
  `ProposedAction` schema block.
- `contracts/groton-rhine-001.datacontract.yaml` (worked example).
- `examples/groton-rhine-001.example.data.json`.
- Regenerate `models/proposed-action.canonical.graphql` via jxql.
- Extend `docs/design-harvester.md` JSONL output spec.
- One PR. **No chain code in this PR.**

### Phase C — Ledger integration (separate repo recommended)

A second repo, e.g. `geocontract-anchor`, holds:

- AnchorRegistry contract (Solidity for EVM L2, or native Rust for
  Solana).
- ProjectTokenFactory contract.
- Deployment scripts.
- An "anchor & issue" CLI (`geocontract-anchor submit <yaml>`).
- Integration tests against Base / Solana devnet.

Rationale for separate repo: keeps the **schema-first** repo small,
avoids dragging chain tooling into the geocontract validator path,
and lets the smart-contract code iterate faster with its own audit
trail.

### Phase D — Form UI (future, separate repo)

- Static site using Docassemble or json-schema-form.
- Deploy to `groton-pha.org/permit/new` or similar.
- Out of scope for the geocontract repo.

### Phase E — Harvester citizen-source support

- Extend `geocontract-harvest` to read from ComposeDB / on-chain
  anchor events as a new source kind.
- Add `--chain-rpc <url>` and `--anchor-registry <addr>` flags.
- Wire the new JSONL fields (`approval_code`, `chain_id`,
  `token_address`) through the normaliser.

### Phase F — Pilot

- 1 municipal partner (Groton Housing Authority, working example).
- 5–10 citizen proposals.
- Capture metrics: time-to-approval, gas cost, fundraised amount,
  rejections, resubmissions.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Securities-law violation on token sale | Medium | Severe | Default to utility-only framing; explicit disclaimer in template; counsel review before Phase C ships. |
| Bad actor submits fake residency proofs | Medium | Medium | W3C VC must be signed by a trusted municipal issuer; revocation list checked on anchor. |
| Chain reorg invalidates approval code | Low | Medium | Require ≥ 64 block confirmations on L2; record timestamp + block hash in the ComposeDB row. |
| CATEX catalogue ambiguity in ontology mapping | Medium | Low | Surface `sourceCitation` provenance on every leaf; hand-curated cluster centroids; periodic re-scan. |
| Municipal clerk unwilling to sign VC issuer | Medium | High | Defer to utility-bill upload as fallback identity proof (slower, manual). |
| Gas cost spikes crowd out low-income filers | Medium | Medium | Subsidy pool from PIC / municipal partners; gasless meta-tx via ERC-2771 forwarder. |
| Harvester over-fetches on-chain events | Low | Low | Rate-limited RPC; cache CTAs; per-source TTL. |
| Activity ontology drift between agencies | High | Medium | Versioned (`ActivityOntology/v1.2`), all leaves carry a `deprecatedAfter` field. |

---

## 10. Success metrics

| Metric | Target |
|--------|--------|
| Time-to-approval-code (median) | < 5 min |
| Cost per anchor (median) | < $0.05 |
| Contracts passing `mise run validate-odcs` | 100% |
| Schema coverage: % of CATEX corpus rows mapped to activity ontology leaves | > 90% |
| Citizen submissions / pilot month | > 25 |
| Token issuances / pilot | > 3 |
| Harvester citizen-source success rate | > 95% (5xx excluded) |

---

## 11. Steering questions (please answer before Phase B)

The plan above is built on **inferred** defaults because `gh` auth is
currently broken and the corpus scan could not run. Before any code is
written, the user should resolve:

- **Q1 — Starred projects corpus.**
  ✅ Resolved. The corpus has been enumerated and §4.4 has been
  updated with the actual repos grouped by relevance. The
  corpus-derived bucket list in §4.4.1 should be folded into the
  ontology ingestion pipeline during Phase B.

- **Q2 — Compliance posture for the token.**
  Default plan: **utility-only** (token grants access, not equity).
  Alternative: **Reg D 506(c)** (accredited only). Alternative:
  **Reg A+** (full mini-IPO). Which? Any answer other than
  utility-only requires counsel sign-off before Phase C.

- **Q3 — Chain choice.**
  Default plan: **EVM L2 (Base) for the anchor + ComposeDB for the
  rich registry.** Alternative: **Solana native** (cheaper, slightly
  less mature tooling). Alternative: **Sui**. Confirm or rerank.

- **Q4 — Identity provider for residency proof.**
  Default: **W3C VC issued by the municipal clerk**. Fallback:
  **utility-bill upload (manual KYC)**. Other?

- **Q5 — Worked example scope.**
  The Groton Housing Authority + Rhine St. façade repair example is
  illustrative. Do you want:
  (a) keep it as a **fictional** worked example in the docs only, or
  (b) reach out to Groton Housing Authority to make it a real pilot
      (Phase F), or
  (c) pick a different partner / parcel for the worked example?

- **Q6 — Token issuance: one coin per project, or shared platform coin?**
  Default: **one coin per project** (ERC-20 deploy-per-contract).
  Shared platform coin simplifies UX but adds securities exposure
  (Howey test more clearly met).

- **Q7 — Acceptable gas-cost ceiling for citizen submissions.**
  Default: **subsidise up to $1 per anchor from a public-pool
  multisig**. Acceptable? Or require citizen to pay?

- **Q8 — Should Phase C live in `geocontract` or a sibling repo
  `geocontract-anchor`?**
  Default: sibling repo (cleaner separation; geocontract stays
  schema-first).

- **Q9 — Are there state / municipal regulations we should
  pre-emptively add to the contract's `description.limitations`?**
  (E.g. Connecticut General Statutes citations for housing
  authority actions.) Federal regulations are intentionally out of
  scope per §1.1 — the citizen flow is municipal from edge to edge.

- **Q10 — Does the existing `geocontract-harvest` design need any
  changes for the citizen flow, or is the additive JSONL fields in
  §6 sufficient?**
  Default: additive fields only, no design changes.

Once these are resolved, Phase B (schema + worked example) can
begin in a single PR.

---

## 12. Open follow-ups (after Phase B)

- File new jxql upstream issues for any quirks encountered.
- Write a `metrics-report.md` summarising the alternatives analysis
  grading (§5.6) with actual scored values, publish in `docs/`.
- Update `README.md` with a "Citizen-initiated flow" subsection
  linking to this plan.
- Consider adding the new `ProposedAction` GraphQL types to the
  `models/` directory in the same PR as Phase B.
- Add `mise run check-ontology-coverage` task that diffs the
  CATEX catalogue leaves against the activity ontology and reports
  unmapped codes.