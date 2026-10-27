#!/usr/bin/env bash
# Install the release binary used by ontology-check and .mcp.json.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="${OPEN_ONTOLOGIES_VERSION:?Run through 'mise run ontology-install' so the version pin is set}"
DEST="${ROOT}/.tools/open-ontologies/bin/open-ontologies"

if [[ -x "${DEST}" ]]; then
  installed="$("${DEST}" --data-dir "${ROOT}/.tools/open-ontologies/state" --no-connect status)"
  if [[ "${installed}" == *"\"version\":\"${VERSION}\""* ]]; then
    echo "Open Ontologies ${VERSION} is already installed at ${DEST}"
    exit 0
  fi
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) asset="open-ontologies-x86_64-unknown-linux-gnu" ;;
  Darwin-arm64) asset="open-ontologies-aarch64-apple-darwin" ;;
  *)
    echo "No documented Open Ontologies release binary for $(uname -s)/$(uname -m)." >&2
    echo "Build the pinned submodule with: cargo build --release --manifest-path open-ontologies/Cargo.toml" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "${DEST}")"
base_url="https://github.com/fabio-rovai/open-ontologies/releases/download/v${VERSION}"
trap 'rm -f "${DEST}.tmp" "${DEST}.sha256"' EXIT
curl -fL "${base_url}/${asset}" -o "${DEST}.tmp"
curl -fL "${base_url}/SHASUMS.txt" -o "${DEST}.sha256"
expected="$(awk -v asset="${asset}" '$2 == asset { print $1 }' "${DEST}.sha256")"
if [[ -z "${expected}" ]]; then
  echo "Release SHASUMS.txt has no entry for ${asset}" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "${DEST}.tmp" | awk '{ print $1 }')"
else
  actual="$(shasum -a 256 "${DEST}.tmp" | awk '{ print $1 }')"
fi
if [[ "${actual}" != "${expected}" ]]; then
  echo "Checksum mismatch for ${asset}: expected ${expected}, got ${actual}" >&2
  exit 1
fi
chmod +x "${DEST}.tmp"
mv "${DEST}.tmp" "${DEST}"
installed="$("${DEST}" --data-dir "${ROOT}/.tools/open-ontologies/state" --no-connect status)"
if [[ "${installed}" != *"\"version\":\"${VERSION}\""* ]]; then
  echo "Downloaded binary does not report Open Ontologies ${VERSION}: ${installed}" >&2
  exit 1
fi
echo "${installed}"
