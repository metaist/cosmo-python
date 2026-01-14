#!/bin/bash
# Download and setup the Cosmopolitan C compiler toolchain
source "$(dirname "$0")/../common.sh"

COSMOCC_VERSION="${COSMOCC_VERSION:-4.0.2}"
COSMOCC_URL="https://github.com/jart/cosmopolitan/releases/download/${COSMOCC_VERSION}/cosmocc-${COSMOCC_VERSION}.zip"

# Check if already installed
if [ -x "${COSMO_DIR}/bin/cosmocc" ]; then
  installed_marker="${COSMO_DIR}/.cosmocc-version"
  if [ -f "$installed_marker" ] && [ "$(cat "$installed_marker")" = "$COSMOCC_VERSION" ]; then
    log_skip "cosmocc ${COSMOCC_VERSION} already installed at ${COSMO_DIR}"
    exit 0
  fi
fi

log_build "cosmocc ${COSMOCC_VERSION}"

mkdir -p "${COSMO_DIR}"
cd "${COSMO_DIR}"

log_info "downloading cosmocc ${COSMOCC_VERSION}..."
timed wget -q "${COSMOCC_URL}" -O cosmocc.zip

log_info "extracting..."
unzip -q -o cosmocc.zip
rm cosmocc.zip

# Verify installation
if "${COSMO_DIR}/bin/cosmocc" --version > /dev/null 2>&1; then
  # Record version for idempotency (only after successful verification)
  echo "${COSMOCC_VERSION}" > "${COSMO_DIR}/.cosmocc-version"
  log_ok "cosmocc ${COSMOCC_VERSION} installed at ${COSMO_DIR}"
else
  log_error "cosmocc installation failed"
  exit 1
fi
