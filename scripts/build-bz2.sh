#!/bin/bash
# Build bzip2 with cosmocc for use with Python
set -euo pipefail

BZ2_VERSION="${BZ2_VERSION:-1.0.8}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

BZ2_URL="https://sourceware.org/pub/bzip2/bzip2-${BZ2_VERSION}.tar.gz"
BZ2_DIR="${WORK_DIR}/bzip2-${BZ2_VERSION}"

echo "Building bzip2 ${BZ2_VERSION} with cosmocc..."

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
if [ ! -d "${BZ2_DIR}" ]; then
  echo "Downloading bzip2 ${BZ2_VERSION}..."
  cd "${WORK_DIR}"
  curl -fsSL "${BZ2_URL}" -o "bzip2-${BZ2_VERSION}.tar.gz"
  tar xzf "bzip2-${BZ2_VERSION}.tar.gz"
  rm "bzip2-${BZ2_VERSION}.tar.gz"
fi

cd "${BZ2_DIR}"

# Clean any previous build
make clean 2>/dev/null || true

# Build libbz2.a (static library only)
# bzip2's Makefile is simple - we just override CC and AR
echo "Compiling bzip2..."
make libbz2.a \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Wall -Winline -O2 -D_FILE_OFFSET_BITS=64"

# Install to deps directory with multi-arch support
# cosmocc creates .aarch64/ subdirs for ARM64 objects
echo "Installing to ${DEPS_DIR}..."
cp libbz2.a "${DEPS_DIR}/lib/"
cp bzlib.h "${DEPS_DIR}/include/"

# Create aarch64 library if objects exist
# Use system ar for aarch64 archive since cosmoar expects different structure
if [ -d ".aarch64" ]; then
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  ar rcs "${DEPS_DIR}/lib/.aarch64/libbz2.a" .aarch64/*.o
  echo "  aarch64:  ${DEPS_DIR}/lib/.aarch64/libbz2.a"
fi

echo "bzip2 ${BZ2_VERSION} built successfully!"
echo "  Library: ${DEPS_DIR}/lib/libbz2.a"
echo "  Header:  ${DEPS_DIR}/include/bzlib.h"
ls -la "${DEPS_DIR}/lib/libbz2.a"
