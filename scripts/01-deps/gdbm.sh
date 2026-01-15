#!/bin/bash
# Build GNU dbm (gdbm) with cosmocc
#
# Usage: ./gdbm.sh [VERSION] [--clean]
#
# gdbm provides a hash-based key-value store used by Python's dbm.gnu module.
# We build with --enable-libgdbm-compat for ndbm compatibility.
#
source "$(dirname "$0")/../common.sh"

# Parse arguments
parse_dep_args "gdbm" "$@"

GDBM_VERSION="$DEP_VERSION"
GDBM_SHA256="$(get_pkg_sha256 gdbm "$GDBM_VERSION")"
GDBM_URL="https://ftp.gnu.org/gnu/gdbm/gdbm-${GDBM_VERSION}.tar.gz"
GDBM_DIR="${WORK_DIR}/gdbm-${GDBM_VERSION}"

# Validate version exists
if [ "$GDBM_SHA256" = "null" ] || [ -z "$GDBM_SHA256" ]; then
  log_error "gdbm ${GDBM_VERSION} not found in versions.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "gdbm" "$GDBM_VERSION" \
    "${DEPS_DIR}/lib/libgdbm.a" \
    "${DEPS_DIR}/lib/libgdbm_compat.a" \
    "${DEPS_DIR}/lib/.aarch64/libgdbm.a" \
    "${DEPS_DIR}/lib/.aarch64/libgdbm_compat.a" \
    "${DEPS_DIR}/include/gdbm.h"
fi

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libgdbm.a" "gdbm ${GDBM_VERSION}"

log_build "gdbm ${GDBM_VERSION}"

# Setup cosmocc
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${GDBM_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="gdbm-${GDBM_VERSION}.tar.gz"
  download_and_verify "${GDBM_URL}" "${TARBALL}" "${GDBM_SHA256}" "gdbm ${GDBM_VERSION}"
  tar xf "${TARBALL}"
  rm -f "${TARBALL}"
fi

cd "${GDBM_DIR}"

# Configure for static build
# Based on superconfigure's config:
# - disable-memory-mapped-io: more portable
# - enable-libgdbm-compat: provides ndbm compatibility
# - without-readline: we don't need the gdbm CLI tool
run_configure ./configure \
  --prefix="${DEPS_DIR}" \
  --disable-memory-mapped-io \
  --enable-libgdbm-compat \
  --disable-shared \
  --enable-static \
  --disable-nls \
  --disable-rpath \
  --without-readline \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os"

# Build
log_info "compiling..."
timed run_dep_make -j"$(nproc)"

# Create aarch64 archives before install
# cosmoar (used as RANLIB) expects .aarch64 archives to exist
# when it runs ranlib on x86_64 archives during libtool install
AARCH64_AR="${COSMO_DIR}/bin/aarch64-linux-cosmo-ar"
mkdir -p "${DEPS_DIR}/lib/.aarch64"
if [ -d "src/.aarch64" ]; then
  log_info "creating aarch64 library..."
  "${AARCH64_AR}" rcs "${DEPS_DIR}/lib/.aarch64/libgdbm.a" src/.aarch64/*.o
fi
if [ -d "compat/.aarch64" ]; then
  "${AARCH64_AR}" rcs "${DEPS_DIR}/lib/.aarch64/libgdbm_compat.a" compat/.aarch64/*.o
fi

# Install
log_info "installing..."
make install

# Handle aarch64 if objects exist
# Use architecture-specific ar, not cosmoar (which expects paired files)
if [ -d "${GDBM_DIR}/src/.aarch64" ]; then
  log_info "finalizing aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  "${AARCH64_AR}" rcs "${DEPS_DIR}/lib/.aarch64/libgdbm.a" "${GDBM_DIR}"/src/.aarch64/*.o
  # Also create compat library if objects exist
  if [ -d "${GDBM_DIR}/compat/.aarch64" ]; then
    "${AARCH64_AR}" rcs "${DEPS_DIR}/lib/.aarch64/libgdbm_compat.a" "${GDBM_DIR}"/compat/.aarch64/*.o
  fi
fi

log_ok "gdbm ${GDBM_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libgdbm.a"
log_info "  headers: ${DEPS_DIR}/include/gdbm.h"
