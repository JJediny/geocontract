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

# ── 3. dprint (native binary) ─────────────────────────────────────────────
# dprint publishes a standalone Rust binary per release on GitHub. We
# download the matching linux-x86_64 tarball into .tools/ so the hook
# runner never has to resolve a Node package at runtime.
install_dprint() {
  local dest="${BIN_DIR}/dprint"
  if [[ -x "${dest}" ]]; then
    ok "dprint already installed at ${dest}"
    return
  fi

  local target="x86_64-unknown-linux-gnu"
  local url="https://github.com/dprint/dprint/releases/download/${DPRINT_VERSION}/dprint-${target}.zip"
  local tmp
  tmp="$(mktemp -d)"
  log "Downloading dprint v${DPRINT_VERSION} (${target})…"
  if ! curl -fsSL "${url}" -o "${tmp}/dprint.zip"; then
    warn "Could not download dprint from ${url} (network or non-x86_64 host?)"
    rm -rf "${tmp}"
    return
  fi

  if command -v unzip >/dev/null 2>&1; then
    unzip -q -o "${tmp}/dprint.zip" -d "${tmp}" || { warn "unzip failed"; rm -rf "${tmp}"; return; }
  else
    python3 -c "import zipfile; zipfile.ZipFile('${tmp}/dprint.zip').extractall('${tmp}')" \
      || { warn "no unzip and python3 zipfile failed"; rm -rf "${tmp}"; return; }
  fi

  if [[ ! -x "${tmp}/dprint" ]]; then
    warn "dprint binary not found in the archive"
    rm -rf "${tmp}"
    return
  fi

  mv "${tmp}/dprint" "${dest}"
  chmod +x "${dest}"
  rm -rf "${tmp}"
  ok "Installed dprint v${DPRINT_VERSION} → ${dest}"

  # Quick smoke-test
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
