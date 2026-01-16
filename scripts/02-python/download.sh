#!/bin/bash
# Download and extract Python source code
#
# Steps:
# 1. Download Python source tarball
# 2. Verify SHA256 checksum (from versions.cdx.json)
# 3. Verify Sigstore signature (optional, if uvx available)
# 4. Extract source
#
# Note: Patches are applied in compile.sh, not here. This keeps
# the downloaded source close to upstream for easier debugging.
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

# Get expected SHA256 from versions.cdx.json (using full version)
PYTHON_SHA256="$(get_python_sha256 "$PYTHON_VERSION")"

# Verify version exists in versions.cdx.json
if [ -z "$PYTHON_SHA256" ]; then
  log_error "Python ${PYTHON_VERSION} not found in versions.cdx.json"
  log_error "available versions:"
  $CDX_CLI versions | tr ' ' '\n' | sed 's/^/  /'
  exit 1
fi

PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
SIGSTORE_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz.sigstore"
SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"

# Get sigstore verification info from versions.cdx.json
PYTHON_RELEASE_IDENTITY="$($CDX_CLI sigstore-identity python "$PYTHON_VERSION" 2>/dev/null || true)"
PYTHON_RELEASE_ISSUER="$($CDX_CLI sigstore-issuer python "$PYTHON_VERSION" 2>/dev/null || true)"

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

# Sigstore verification (if configured in versions.cdx.json)
if [ "${SKIP_SIGSTORE:-}" = "1" ]; then
  log_warn "SKIP_SIGSTORE=1 set - skipping sigstore verification"
elif [ -z "$PYTHON_RELEASE_IDENTITY" ] || [ -z "$PYTHON_RELEASE_ISSUER" ]; then
  log_info "no sigstore verification configured for Python ${PYTHON_VERSION}"
elif ! command -v uvx >/dev/null 2>&1; then
  log_info "uvx not found - skipping sigstore verification"
  log_info "install uv from: https://docs.astral.sh/uv/"
else
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
      log_error "sigstore verification FAILED"
      log_error "this may indicate a compromised download or supply chain attack"
      log_error "if you trust the SHA256 checksum, set SKIP_SIGSTORE=1 to bypass"
      rm -f "${SIGSTORE_BUNDLE}"
      exit 1
    fi
    rm -f "${SIGSTORE_BUNDLE}"
  else
    log_warn "sigstore bundle not available for Python ${PYTHON_VERSION}"
    log_warn "expected identity: ${PYTHON_RELEASE_IDENTITY}"
  fi
fi

log_info "extracting..."
tar xzf "${TARBALL}"
rm "${TARBALL}"

log_ok "Python ${PYTHON_VERSION} source ready at ${SRC_DIR}"
