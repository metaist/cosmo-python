#!/bin/bash
# Build Python with cosmocc
set -euo pipefail

PYTHON_VERSION="${1:-3.12.8}"
ARCH="${2:-x86_64}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"
BUILD_DIR="${WORK_DIR}/build-${ARCH}"

if [ ! -d "${SRC_DIR}" ]; then
  echo "Error: Python source not found at ${SRC_DIR}"
  echo "Run download-python.sh first"
  exit 1
fi

echo "Building Python ${PYTHON_VERSION} for ${ARCH}..."

# Setup compiler with cosmocc include paths only
# DO NOT mix system headers - they conflict with cosmopolitan
export CC="${COSMO_DIR}/bin/cosmocc"
export CXX="${COSMO_DIR}/bin/cosmoc++"
export AR="${COSMO_DIR}/bin/cosmoar"
export CFLAGS="-Os -I${COSMO_DIR}/include/third_party/zlib -I${DEPS_DIR}/include"
export LDFLAGS="-L${COSMO_DIR}/lib -L${DEPS_DIR}/lib"

# Verify cosmocc exists
if [ ! -x "${CC}" ]; then
  echo "Error: cosmocc not found at ${CC}"
  echo "Run setup-cosmocc.sh first"
  exit 1
fi

# Build out-of-tree
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# Disable modules that need headers cosmocc doesn't have
cat > "${SRC_DIR}/Modules/Setup.local" << 'SETUP'
*disabled*
_tkinter
_dbm
_gdbm
nis
_curses
_curses_panel
readline
_ctypes
_ctypes_test
SETUP

echo "Configuring..."
# Set pkg-config vars to empty to prevent detection of system libs
"${SRC_DIR}/configure" \
  --disable-shared \
  --disable-ipv6 \
  --disable-loadable-sqlite-extensions \
  --disable-test-modules \
  --without-ensurepip \
  --without-system-expat \
  --without-system-ffi \
  --with-lto=no \
  --prefix=/zip \
  ZLIB_CFLAGS="-I${COSMO_DIR}/include/third_party/zlib" \
  ZLIB_LIBS=" " \
  BZIP2_CFLAGS="-I${DEPS_DIR}/include" \
  BZIP2_LIBS="-L${DEPS_DIR}/lib -lbz2" \
  LIBLZMA_CFLAGS="-I${DEPS_DIR}/include" \
  LIBLZMA_LIBS="-L${DEPS_DIR}/lib -llzma" \
  LIBREADLINE_CFLAGS=" " \
  LIBREADLINE_LIBS=" " \
  CURSES_CFLAGS=" " \
  CURSES_LIBS=" " \
  PANEL_CFLAGS=" " \
  PANEL_LIBS=" " \
  GDBM_CFLAGS=" " \
  GDBM_LIBS=" "

# For cosmopolitan, we need all modules built statically into the binary
# Patch Setup.stdlib to use *static* instead of *shared*
echo "Patching Setup.stdlib for static module building..."
sed -i 's/^\*shared\*/*static*/' Modules/Setup.stdlib

# Remove modules that need unavailable headers from Setup.stdlib
echo "Removing unavailable modules from Setup.stdlib..."

# List of modules to remove (need headers cosmocc doesn't have)
DISABLE_MODULES="readline _ctypes _ctypes_test _crypt _uuid _dbm _gdbm _ssl _hashlib"

for mod in $DISABLE_MODULES; do
  # Comment out the module line in Setup.stdlib
  sed -i "s/^${mod} /#${mod} /" Modules/Setup.stdlib
done

# Copy patched Setup.stdlib to Setup.local so makesetup uses it
cp Modules/Setup.stdlib Modules/Setup.local

# Regenerate Makefile to pick up Setup.local changes
echo "Regenerating Makefile with static modules..."
make Makefile

echo "Building..."
make -j"$(nproc)"

echo "Build complete: ${BUILD_DIR}"
ls -la python* 2>/dev/null || ls -la Programs/python* 2>/dev/null || echo "Binary location may vary"
