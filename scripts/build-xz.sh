#!/bin/bash
# Build xz/liblzma with cosmocc for use with Python
set -euo pipefail

XZ_VERSION="${XZ_VERSION:-5.4.5}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

XZ_URL="https://tukaani.org/xz/xz-${XZ_VERSION}.tar.gz"
XZ_DIR="${WORK_DIR}/xz-${XZ_VERSION}"

echo "Building xz/liblzma ${XZ_VERSION} with cosmocc..."

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
if [ ! -d "${XZ_DIR}" ]; then
  echo "Downloading xz ${XZ_VERSION}..."
  cd "${WORK_DIR}"
  curl -fsSL "${XZ_URL}" -o "xz-${XZ_VERSION}.tar.gz"
  tar xzf "xz-${XZ_VERSION}.tar.gz"
  rm "xz-${XZ_VERSION}.tar.gz"
fi

cd "${XZ_DIR}"

# Clean any previous build
make clean 2>/dev/null || true
make distclean 2>/dev/null || true

# Configure for static library only
echo "Configuring xz..."
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
echo "Compiling liblzma..."
make -C src/liblzma -j"$(nproc)"

# Install to deps directory
echo "Installing to ${DEPS_DIR}..."
cp src/liblzma/.libs/liblzma.a "${DEPS_DIR}/lib/"
cp -r src/liblzma/api/lzma.h src/liblzma/api/lzma "${DEPS_DIR}/include/"

# Create aarch64 library if objects exist
if [ -d "src/liblzma/.libs/.aarch64" ]; then
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  # Find all .o files in aarch64 subdirs and create archive
  find src/liblzma -path "*/.aarch64/*.o" -exec ar rcs "${DEPS_DIR}/lib/.aarch64/liblzma.a" {} +
  echo "  aarch64: ${DEPS_DIR}/lib/.aarch64/liblzma.a"
elif [ -d "src/liblzma/api/.aarch64" ] || find src/liblzma -name ".aarch64" -type d | head -1 | grep -q .; then
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  find src/liblzma -path "*/.aarch64/*.o" -exec ar rcs "${DEPS_DIR}/lib/.aarch64/liblzma.a" {} + 2>/dev/null || true
  if [ -f "${DEPS_DIR}/lib/.aarch64/liblzma.a" ]; then
    echo "  aarch64: ${DEPS_DIR}/lib/.aarch64/liblzma.a"
  fi
fi

echo "xz/liblzma ${XZ_VERSION} built successfully!"
echo "  Library: ${DEPS_DIR}/lib/liblzma.a"
echo "  Headers: ${DEPS_DIR}/include/lzma.h"
ls -la "${DEPS_DIR}/lib/liblzma.a"
