#!/bin/bash
# Download Mozilla CA certificate bundle
#
# Usage: ./cacert.sh [VERSION]
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/share/ssl/cert.pem, ${DEPS_DIR}/share/ssl/certs/
#
source "$(dirname "$0")/common.sh"

# Parse arguments
parse_dep_args "cacert" "$@"

CACERT_VERSION="$DEP_VERSION"
CACERT_SHA256="$(get_pkg_sha256 cacert "$CACERT_VERSION")"
CACERT_URL="$(get_pkg_url cacert "$CACERT_VERSION")"

CA_BUNDLE_DIR="${DEPS_DIR}/share/ssl/certs"
CA_BUNDLE_FILE="${DEPS_DIR}/share/ssl/cert.pem"

# Validate version exists
if [ "$CACERT_SHA256" = "null" ] || [ -z "$CACERT_SHA256" ]; then
  log_error "cacert ${CACERT_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "cacert" "$CACERT_VERSION" \
    "${CA_BUNDLE_FILE}" \
    "${CA_BUNDLE_DIR}"
fi

# Idempotency: skip if already installed
skip_if_exists "${CA_BUNDLE_FILE}" "cacert ${CACERT_VERSION}"

log_build "cacert ${CACERT_VERSION}"

mkdir -p "${CA_BUNDLE_DIR}"

# Download and verify
log_info "downloading Mozilla CA certificate bundle..."
curl -fsSL "${CACERT_URL}" -o "${CA_BUNDLE_FILE}.tmp"
echo "${CACERT_SHA256}  ${CA_BUNDLE_FILE}.tmp" | sha256sum -c - > /dev/null 2>&1 || {
  log_error "CA bundle checksum verification failed!"
  rm -f "${CA_BUNDLE_FILE}.tmp"
  exit 1
}
mv "${CA_BUNDLE_FILE}.tmp" "${CA_BUNDLE_FILE}"
log_info "checksum verified"

# Also create individual cert files for compatibility
# Some tools expect a directory of individual certs
log_info "extracting individual certificates..."
cd "${CA_BUNDLE_DIR}"
awk 'BEGIN {c=0} /-----BEGIN CERTIFICATE-----/{c++} {print > "cert-" c ".pem"}' "${CA_BUNDLE_FILE}" 2>/dev/null || true

log_ok "cacert ${CACERT_VERSION} installed"
log_info "  bundle:  ${CA_BUNDLE_FILE}"
log_info "  certs:   ${CA_BUNDLE_DIR}/"
