#!/bin/bash
# Build bzip2 with cosmocc for use with Python
#
# Usage: ./bz2.sh [VERSION] [--clean]
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libbz2.a, ${DEPS_DIR}/include/bzlib.h
#
source "$(dirname "$0")/../common.sh"

# Parse arguments
parse_dep_args "bz2" "$@"

BZ2_VERSION="$DEP_VERSION"
BZ2_SHA256="$(get_pkg_sha256 bz2 "$BZ2_VERSION")"
BZ2_URL="$(get_pkg_url bz2 "$BZ2_VERSION")"
BZ2_DIR="${WORK_DIR}/bzip2-${BZ2_VERSION}"

# Validate version exists
if [ "$BZ2_SHA256" = "null" ] || [ -z "$BZ2_SHA256" ]; then
  log_error "bz2 ${BZ2_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "bzip2" "$BZ2_VERSION" \
    "${DEPS_DIR}/lib/libbz2.a" \
    "${DEPS_DIR}/lib/.aarch64/libbz2.a" \
    "${DEPS_DIR}/include/bzlib.h"
fi

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libbz2.a" "bzip2 ${BZ2_VERSION}"

log_build "bzip2 ${BZ2_VERSION}"

# Setup cosmocc
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${BZ2_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="bzip2-${BZ2_VERSION}.tar.gz"
  download_verify_gpg "bz2" "${BZ2_VERSION}" "${BZ2_URL}" "${TARBALL}" "bzip2 ${BZ2_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${BZ2_DIR}"

# Clean any previous build
make clean 2>/dev/null || true

# bzip2 uses a simple Makefile, override CC and AR
log_info "compiling..."
timed run_dep_make -j"$(nproc)" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os -D_FILE_OFFSET_BITS=64" \
  libbz2.a

log_info "installing..."
cp libbz2.a "${DEPS_DIR}/lib/"
cp bzlib.h "${DEPS_DIR}/include/"

# Handle aarch64 if objects exist
if [ -d ".aarch64" ] && ls .aarch64/*.o 1> /dev/null 2>&1; then
  log_info "creating aarch64 library..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  ar rcs "${DEPS_DIR}/lib/.aarch64/libbz2.a" .aarch64/*.o
fi

log_ok "bzip2 ${BZ2_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libbz2.a"
log_info "  header:  ${DEPS_DIR}/include/bzlib.h"
