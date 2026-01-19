#!/bin/bash
# Build zstd with cosmocc for use with Python
#
# Usage: ./zstd.sh [VERSION] [--clean]
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libzstd.a, ${DEPS_DIR}/include/zstd.h
#
source "$(dirname "$0")/common.sh"

# Parse arguments
parse_dep_args "zstd" "$@"

ZSTD_VERSION="$DEP_VERSION"
ZSTD_SHA256="$(get_pkg_sha256 zstd "$ZSTD_VERSION")"
ZSTD_URL="$(get_pkg_url zstd "$ZSTD_VERSION")"
ZSTD_DIR="${WORK_DIR}/zstd-${ZSTD_VERSION}"

# Validate version exists
if [ "$ZSTD_SHA256" = "null" ] || [ -z "$ZSTD_SHA256" ]; then
  log_error "zstd ${ZSTD_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "zstd" "$ZSTD_VERSION" \
    "${DEPS_DIR}/lib/libzstd.a" \
    "${DEPS_DIR}/lib/.aarch64/libzstd.a" \
    "${DEPS_DIR}/include/zstd.h" \
    "${DEPS_DIR}/include/zdict.h" \
    "${DEPS_DIR}/include/zstd_errors.h"
fi

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libzstd.a" "zstd ${ZSTD_VERSION}"

log_build "zstd ${ZSTD_VERSION}"

# Setup cosmocc
setup_cosmocc

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run scripts/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${ZSTD_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="zstd-${ZSTD_VERSION}.tar.gz"
  download_and_verify "${ZSTD_URL}" "${TARBALL}" "${ZSTD_SHA256}" "zstd ${ZSTD_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${ZSTD_DIR}/lib"

# Clean any previous build
make clean 2>/dev/null || true

# Build static library only
# zstd uses a simple Makefile in lib/, override CC and AR
# ZSTD_NO_ASM=1 disables x86 assembly (not supported by cosmocc)
log_info "compiling..."
timed run_dep_make -j"$(nproc)" \
  CC="${CC}" \
  AR="${AR}" \
  ZSTD_NO_ASM=1 \
  CFLAGS="-Os -fPIC" \
  libzstd.a

# Install
log_info "installing..."
cp libzstd.a "${DEPS_DIR}/lib/"
cp zstd.h zdict.h zstd_errors.h "${DEPS_DIR}/include/"

# Handle aarch64 if objects exist (cosmocc puts them in nested .aarch64 dirs)
AARCH64_OBJS=$(find . -path "*/.aarch64/*.o" -type f 2>/dev/null)
if [ -n "$AARCH64_OBJS" ]; then
  log_info "creating aarch64 library..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  # shellcheck disable=SC2086
  ar rcs "${DEPS_DIR}/lib/.aarch64/libzstd.a" $AARCH64_OBJS
fi

log_ok "zstd ${ZSTD_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libzstd.a"
log_info "  headers: ${DEPS_DIR}/include/zstd.h"
