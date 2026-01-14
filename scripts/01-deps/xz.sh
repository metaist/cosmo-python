#!/bin/bash
# Build xz/liblzma with cosmocc for use with Python
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/liblzma.a, ${DEPS_DIR}/include/lzma.h
#
source "$(dirname "$0")/../common.sh"

# Get version and checksum from versions.json
XZ_VERSION="${XZ_VERSION:-$(get_dep_version xz)}"
XZ_SHA256="$(get_dep_sha256 xz)"
XZ_URL="https://github.com/tukaani-project/xz/releases/download/v${XZ_VERSION}/xz-${XZ_VERSION}.tar.gz"
XZ_DIR="${WORK_DIR}/xz-${XZ_VERSION}"

ensure_dirs

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/liblzma.a" "xz/liblzma ${XZ_VERSION}"

log_build "xz/liblzma ${XZ_VERSION}"

# Setup cosmocc (with ccache if available)
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${XZ_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="xz-${XZ_VERSION}.tar.gz"
  download_and_verify "${XZ_URL}" "${TARBALL}" "${XZ_SHA256}" "xz ${XZ_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${XZ_DIR}"

# Clean any previous build
make clean 2>/dev/null || true
make distclean 2>/dev/null || true

# Configure for static library only
log_info "configuring..."
./configure \
  --host=x86_64-linux \
  --disable-shared \
  --enable-static \
  --disable-xz \
  --disable-xzdec \
  --disable-lzmadec \
  --disable-lzmainfo \
  --disable-scripts \
  --disable-doc \
  --disable-nls \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os"

# Build only liblzma
log_info "compiling..."
timed make -C src/liblzma -j"$(nproc)"

# Install
log_info "installing..."
cp src/liblzma/.libs/liblzma.a "${DEPS_DIR}/lib/"
cp -r src/liblzma/api/lzma.h src/liblzma/api/lzma "${DEPS_DIR}/include/"

# Create aarch64 library if objects exist
if find src/liblzma -name ".aarch64" -type d | head -1 | grep -q .; then
  log_info "creating aarch64 library..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  find src/liblzma -path "*/.aarch64/*.o" -exec ar rcs "${DEPS_DIR}/lib/.aarch64/liblzma.a" {} + 2>/dev/null || true
fi

log_ok "xz/liblzma ${XZ_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/liblzma.a"
log_info "  headers: ${DEPS_DIR}/include/lzma.h"
