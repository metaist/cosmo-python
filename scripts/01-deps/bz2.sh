#!/bin/bash
# Build bzip2 with cosmocc for use with Python
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libbz2.a, ${DEPS_DIR}/include/bzlib.h
#
source "$(dirname "$0")/../common.sh"

# Get version and checksum from versions.json
BZ2_VERSION="${BZ2_VERSION:-$(get_dep_version bz2)}"
BZ2_SHA256="$(get_dep_sha256 bz2)"
BZ2_URL="https://sourceware.org/pub/bzip2/bzip2-${BZ2_VERSION}.tar.gz"
BZ2_DIR="${WORK_DIR}/bzip2-${BZ2_VERSION}"

ensure_dirs

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libbz2.a" "bzip2 ${BZ2_VERSION}"

log_build "bzip2 ${BZ2_VERSION}"

# Setup cosmocc
export CC="${COSMO_DIR}/bin/cosmocc"
export AR="${COSMO_DIR}/bin/cosmoar"
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${CC}" ]; then
  log_error "cosmocc not found at ${CC}"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${BZ2_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="bzip2-${BZ2_VERSION}.tar.gz"
  download_and_verify "${BZ2_URL}" "${TARBALL}" "${BZ2_SHA256}" "bzip2 ${BZ2_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${BZ2_DIR}"

# Clean any previous build
make clean 2>/dev/null || true

# bzip2 uses a simple Makefile, override CC and AR
log_info "compiling..."
timed make -j"$(nproc)" \
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
