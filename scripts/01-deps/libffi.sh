#!/bin/bash
# Build libffi with Cosmopolitan for Python's ctypes module
#
# Usage: ./libffi.sh [VERSION] [--clean]
#
# This script builds C libraries with assembly code for Cosmopolitan.
# Key challenges:
#   1. The cosmocc wrapper rejects assembly files (.S) directly
#   2. The arch-specific compilers need Cosmopolitan's include paths
#   3. Configure's executable tests conflict with Cosmopolitan's runtime
#
# Solution: Create a wrapper script that handles both C and assembly files.
#
# Based on ahgamut/superconfigure's approach.
#
# CRITICAL: --disable-exec-static-tramp prevents segfaults with closures
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libffi.a, ${DEPS_DIR}/include/ffi.h
#
source "$(dirname "$0")/../common.sh"

# Parse arguments
parse_dep_args "libffi" "$@"

LIBFFI_VERSION="$DEP_VERSION"
LIBFFI_SHA256="$(get_pkg_sha256 libffi "$LIBFFI_VERSION")"
LIBFFI_URL="$(get_pkg_url libffi "$LIBFFI_VERSION")"
LIBFFI_SRC="${WORK_DIR}/libffi-${LIBFFI_VERSION}"

# Validate version exists
if [ "$LIBFFI_SHA256" = "null" ] || [ -z "$LIBFFI_SHA256" ]; then
  log_error "libffi ${LIBFFI_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "libffi" "$LIBFFI_VERSION" \
    "${DEPS_DIR}/lib/libffi.a" \
    "${DEPS_DIR}/lib/.aarch64/libffi.a" \
    "${DEPS_DIR}/include/ffi.h" \
    "${DEPS_DIR}/include/ffitarget.h" \
    "${WORK_DIR}/libffi-build-x86_64" \
    "${WORK_DIR}/libffi-build-aarch64"
fi

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libffi.a" "libffi ${LIBFFI_VERSION}"

log_build "libffi ${LIBFFI_VERSION}"

# Verify toolchain exists
if [ ! -x "${COSMO_DIR}/bin/x86_64-linux-cosmo-gcc" ]; then
  log_error "cosmopolitan toolchain not found at ${COSMO_DIR}"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${LIBFFI_SRC}" ]; then
  cd "${WORK_DIR}"
  TARBALL="libffi-${LIBFFI_VERSION}.tar.gz"
  download_verify_gpg "libffi" "${LIBFFI_VERSION}" "${LIBFFI_URL}" "${TARBALL}" "libffi ${LIBFFI_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

# Common configure flags for both architectures
COMMON_CONFIG_FLAGS=(
  --disable-shared
  --enable-static
  --disable-exec-static-tramp  # CRITICAL: prevents segfaults with closures
  --disable-docs
)

