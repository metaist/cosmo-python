#!/bin/bash
# Build OpenSSL with cosmocc for use with Python
#
# Based on ahgamut/superconfigure's proven approach, adapted for our
# cleaner script-based build system.
#
# Key decisions:
# - OpenSSL 1.1.1u: Stable, supported through 2026, well-tested with Cosmopolitan
# - Static library only: Cosmopolitan requires static linking
# - no-asm: Maximum compatibility across platforms
# - getrandom: Modern entropy source that works on all Cosmopolitan targets
#
set -euo pipefail

OPENSSL_VERSION="${OPENSSL_VERSION:-1.1.1u}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

# OpenSSL uses underscore format for tags: OpenSSL_1_1_1u
OPENSSL_TAG="OpenSSL_${OPENSSL_VERSION//./_}"
OPENSSL_URL="https://github.com/openssl/openssl/archive/refs/tags/${OPENSSL_TAG}.tar.gz"
OPENSSL_DIR="${WORK_DIR}/openssl-${OPENSSL_TAG}"

# Known good checksum for 1.1.1u
OPENSSL_SHA256="fafe27202bde4238dce258d82ec8a8592a657842e5431264620a933a0c9436b7"

echo "Building OpenSSL ${OPENSSL_VERSION} with cosmocc..."

# Setup cosmocc
export CC="${COSMO_DIR}/bin/cosmocc"
export AR="${COSMO_DIR}/bin/cosmoar"
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${CC}" ]; then
  echo "Error: cosmocc not found at ${CC}"
  echo "Run setup-cosmocc.sh first"
  exit 1
fi

mkdir -p "${WORK_DIR}" "${DEPS_DIR}/lib" "${DEPS_DIR}/include"

# Download if needed
if [ ! -d "${OPENSSL_DIR}" ]; then
  echo "Downloading OpenSSL ${OPENSSL_VERSION}..."
  cd "${WORK_DIR}"

  TARBALL="openssl-${OPENSSL_TAG}.tar.gz"
  curl -fsSL "${OPENSSL_URL}" -o "${TARBALL}"

  # Verify checksum
  echo "Verifying checksum..."
  ACTUAL_SHA256=$(sha256sum "${TARBALL}" | cut -d' ' -f1)
  if [ "${ACTUAL_SHA256}" != "${OPENSSL_SHA256}" ]; then
    echo "Error: Checksum mismatch!"
    echo "  Expected: ${OPENSSL_SHA256}"
    echo "  Got:      ${ACTUAL_SHA256}"
    rm -f "${TARBALL}"
    exit 1
  fi
  echo "Checksum OK"

  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${OPENSSL_DIR}"

# Apply getrandom patch if not already applied
# This ensures reliable entropy on all Cosmopolitan platforms
RAND_FILE="crypto/rand/rand_unix.c"
if ! grep -q "Force getrandom for Cosmopolitan" "${RAND_FILE}" 2>/dev/null; then
  echo "Applying getrandom patch..."

  # The patch forces OpenSSL to use getrandom() unconditionally
  # This is necessary because Cosmopolitan provides getrandom() on all platforms
  # but the preprocessor conditionals in OpenSSL don't detect it correctly

  # Find the #if line that guards getrandom usage and make it always true
  # Original: #if defined(__GNUC__) && __GNUC__>=2 && defined(__ELF__) && !defined(__hpux)
  # We add a comment and force it to be true

  if grep -q "defined(__linux)" "${RAND_FILE}"; then
    # Patch the linux-specific getrandom section
    sed -i 's/#  if defined(__linux) && defined(__NR_getrandom)/#  if 1 \/\* Force getrandom for Cosmopolitan \*\/ || (defined(__linux) \&\& defined(__NR_getrandom))/' "${RAND_FILE}"

    # Also simplify the syscall to direct getrandom() call if needed
    # superconfigure changes: syscall(__NR_getrandom, buf, buflen, 0) -> getrandom(buf, buflen, 0)
    sed -i 's/syscall(__NR_getrandom, buf, buflen, 0)/getrandom(buf, buflen, 0)/' "${RAND_FILE}"

    echo "Patch applied successfully"
  else
    echo "Warning: Expected pattern not found in ${RAND_FILE}"
    echo "OpenSSL version may have different code structure"
  fi
fi

# Clean any previous build
make clean 2>/dev/null || true

# Configure OpenSSL for static library with Cosmopolitan
#
# Flag explanations:
#   no-shared         - Static libraries only (required for Cosmopolitan)
#   no-asm            - Disable assembly for maximum compatibility
#   no-dso            - Disable dynamic shared object loading
#   no-dynamic-engine - Disable runtime engine loading
#   no-engine         - Disable engine support entirely
#   no-pic            - Disable position-independent code (static linking)
#   no-autoalginit    - Reduce automatic initialization overhead
#   no-autoerrinit    - Reduce automatic error string initialization
#   --with-rand-seed=getrandom - Use getrandom() for entropy
#
echo "Configuring OpenSSL..."
./Configure \
  no-shared \
  no-asm \
  no-dso \
  no-dynamic-engine \
  no-engine \
  no-pic \
  no-autoalginit \
  no-autoerrinit \
  --with-rand-seed=getrandom \
  --openssldir="${DEPS_DIR}/ssl" \
  --prefix="${DEPS_DIR}" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os" \
  linux-x86_64

# Build OpenSSL
echo "Compiling OpenSSL (this may take a few minutes)..."
make -j"$(nproc)" build_libs

# Manual install - avoid make install_sw because cosmoar conflicts with
# OpenSSL's install script when handling fat binary directories
echo "Installing to ${DEPS_DIR}..."
cp libcrypto.a libssl.a "${DEPS_DIR}/lib/"
cp -r include/openssl "${DEPS_DIR}/include/"

# Handle aarch64 objects if they exist
# cosmocc creates .aarch64/ subdirectories for ARM64 objects
if find . -name ".aarch64" -type d | head -1 | grep -q .; then
  echo "Creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"

  # Collect all aarch64 object files and create archives
  CRYPTO_OBJS=$(find crypto -path "*/.aarch64/*.o" 2>/dev/null || true)
  SSL_OBJS=$(find ssl -path "*/.aarch64/*.o" 2>/dev/null || true)

  if [ -n "${CRYPTO_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libcrypto.a" ${CRYPTO_OBJS}
    echo "  Created: ${DEPS_DIR}/lib/.aarch64/libcrypto.a"
  fi

  if [ -n "${SSL_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libssl.a" ${SSL_OBJS}
    echo "  Created: ${DEPS_DIR}/lib/.aarch64/libssl.a"
  fi
fi

echo ""
echo "OpenSSL ${OPENSSL_VERSION} built successfully!"
echo "  Libraries:"
echo "    ${DEPS_DIR}/lib/libssl.a"
echo "    ${DEPS_DIR}/lib/libcrypto.a"
echo "  Headers:  ${DEPS_DIR}/include/openssl/"
ls -la "${DEPS_DIR}/lib/libssl.a" "${DEPS_DIR}/lib/libcrypto.a"
