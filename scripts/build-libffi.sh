#!/bin/bash
# Build libffi with Cosmopolitan for Python's ctypes module
#
# This script demonstrates how to build C libraries with assembly code
# for Cosmopolitan. The key challenges are:
#
# 1. The cosmocc wrapper rejects assembly files (.S) directly
# 2. The arch-specific compilers need Cosmopolitan's include paths
# 3. Configure's executable tests conflict with Cosmopolitan's runtime
#
# Solution: Create a wrapper script that:
# - Passes proper Cosmopolitan flags to the arch-specific compiler
# - Handles both C and assembly files
# - Uses cross-compile mode to skip problematic link tests
#
# Based on ahgamut/superconfigure's approach.
#
# CRITICAL: --disable-exec-static-tramp prevents segfaults with closures
#
set -euo pipefail

LIBFFI_VERSION="${LIBFFI_VERSION:-3.4.2}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

LIBFFI_URL="https://github.com/libffi/libffi/releases/download/v${LIBFFI_VERSION}/libffi-${LIBFFI_VERSION}.tar.gz"
LIBFFI_SRC="${WORK_DIR}/libffi-${LIBFFI_VERSION}"

echo "Building libffi ${LIBFFI_VERSION} for Cosmopolitan..."

# Verify toolchain exists
if [ ! -x "${COSMO_DIR}/bin/x86_64-linux-cosmo-gcc" ]; then
  echo "Error: Cosmopolitan toolchain not found at ${COSMO_DIR}"
  echo "Run setup-cosmocc.sh first"
  exit 1
fi

mkdir -p "${WORK_DIR}" "${DEPS_DIR}/lib" "${DEPS_DIR}/lib/.aarch64" "${DEPS_DIR}/include"

# Download if needed
if [ ! -d "${LIBFFI_SRC}" ]; then
  echo "Downloading libffi ${LIBFFI_VERSION}..."
  cd "${WORK_DIR}"
  curl -fsSL "${LIBFFI_URL}" -o "libffi-${LIBFFI_VERSION}.tar.gz"
  tar xzf "libffi-${LIBFFI_VERSION}.tar.gz"
  rm "libffi-${LIBFFI_VERSION}.tar.gz"
fi

# Common configure flags for both architectures
COMMON_CONFIG_FLAGS=(
  --disable-shared
  --enable-static
  --disable-exec-static-tramp  # CRITICAL: prevents segfaults with closures
  --disable-docs
)

# Create a compiler wrapper script for the specified architecture
# This handles both C and assembly files with proper Cosmopolitan setup
# It also handles linking with proper CRT files and libraries
create_compiler_wrapper() {
  local ARCH="$1"
  local WRAPPER_PATH="$2"

  cat > "${WRAPPER_PATH}" << 'WRAPPER_EOF'
#!/bin/bash
# Cosmopolitan compiler wrapper for ARCH_PLACEHOLDER
# Handles C, assembly files, and linking with proper Cosmopolitan setup

COSMO_DIR="COSMO_DIR_PLACEHOLDER"
ARCH="ARCH_PLACEHOLDER"
ARCH_GCC="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-gcc"
LIB_DIR="${COSMO_DIR}/${ARCH}-linux-cosmo/lib"

# Cosmopolitan compiler flags
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
  # Compile only - just need include paths
  exec "${ARCH_GCC}" ${COSMO_CPPFLAGS} "$@"
else
  # Linking - need full Cosmopolitan link setup
  # Use -static -nostdlib and provide CRT files explicitly
  COSMO_LDFLAGS="-static -nostdlib -no-pie -fuse-ld=bfd"
  COSMO_LDFLAGS="${COSMO_LDFLAGS} -L${LIB_DIR}"

  # CRT files and linker script
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

  # Replace placeholders with actual values
  sed -i "s|COSMO_DIR_PLACEHOLDER|${COSMO_DIR}|g" "${WRAPPER_PATH}"
  sed -i "s|ARCH_PLACEHOLDER|${ARCH}|g" "${WRAPPER_PATH}"

  chmod +x "${WRAPPER_PATH}"
}

