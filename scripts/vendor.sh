#!/usr/bin/env bash
# vendor.sh — install local development binaries into .tools/
#
# Idempotent: re-running skips installs that are already present and
# up-to-date.
#
# What this installs:
#   * jxql         — Rust CLI from ../json-schema-x-graphql (release build)
#   * datacontract — Python CLI from PyPI, via `uv tool install`
#   * dprint       — Node CLI from npm, via pnpm dlx cache
#
# Each binary is downloaded once and stashed under .tools/<bin>/<version>/.
# Add .tools/bin to your PATH or call via `mise run vendor-jxql` which
# exports it for the current shell.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOLS_DIR="${ROOT}/.tools"
BIN_DIR="${TOOLS_DIR}/bin"
mkdir -p "${BIN_DIR}"

JXQL_REPO="${JXQL_REPO:-../json-schema-x-graphql}"
# Pinned to commit 69100a1229a7823f242b637a81ab58a847394a3d, the
# merge of PR #264 on json-schema-x-graphql main on 4 October 2026.
# PR #264 fixed four classes of bug that affected our generated
# GraphQL SDL: nullability unions collapsing to JSON; root-level
# x-graphql-enums registry definitions silently dropped; lenient
# root pointers ($ref: "/", $ref: "") rendering as bogus
# `Externalplace`; and explicit x-graphql-type-name values being
# PascalCase-mangled into different names. The tag `v2.0.2` predates
# all four fixes; when a new tag cuts on main, replace this SHA
# with it. Until then the SHA is the only stable ref for the fixes.
JXQL_VERSION="${JXQL_VERSION:-0.4.0}"
DATACONTRACT_VERSION="${DATACONTRACT_VERSION:-0.10.21}"
DPRINT_VERSION="${DPRINT_VERSION:-0.47.5}"

log() { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ── 1. jxql (Rust) ───────────────────────────────────────────────────────────
install_jxql() {
  local dest="${BIN_DIR}/jxql"
  if [[ -x "${dest}" ]]; then
    ok "jxql already installed at ${dest}"
    "${dest}" --version || true
    return
  fi

  if [[ -d "${JXQL_REPO}" ]] && command -v cargo >/dev/null 2>&1; then
    log "Building jxql from local checkout (${JXQL_REPO})…"
    (
      cd "${JXQL_REPO}"
      cargo build --release --bin jxql --features cli
    )
    cp "${JXQL_REPO}/target/release/jxql" "${dest}"
    chmod +x "${dest}"
    ok "Built jxql from local checkout → ${dest}"
    return
  fi

  # No local checkout (e.g. CI runner). Clone at the recorded git ref
  # (default: pinned commit SHA) into a build scratch dir, build with
  # cargo, and stash the binary. This is the path CI takes; local dev
  # can keep using the sibling checkout. A 40-char SHA does not work
  # with `git clone --branch`, so we detect that case and use a full
  # clone + checkout instead.
  if command -v cargo >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
    local build_dir="${TOOLS_DIR}/jxql-src"
    local jxql_ref="${JXQL_GIT_REF:-69100a1229a7823f242b637a81ab58a847394a3d}"
    local jxql_url="${JXQL_GIT_URL:-https://github.com/json-schema-x-graphql/json-schema-x-graphql.git}"
    log "Cloning json-schema-x-graphql @ ${jxql_ref} and building jxql…"
    if [[ ! -d "${build_dir}" ]]; then
      if [[ "${jxql_ref}" =~ ^[0-9a-f]{40}$ ]]; then
        git clone "${jxql_url}" "${build_dir}"
        (cd "${build_dir}" && git checkout "${jxql_ref}")
      else
        git clone --depth 1 --branch "${jxql_ref}" "${jxql_url}" "${build_dir}"
      fi
    fi
    (
      cd "${build_dir}"
      cargo build --release --bin jxql --features cli
    )
    cp "${build_dir}/target/release/jxql" "${dest}"
    chmod +x "${dest}"
    ok "Built jxql from ${jxql_url} @ ${jxql_ref} → ${dest}"
    return
  fi

  warn "cargo and git not found; skipping jxql install"
}

# ── 2. datacontract-cli (Python) ─────────────────────────────────────────────
install_datacontract() {
  local dest="${BIN_DIR}/datacontract"
  if [[ -x "${dest}" ]]; then
    ok "datacontract already installed at ${dest}"
    return
  fi

  if command -v uv >/dev/null 2>&1; then
    log "Installing datacontract-cli v${DATACONTRACT_VERSION} via uv…"
    # uv refuses to overwrite a system tool dir; install into a private dir.
    uv tool install --python 3.13 "datacontract-cli==${DATACONTRACT_VERSION}"
    local uv_bin
    uv_bin="$(uv tool dir --bin 2>/dev/null || true)"
    if [[ -x "${uv_bin}/datacontract" ]]; then
      ln -sf "${uv_bin}/datacontract" "${dest}"
      ok "Installed datacontract → ${dest} (→ ${uv_bin}/datacontract)"
    else
      warn "uv tool dir not found; install may have failed"
    fi
    return
  fi

  warn "uv not found; skipping datacontract install"
}

# ── 3. dprint (delegated to mise) ────────────────────────────────────────────
# dprint is owned by mise (see [tools] in mise.toml: "npm:dprint" = "0.47.5").
# We create a tiny wrapper at .tools/bin/dprint that invokes the mise-managed
# binary via `mise exec`. This keeps the prek hook path resolution simple
# (just `export PATH=$PWD/.tools/bin:$PATH`) while ensuring the version in
# use is the one mise pinned.
install_dprint() {
  local dest="${BIN_DIR}/dprint"
  if [[ -x "${dest}" ]]; then
    ok "dprint wrapper already installed at ${dest}"
    return
  fi

  if ! command -v mise >/dev/null 2>&1; then
    warn "mise not found; cannot create dprint wrapper"
    return
  fi

  cat > "${dest}" <<'EOF'
#!/usr/bin/env bash
# Auto-generated by scripts/vendor.sh — delegates to the mise-managed
# dprint binary pinned in mise.toml ("npm:dprint" = "<version>").
exec mise exec -- dprint "$@"
EOF
  chmod +x "${dest}"
  ok "Installed dprint wrapper → ${dest} (delegates to mise exec dprint)"

  # Smoke-test (mise install is lazy; this is the first invocation)
  "${dest}" --version
}

main() {
  log "Vendoring geocontract dev tools into ${BIN_DIR}"
  install_jxql
  install_datacontract
  install_dprint

  echo
  ok "Done. Add to PATH with:"
  echo "    export PATH=\"${BIN_DIR}:\$PATH\""
}

main "$@"
