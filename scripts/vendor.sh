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

  if command -v cargo >/dev/null 2>&1; then
    log "Building jxql from crates.io (v${JXQL_VERSION})…"
    cargo install jxql --version "${JXQL_VERSION}" --root "${TOOLS_DIR}/cargo" --features cli
    cp "${TOOLS_DIR}/cargo/bin/jxql" "${dest}"
    chmod +x "${dest}"
    ok "Installed jxql v${JXQL_VERSION} → ${dest}"
    return
  fi

  warn "cargo not found; skipping jxql install"
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

# ── 3. dprint (Node) ─────────────────────────────────────────────────────────
install_dprint() {
  local dest="${BIN_DIR}/dprint"
  if [[ -x "${dest}" ]]; then
    ok "dprint already installed at ${dest}"
    return
  fi

  if command -v pnpm >/dev/null 2>&1; then
    log "Installing dprint v${DPRINT_VERSION} via pnpm…"
    pnpm dlx "dprint@${DPRINT_VERSION}" --version
    # pnpm dlx is ephemeral; install into a local node_modules for persistence.
    pnpm add -D "dprint@${DPRINT_VERSION}" --silent
    mkdir -p "${TOOLS_DIR}/node_modules/.bin"
    if [[ -x "node_modules/.bin/dprint" ]]; then
      cp "node_modules/.bin/dprint" "${dest}"
      chmod +x "${dest}"
      ok "Installed dprint → ${dest}"
    fi
    return
  fi

  if command -v npm >/dev/null 2>&1; then
    log "Installing dprint v${DPRINT_VERSION} via npm…"
    npm install -g "dprint@${DPRINT_VERSION}"
    local npm_prefix
    npm_prefix="$(npm config get prefix)"
    if [[ -x "${npm_prefix}/bin/dprint" ]]; then
      ln -sf "${npm_prefix}/bin/dprint" "${dest}"
      ok "Installed dprint → ${dest}"
    fi
    return
  fi

  warn "pnpm/npm not found; skipping dprint install"
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
