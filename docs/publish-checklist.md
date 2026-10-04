# Publish checklist

> Spec baseline: `portolan-spec` @ v0.2.0
> Tools: `portolan` 0.8.0, `rashid` 0.1.8, `tools/publish.py`
> Status: Phases 0–4 complete. Publishing is wired through `mise run publish`
> but never run against a real destination; this checklist tracks the
> remaining manual work before the catalog can be registered in the
> portolan-sdi registry.

This checklist walks every step required to take `catalog/` from a
generated-but-unpublished tree to a live URL that the portolan-sdi
registry can pin. It mirrors the §11 item 1 in
`docs/plan-portolan-catalog-integration.md`.

The doc has four sections, in order. Do not skip sections.

---

## 1. Configure `catalog.publish.yaml`

`tools/publish.py` reads `catalog.publish.yaml` from the repo root. Two
fields must be filled before the first publish; both are flagged `TODO`
in the checked-in file.

### 1.1 Pick a destination

The supported schemes are `file://` (local directory, for testing) and
`s3://` (any S3-compatible store). For a registry-pinnable URL the
destination must be reachable from the open internet. Recommended:

```yaml
destination: s3://geocontract-data/catalog/
```

A non-default bucket or prefix is fine. The bucket must allow
public-readable objects (or sit behind a CloudFront distribution that
does); `tools/publish.py` does not configure bucket policies.

### 1.2 Pick the public base URL

This is the URL consumers (and `rashid check --live`) will fetch from.
It must agree byte-for-byte with the destination prefix:

```yaml
public_base: https://catalog.geocontract.org/catalog/
```

The first segment after `public_base` matches the S3 prefix. If the
destination is `s3://bucket/prefix/`, the public URL is
`https://<cdn>/prefix/`. A mismatch makes the `self` link on the root
catalog (PORTO-CORE-081) unreachable.

### 1.3 AWS region and credentials

`tools/publish.py` uses `boto3` for `s3://`. For GitHub Actions
workflows, set the region and let the workflow's OIDC role supply
credentials:

```yaml
region: us-east-1
# profile: default    # only when running outside an OIDC context
```

Local `mise run publish-confirm` with an `s3://` destination needs
credentials too. `aws sso login` then `unset AWS_PROFILE` works.

---

## 2. Run the pre-publish gates

These run locally without credentials. They must pass before any
publish, dry-run or otherwise.

```bash
# All gates the CI runs, locally
mise run:ci

# Equivalent to `ci` but skips the parallel-portolan-calibrate sanity
# check. Faster on the laptop.
mise run drift-check
mise run validate-odcs
mise run datacontract-lint
mise run fmt-check
mise run test
mise run pipeline-test
mise run catalog-check
mise run dcat-check
mise run datacite-check
```

Expected: `0 error(s), 0 warning(s)`, 191 pytest tests, and the same
information ceiling every PR sees (5 `PTL-PRO-002` findings on the
current manifest: 2 federal mirrors + 3 harvested mirrors, until PR #26
adds `upstream_stac` plumbing).

Then a clean publish dry-run:

```bash
mise run publish
```

Expected: the script lists every file it WOULD upload, in deterministic
order, with size and checksum. No upload happens. If anything here
errors, fix it before touching the real destination.

---

## 3. Publish

```bash
# First time only — confirm the destination is reachable and writeable
mise run publish-confirm --dry-run   # if the flag exists; otherwise
aws s3 ls s3://your-bucket/your-prefix/

# Real publish
mise run publish-confirm
```

`publish-confirm` runs `rashid check` on the generated tree immediately
before upload. It never deletes objects on the destination (use the S3
console or `aws s3 rm` when intended). Re-running on the same tree is a
no-op: the script compares size + checksum and skips matches.

If the first publish introduces new `Content-Type` metadata, force the
upload so the bucket listing picks it up:

```bash
mise run publish-confirm -- --force
```

---

## 4. Validate the published URL

Open the public base URL in a browser. `catalog.json` should fetch and
parse. The `self` link on the root (PORTO-CORE-081) must match the
public base.

Then run rashid in live mode against the published URL:

```bash
uvx --from 'rashid>=0.1.8,<0.2.0' \
  rashid check https://catalog.geocontract.org/catalog/ --summary
```

Expected: `0 error(s), 0 warning(s)`, the same 5 informational findings
the local run reports, plus any `--data` check warnings the script
chooses to surface. A live-data pass fetches every asset's href; expect
it to take a few minutes on a cold cache.

---

## 5. Submit to the portolan-sdi registry

This is the step that turns the published catalog into a registry entry.
Use the `register-catalog` skill in `portolan-skills/`:

```bash
# Inside portolan-skills/, follow the skill's flow:
#   1. Fork portolan-sdi/registry
#   2. Add catalogs/<slug>.yaml with:
#        url: https://catalog.geocontract.org/catalog/catalog.json
#        submitter_email: <your-email>
#   3. Open the PR; CI runs `rashid check --live` against the URL
```

Two fields are required: `url` (the `catalog.json` root, not the
prefix) and `submitter_email`. The submitter email is a maintainer
contact, not a public address — it goes into the registry's contact
list and is used by portolan-sdi for catalog-health notifications.

The PR is gated on `rashid check --live` passing against the published
URL. Until the catalog is reachable, the registry PR will fail.

---

## Open follow-ups

These three items block first-publish and must be answered by a human
with credentials and authority, not by an agent:

1. **`catalog.publish.yaml`** — destination bucket and public base URL.
   Pick a destination that allows public reads; commit the YAML.
2. **Submitter email** — a maintainer address for the registry entry.
   Goes into the portolan-sdi registry only; not published in the
   catalog itself.
3. **Bucket policy** — `tools/publish.py` does not configure the
   bucket. Whoever owns the bucket must set it to allow public reads on
   the catalog prefix, or front it with a CDN that does.

Until all three are resolved, this checklist stops at §4. The §5 PR is
mechanical once §1 and §4 are green.