# Create a compiler wrapper script for the specified architecture
create_compiler_wrapper() {
  local ARCH="$1"
  local WRAPPER_PATH="$2"

  cat > "${WRAPPER_PATH}" << 'WRAPPER_EOF'
#!/bin/bash
# Cosmopolitan compiler wrapper for ARCH_PLACEHOLDER

COSMO_DIR="COSMO_DIR_PLACEHOLDER"
ARCH="ARCH_PLACEHOLDER"
ARCH_GCC="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-gcc"
LIB_DIR="${COSMO_DIR}/${ARCH}-linux-cosmo/lib"

COSMO_CPPFLAGS="-fno-pie -nostdinc -isystem ${COSMO_DIR}/include"
COSMO_CPPFLAGS="${COSMO_CPPFLAGS} -include libc/integral/normalize.inc"

# Check if we're compiling only (-c flag) or linking
COMPILE_ONLY=0
for arg in "$@"; do
  if [ "$arg" = "-c" ] || [ "$arg" = "-E" ] || [ "$arg" = "-S" ]; then
    COMPILE_ONLY=1
    break
  fi
done

if [ $COMPILE_ONLY -eq 1 ]; then
  exec "${ARCH_GCC}" ${COSMO_CPPFLAGS} "$@"
else
  COSMO_LDFLAGS="-static -nostdlib -no-pie -fuse-ld=bfd"
  COSMO_LDFLAGS="${COSMO_LDFLAGS} -L${LIB_DIR}"

  if [ "${ARCH}" = "x86_64" ]; then
    CRT="${LIB_DIR}/ape.o ${LIB_DIR}/crt.o"
    COSMO_LDFLAGS="${COSMO_LDFLAGS} -Wl,-T,${LIB_DIR}/ape.lds"
  else
    CRT="${LIB_DIR}/crt.o"
    COSMO_LDFLAGS="${COSMO_LDFLAGS} -Wl,-T,${LIB_DIR}/aarch64.lds"
  fi

  exec "${ARCH_GCC}" ${COSMO_CPPFLAGS} ${COSMO_LDFLAGS} ${CRT} "$@" -lcosmo
fi
WRAPPER_EOF

  sed -i "s|COSMO_DIR_PLACEHOLDER|${COSMO_DIR}|g" "${WRAPPER_PATH}"
  sed -i "s|ARCH_PLACEHOLDER|${ARCH}|g" "${WRAPPER_PATH}"
  chmod +x "${WRAPPER_PATH}"
}

# Build for a specific architecture
build_arch() {
  local ARCH="$1"
  local HOST="$2"
  local BUILD_DIR="${WORK_DIR}/libffi-build-${ARCH}"
  local INSTALL_DIR="${BUILD_DIR}/install"
  local WRAPPER="${BUILD_DIR}/cosmo-cc"

  log_info "building for ${ARCH}..."

  rm -rf "${BUILD_DIR}"
  mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

  create_compiler_wrapper "${ARCH}" "${WRAPPER}"

  local AR="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-ar"
  local RANLIB="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-ranlib"

  cd "${BUILD_DIR}"

  run_configure "${LIBFFI_SRC}/configure" \
    --build=x86_64-pc-linux-gnu \
    --host="${HOST}" \
    --prefix="${INSTALL_DIR}" \
    "${COMMON_CONFIG_FLAGS[@]}" \
    CC="${WRAPPER}" \
    AR="${AR}" \
    RANLIB="${RANLIB}" \
    CFLAGS="-Os"

  timed run_dep_make -j"$(nproc)"
  make install
}

# Build for both architectures
build_arch "x86_64" "x86_64-linux-gnu"
build_arch "aarch64" "aarch64-linux-gnu"

# Install to final DEPS_DIR
log_info "installing to ${DEPS_DIR}..."

# Copy x86_64 libraries (libffi installs to lib64 on some systems)
if [ -f "${WORK_DIR}/libffi-build-x86_64/install/lib64/libffi.a" ]; then
  cp "${WORK_DIR}/libffi-build-x86_64/install/lib64/libffi.a" "${DEPS_DIR}/lib/"
else
  cp "${WORK_DIR}/libffi-build-x86_64/install/lib/libffi.a" "${DEPS_DIR}/lib/"
fi

# Copy aarch64 libraries
if [ -f "${WORK_DIR}/libffi-build-aarch64/install/lib64/libffi.a" ]; then
  cp "${WORK_DIR}/libffi-build-aarch64/install/lib64/libffi.a" "${DEPS_DIR}/lib/.aarch64/"
else
  cp "${WORK_DIR}/libffi-build-aarch64/install/lib/libffi.a" "${DEPS_DIR}/lib/.aarch64/"
fi

# Copy headers
cp -r "${WORK_DIR}/libffi-build-x86_64/install/include"/* "${DEPS_DIR}/include/"

log_ok "libffi ${LIBFFI_VERSION} installed"
log_info "  x86_64:  ${DEPS_DIR}/lib/libffi.a"
log_info "  aarch64: ${DEPS_DIR}/lib/.aarch64/libffi.a"
log_info "  headers: ${DEPS_DIR}/include/ffi.h"
