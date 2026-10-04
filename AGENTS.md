<!-- ops-sync:begin — synced from portolan-sdi/portolan-ops. Edit there, not here. -->
# Portolan agent norms

These rules apply to AI agents working in any portolan-sdi repo. Every downstream repo repeats this text verbatim as a synced block at the top of its own `AGENTS.md`. Repo-specific instructions live below the block and override the canonical rules in that repo only.

Claude Code does not read `AGENTS.md`. Each repo has a one-line `CLAUDE.md` that imports it instead. Put repo-specific instructions in `AGENTS.md`, never in `CLAUDE.md`, which the sync overwrites.

## Ground rules

The [portolan-spec](https://github.com/portolan-sdi/portolan-spec) repo is ground truth for the Portolan specification. The CLI, `rashid`, the registry, and every other tool implement the specification. They are downstream of it. Never describe the CLI as the source of truth. Propose spec changes in portolan-spec.

Before documenting any command, flag, or API, verify it exists in the released tool. A fabricated example persists beyond the session that wrote it.

Every repo uses Apache-2.0 except portolan-browser and portolan-nl-demo, which are ISC forks. See [norms/repos.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/repos.md) for the record. Never introduce code under another license without a human decision recorded there.

Never bypass pre-commit hooks or CI gates. Green means green.

Write commits in conventional form. Squash-merge makes the pull request title become the commit message.

## Pull requests and issues

Write every issue and pull request in two layers. The human layer first states what is wrong or missing. It explains why the problem matters and what should happen instead. Someone who did not follow your investigation should understand it in about a minute. The agent layer then provides evidence and implementation detail. It also records constraints, edge cases, and verification.

There is no word limit. A 700-word issue is good when its first 150 words make the outcome obvious. A 150-word issue is bad when it compresses the meaning into prose the reader has to unpack. Optimize for fast comprehension, not for short tickets.

Write them in Simplified Technical English (ASD-STE100). The rules are an output style, `.claude/output-styles/simplified-technical-english.md`, which every repo receives. A hook prints it at session start. Sentences run under 20 words and express one idea. Use the active voice, and use only the infinitive, the imperative, and simple tenses. Use a verb rather than a noun made from a verb. Keep the technical content exactly as precise as it was, and simplify only the language around it. Describe the design as it stands now rather than the approaches you discarded.

The structural contract CI enforces on a pull request:

- The sections `## What changed`, `## Why`, and `## Verification` exist and are not empty.
- The prose references the issue the change resolves, as `#N` or its URL.
- Verification pastes the command you ran and its output in a fenced block under `## Verification`. It identifies the data it read, as a URL or catalog path.
- A change that alters no behavior ticks the waiver checkbox instead. Keep its wording intact because the check matches the phrase "does not alter behavior".

Good evidence shows the fix works against real data. Proving a command exits zero is not enough. Take the failing command from the issue, run it against the same catalog, and show it now succeeds. A wall of pytest output does not count.

Issues follow the same shape. A bug report shows the failure and identifies the data. Write a feature request to show what the current tool cannot do, or what the workaround costs. A task states the outcome and the command that proves it is done.

Each repo uses the org issue template. The language itself is checked before a body is ever filed: `.claude/hooks/writing_check.py` runs on `gh issue create` and `gh pr create`, and reports the specific problems it found. Run `writing_check.py --print-rules` to read the rules. When it is wrong about a line, say so in the body with `<!-- ste-ok: RULE_ID why this is correct -->`. Dependabot is exempt from the CI check.

That check matches words and punctuation, but cannot assess tone or padding. It also cannot assess prose that argues for its own value. Passing proves nothing about how the body reads. Read what you wrote before you file it. Cut sentences that only make the change sound good.

## Documentation

Agents writing or restructuring documentation follow two exemplars named in [norms/docs.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/docs.md). [obstore](https://github.com/developmentseed/obstore) demonstrates a concise, human-readable README that delegates to good docs elsewhere. [scaffold-docs-skill](https://github.com/dbreunig/scaffold-docs-skill) shows how to build docs that have a clear human-facing surface, maintain examples via tests so they never drift, and auto-generate API docs instead of duplicating them. Both make documentation easy to maintain and easy to update. Draft top-down with human review between layers. Do not draft a README from a generic template or from memory.

These rules apply to every docs change. Use sentence-case headings without emoji. Use absolute dates like "in July 2026", never "recently". Run every command example against the released tool before you publish it.

## Voice and messaging

Every written artifact follows the prose rules in [norms/prose.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/prose.md). Vale checks Markdown and website copy. The writing hook checks the prose in issues and pull requests. Apply the rules while drafting, not as cleanup.

Before drafting substantial public copy like a README, a docs page, or an announcement, fetch and read [norms/prose.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/prose.md) and [copy/messaging.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/copy/messaging.md) in full. If you cannot fetch them, say so and stop. Write from the actual files, not from memory.

How Portolan is described comes from [copy/messaging.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/copy/messaging.md) alone.

## Org-wide facts

The canonical homepage is https://www.portolan-sdi.org/. Canonical URLs live in [copy/urls.md](https://github.com/portolan-sdi/portolan-ops/blob/main/norms/copy/urls.md). Do not hardcode variants.

Community discussion happens in the [Portolan Google Group](https://groups.google.com/g/portolan) and the [Portolan channel](https://cloudnativegeo.slack.com/archives/C0A1JBH9529) in Cloud-Native Geo Slack. Planning happens in [org-level GitHub projects](https://github.com/orgs/portolan-sdi/projects/1).

## Contribution rules

The [AI policy](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/AI_POLICY.md) applies to every contribution. An agent may draft the diff and the pull request body. A human must read, understand, and approve both before review is requested. Agents never open PRs, post comments, or take action in shared spaces without human approval.

Follow the [contributing guide](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/CONTRIBUTING.md) and the [code of conduct](https://github.com/portolan-sdi/portolan-ops/blob/main/policies/CODE_OF_CONDUCT.md).

## Sync discipline

Files between `ops-sync` markers are synced from [portolan-ops](https://github.com/portolan-sdi/portolan-ops). They are overwritten on every sync run. To change one, edit it in portolan-ops, never in place.

One canonical home per fact. If a value like a color, URL, or policy line exists in portolan-ops, link to it rather than copying it.
<!-- ops-sync:end -->

## geocontract repo rules

These rules apply in this repo only. They override the block above where
they differ.

### This repo is not a portolan-sdi repo

geocontract lives at [JJediny/geocontract](https://github.com/JJediny/geocontract).
It adopts the Portolan specification for its catalog. It is not a member of
the portolan-sdi organisation, so the `ops-sync` block above is copied for
agent consistency rather than received by an automated sync. No sync job
overwrites it here. A human must update it by hand.

### License

This repo is **CC0-1.0**, as declared in `pyproject.toml` and `LICENSE`.
The Apache-2.0 rule in the synced block does not apply here. Do not
relicense any file in this repo without a recorded human decision.

Catalog `license` values describe the **data** each collection publishes,
not the code in this repo. Those values live in
`catalog/manifests/geocontract.yaml`.

### Two sources of truth, no overlap

The ODCS contract carries semantics. The catalog manifest carries catalog
facts. Never state one fact in both places.

| Fact | Home |
| --- | --- |
| Contract id, name, description, schema, tags, tenant, servers | `contracts/*.datacontract.yaml` |
| License, bbox, host provider, `via` page, keywords, nested-catalog titles | `catalog/manifests/geocontract.yaml` |

ODCS sets `additionalProperties: false` and has no `license` field. So a
catalog fact added to a contract YAML fails `mise run validate-odcs`.
See `docs/portolan-conformance-notes.md` §F7.

### Generated files

`catalog/**/collection.json` and `catalog/**/catalog.json` are generated.
Edit the contract or the manifest, then run `mise run catalog-build`.
Never hand-edit generated JSON. The same rule already applies to
`models/*.canonical.graphql`, which `mise run generate-graphql` produces.

`README.md` and `AGENTS.md` inside `catalog/` are curated. The generator
seeds them once and then leaves them alone.

### Data never enters git

The published `data`-role assets are Parquet, GeoParquet, or COG files.
They live in the object store, never in this repo. `external/exclusions.json`
is a vendored development fixture and stays out of the catalog tree.

### Validation gates

Both validators must pass before a commit:

```bash
mise run validate-odcs    # ODCS v3.1.0, the contract side
mise run catalog-check    # rashid, the catalog side
```

Never widen an `ACCEPTED` allow-list to make CI green. An accepted finding
needs a row in `docs/portolan-conformance.md` plus a tracking issue, or
neither.

### Skills

`portolan-skills/` is a git submodule. Use its skills rather than
re-deriving their workflows:

| Task | Skill |
| --- | --- |
| Edit and publish the catalog | `skills/git-backed-catalog/` (Mode B) |
| Portolan-ify a new source | `skills/portolan-bootstrap/` |
| Command reference | `skills/portolan-cli/` |
| Bump the pinned spec version | `skills/portolan-migrate/` |
| Publish to Source Cooperative | `skills/sourcecoop/` |
| Register the catalog | `skills/register-catalog/` |
| Report a problem in another catalog | `skills/report-catalog-issue/` |
| Consume a catalog | `skills/reading-portolan/` |

Read `docs/plan-portolan-catalog-integration.md` §14 for the phase-to-skill
map.

### Pull requests in this repo

Follow the synced block: `## What changed`, `## Why`, `## Verification`,
conventional commit titles, Simplified Technical English. Paste real command
output under `## Verification`. An agent prepares the branch and the body.
A human pushes and opens the pull request.

## Publishing the catalog

The catalog is published to the destination configured in `catalog.publish.yaml`.
The publish script validates the catalog with `rashid` before publishing and
never deletes files from the destination.

### Publish workflow

```bash
# Dry run: see what would be published
mise run publish

# Actually publish (needs credentials for S3)
mise run publish-confirm
```

### Publishing rules

- **Validate first.** The publish script runs `rashid check` before uploading.
  Fix errors before publishing.
- **Never delete manually.** Removing a file from `catalog/` does not remove it
  from the destination. Delete objects separately when intended.
- **Change detection.** Files are uploaded only if size or checksum differs.
  Use `--force` after changing content type (the bucket listing omits
  Content-Type).
- **Relative links in git, absolute in published.** Keep structural links
  relative in the tracked tree. The published root gets an absolute `self` link.
- **Data files don't belong in git.** Build them, upload with a data upload
  script, and reference them by public URL in the STAC.

### Configuration

Edit `catalog.publish.yaml` to set:
- `destination`: Where to publish (file:// for testing, s3:// for production)
- `public_base`: Public URL where the catalog is accessible
- `region`: AWS region (for S3 destinations)
- `profile`: AWS credentials profile (optional)

Before first publish, update the TODO placeholders in `catalog.publish.yaml`.

### CI integration

The CI workflow runs `mise run publish` as a dry-run on every PR and push.
This validates the catalog and checks that the publish script works, without
actually uploading. Use `mise run publish-confirm` to publish to production.
