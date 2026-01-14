#!/bin/bash
# Download and extract Python source code
#
# Verifies source integrity via:
# 1. SHA256 checksum (always, from versions.json)
# 2. Sigstore signature (optional, if sigstore CLI is available)
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"

# Get expected SHA256 from versions.json (using full version)
PYTHON_SHA256="$(get_python_sha256 "$PYTHON_VERSION")"

# Verify version exists in versions.json
if [ "$PYTHON_SHA256" = "null" ] || [ -z "$PYTHON_SHA256" ]; then
  log_error "Python ${PYTHON_VERSION} not found in versions.json"
  log_error "available versions:"
  jq -r '.python.versions | keys[]' "${VERSIONS_FILE}" | sed 's/^/  /'
  exit 1
fi

PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
SIGSTORE_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz.sigstore"
SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"

# Python release manager identity for sigstore verification
# See: https://www.python.org/dev/peps/pep-0101/
PYTHON_RELEASE_IDENTITY="thomas@python.org"
PYTHON_RELEASE_ISSUER="https://accounts.google.com"

# Check if already downloaded and extracted
if [ -f "${SRC_DIR}/configure" ]; then
  log_skip "Python ${PYTHON_VERSION} source already at ${SRC_DIR}"
  exit 0
fi

log_build "downloading Python ${PYTHON_VERSION} source"

mkdir -p "${WORK_DIR}"
cd "${WORK_DIR}"

TARBALL="Python-${PYTHON_VERSION}.tgz"
SIGSTORE_BUNDLE="${TARBALL}.sigstore"

# Download and verify checksum
download_and_verify "${PYTHON_URL}" "${TARBALL}" "${PYTHON_SHA256}" "Python ${PYTHON_VERSION}"

# Sigstore verification (optional but recommended)
if command -v uvx >/dev/null 2>&1; then
  log_info "verifying sigstore signature..."
  
  # Download sigstore bundle
  if curl -fsSL "${SIGSTORE_URL}" -o "${SIGSTORE_BUNDLE}" 2>/dev/null; then
    if uvx sigstore verify identity \
        --bundle "${SIGSTORE_BUNDLE}" \
        --cert-identity "${PYTHON_RELEASE_IDENTITY}" \
        --cert-oidc-issuer "${PYTHON_RELEASE_ISSUER}" \
        "${TARBALL}" >/dev/null 2>&1; then
      log_ok "sigstore signature verified (signed by ${PYTHON_RELEASE_IDENTITY})"
    else
      log_warn "sigstore verification failed - continuing with SHA256 verification only"
      log_warn "this may indicate a supply chain issue or changed release process"
    fi
    rm -f "${SIGSTORE_BUNDLE}"
  else
    log_warn "sigstore bundle not available for Python ${PYTHON_VERSION}"
  fi
else
  log_info "uvx not found - skipping sigstore verification"
  log_info "install uv from: https://docs.astral.sh/uv/"
fi

log_info "extracting..."
tar xzf "${TARBALL}"
rm "${TARBALL}"

# Apply version-specific patches if they exist
PATCHES_DIR="${REPO_ROOT}/patches/${PYTHON_MAJOR_MINOR}"

if [ -d "${PATCHES_DIR}" ]; then
  log_info "applying patches from ${PATCHES_DIR}..."
  cd "${SRC_DIR}"
  for patch in "${PATCHES_DIR}"/*.patch; do
    if [ -f "$patch" ]; then
      patch_name=$(basename "$patch")
      log_info "  applying ${patch_name}..."
      patch -p1 < "$patch"
    fi
  done
fi

log_ok "Python ${PYTHON_VERSION} source ready at ${SRC_DIR}"
