#!/bin/bash
# Download and setup the Cosmopolitan C compiler toolchain
source "$(dirname "$0")/../common.sh"

# Get version, checksum, and URL from upstream.cdx.json
COSMOCC_VERSION="${COSMOCC_VERSION:-$(get_dep_version cosmocc)}"
COSMOCC_SHA256="$(get_dep_sha256 cosmocc)"
COSMOCC_URL="$(get_pkg_url cosmocc "$COSMOCC_VERSION")"

# Check if already installed with correct version
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

# Download and verify checksum
download_and_verify "${COSMOCC_URL}" "cosmocc.zip" "${COSMOCC_SHA256}" "cosmocc ${COSMOCC_VERSION}"

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

# Setup APE loader (allows running Cosmopolitan binaries directly)
APE_LOADER="${COSMO_DIR}/bin/ape-x86_64.elf"
if [ -f "$APE_LOADER" ] && [ ! -f /usr/bin/ape ]; then
  if [ -w /usr/bin ] 2>/dev/null; then
    log_info "installing APE loader to /usr/bin/ape..."
    cp "$APE_LOADER" /usr/bin/ape 2>/dev/null || true
  elif command -v sudo >/dev/null 2>&1; then
    log_info "installing APE loader to /usr/bin/ape (via sudo)..."
    sudo cp "$APE_LOADER" /usr/bin/ape 2>/dev/null || true
  fi
fi

# Register APE with binfmt_misc (Linux only, best-effort)
if [ -f /proc/sys/fs/binfmt_misc/register ] && [ ! -f /proc/sys/fs/binfmt_misc/APE ]; then
  log_info "registering APE with binfmt_misc..."
  if [ -w /proc/sys/fs/binfmt_misc/register ] 2>/dev/null; then
    echo ':APE:M::MZqFpD::/usr/bin/ape:' > /proc/sys/fs/binfmt_misc/register 2>/dev/null || true
  elif command -v sudo >/dev/null 2>&1; then
    sudo sh -c "echo ':APE:M::MZqFpD::/usr/bin/ape:' > /proc/sys/fs/binfmt_misc/register" 2>/dev/null || true
  fi
fi