# Function to build for a specific architecture
build_arch() {
  local ARCH="$1"
  local HOST="$2"
  local BUILD_DIR="${WORK_DIR}/libffi-build-${ARCH}"
  local INSTALL_DIR="${BUILD_DIR}/install"
  local WRAPPER="${BUILD_DIR}/cosmo-cc"

  echo ""
  echo "=========================================="
  echo "Building libffi for ${ARCH}"
  echo "=========================================="

  # Create fresh build directory
  rm -rf "${BUILD_DIR}"
  mkdir -p "${BUILD_DIR}" "${INSTALL_DIR}"

  # Create compiler wrapper for this architecture
  create_compiler_wrapper "${ARCH}" "${WRAPPER}"

  # Other tools
  local AR="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-ar"
  local RANLIB="${COSMO_DIR}/bin/${ARCH}-linux-cosmo-ranlib"

  cd "${BUILD_DIR}"

  echo "Configuring for ${ARCH}..."
  # Use cross-compile mode (--build != --host) to skip executable link tests
  # Pre-set cache variables to avoid tests that would fail
  "${LIBFFI_SRC}/configure" \
    --build=x86_64-pc-linux-gnu \
    --host="${HOST}" \
    --prefix="${INSTALL_DIR}" \
    "${COMMON_CONFIG_FLAGS[@]}" \
    CC="${WRAPPER}" \
    AR="${AR}" \
    RANLIB="${RANLIB}" \
    CFLAGS="-Os"

  echo "Compiling for ${ARCH}..."
  make -j"$(nproc)"

  echo "Installing ${ARCH} build..."
  make install

  echo "  Built: ${INSTALL_DIR}/lib/libffi.a"
}

# Build for both architectures
build_arch "x86_64" "x86_64-linux-gnu"
build_arch "aarch64" "aarch64-linux-gnu"

# Install to final DEPS_DIR
echo ""
echo "=========================================="
echo "Installing to ${DEPS_DIR}"
echo "=========================================="

# Copy x86_64 libraries (primary)
# libffi installs to lib64 on some systems
if [ -f "${WORK_DIR}/libffi-build-x86_64/install/lib64/libffi.a" ]; then
  cp "${WORK_DIR}/libffi-build-x86_64/install/lib64/libffi.a" "${DEPS_DIR}/lib/"
else
  cp "${WORK_DIR}/libffi-build-x86_64/install/lib/libffi.a" "${DEPS_DIR}/lib/"
fi

# Copy aarch64 libraries to .aarch64 subdirectory (for fat binary linking)
if [ -f "${WORK_DIR}/libffi-build-aarch64/install/lib64/libffi.a" ]; then
  cp "${WORK_DIR}/libffi-build-aarch64/install/lib64/libffi.a" "${DEPS_DIR}/lib/.aarch64/"
else
  cp "${WORK_DIR}/libffi-build-aarch64/install/lib/libffi.a" "${DEPS_DIR}/lib/.aarch64/"
fi

# Copy headers (same for both architectures, use x86_64)
cp -r "${WORK_DIR}/libffi-build-x86_64/install/include"/* "${DEPS_DIR}/include/"

# Verify installation
echo ""
echo "libffi ${LIBFFI_VERSION} built successfully!"
echo ""
echo "Libraries:"
echo "  x86_64:  ${DEPS_DIR}/lib/libffi.a"
ls -la "${DEPS_DIR}/lib/libffi.a"
echo "  aarch64: ${DEPS_DIR}/lib/.aarch64/libffi.a"
ls -la "${DEPS_DIR}/lib/.aarch64/libffi.a"
echo ""
echo "Headers:   ${DEPS_DIR}/include/ffi.h"
echo ""
echo "Note: When linking with cosmocc, the toolchain automatically uses"
echo "the appropriate library based on the target architecture."
