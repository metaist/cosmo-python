#!/bin/bash
# Compile Python with cosmocc
#
# cosmocc automatically compiles for both x86_64 and aarch64 architectures,
# creating a "fat" APE binary that runs on both.
#
# Dependencies: all 01-deps/* must be built first
# Outputs: ${WORK_DIR}/build-${PYTHON_VERSION}-x86_64/python (fat APE)
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"

if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"
# Note: cosmocc names the build dir with x86_64 suffix but builds both archs
BUILD_DIR="${WORK_DIR}/build-${PYTHON_VERSION}-x86_64"

# Idempotency: skip if already built
if [ -f "${BUILD_DIR}/python.com" ]; then
  log_skip "Python ${PYTHON_VERSION} already compiled at ${BUILD_DIR}/python.com"
  exit 0
fi

# Check source exists
if [ ! -d "${SRC_DIR}" ]; then
  log_error "Python source not found at ${SRC_DIR}"
  log_error "run 00-setup/python-source.sh ${PYTHON_VERSION} first"
  exit 1
fi

# Check dependencies
REQUIRED_LIBS=(
  "${DEPS_DIR}/lib/libssl.a"
  "${DEPS_DIR}/lib/libcrypto.a"
  "${DEPS_DIR}/lib/libreadline.a"
  "${DEPS_DIR}/lib/libncurses.a"
  "${DEPS_DIR}/lib/libffi.a"
  "${DEPS_DIR}/lib/libbz2.a"
  "${DEPS_DIR}/lib/liblzma.a"
)

for lib in "${REQUIRED_LIBS[@]}"; do
  if [ ! -f "$lib" ]; then
    log_error "missing dependency: $lib"
    log_error "run all 01-deps/*.sh scripts first"
    exit 1
  fi
done

log_build "Python ${PYTHON_VERSION} for ${ARCH}"

# Apply Cosmopolitan-specific patches
SCRIPT_DIR="$(dirname "$0")"
PATCHES_DIR="${SCRIPT_DIR}/../../patches"

if [ -d "${PATCHES_DIR}" ]; then
  for patch in "${PATCHES_DIR}"/*.patch; do
    if [ -f "$patch" ]; then
      patch_name=$(basename "$patch")
      if ! grep -q "COSMO_PATCH_APPLIED_${patch_name}" "${SRC_DIR}/.cosmo_patches" 2>/dev/null; then
        log_info "applying patch: ${patch_name}"
        cd "${SRC_DIR}"
        patch -p1 < "$patch" || log_warn "patch may have already been applied"
        echo "COSMO_PATCH_APPLIED_${patch_name}" >> "${SRC_DIR}/.cosmo_patches"
        cd - > /dev/null
      fi
    fi
  done
fi

# Setup compiler with cosmocc include paths only
# DO NOT mix system headers - they conflict with cosmopolitan
export CC="${COSMO_DIR}/bin/cosmocc"
export CXX="${COSMO_DIR}/bin/cosmoc++"
export AR="${COSMO_DIR}/bin/cosmoar"
export CFLAGS="-Os -I${COSMO_DIR}/include/third_party/zlib -I${DEPS_DIR}/include"
export LDFLAGS="-L${COSMO_DIR}/lib -L${DEPS_DIR}/lib"
export LIBS="-lreadline -ltinfo -lffi"

if [ ! -x "${CC}" ]; then
  log_error "cosmocc not found at ${CC}"
  log_error "run 00-setup/cosmocc.sh first"
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
SETUP

log_info "configuring..."
# Set pkg-config vars to empty to prevent detection of system libs
"${SRC_DIR}/configure" \
  --disable-shared \
  --disable-ipv6 \
  --disable-loadable-sqlite-extensions \
  --disable-test-modules \
  --without-ensurepip \
  --without-system-expat \
  --with-lto=no \
  --prefix=/zip \
  ZLIB_CFLAGS="-I${COSMO_DIR}/include/third_party/zlib" \
  ZLIB_LIBS=" " \
  BZIP2_CFLAGS="-I${DEPS_DIR}/include" \
  BZIP2_LIBS="-L${DEPS_DIR}/lib -lbz2" \
  LIBLZMA_CFLAGS="-I${DEPS_DIR}/include" \
  LIBLZMA_LIBS="-L${DEPS_DIR}/lib -llzma" \
  LIBREADLINE_CFLAGS="-I${DEPS_DIR}/include" \
  LIBREADLINE_LIBS="-L${DEPS_DIR}/lib -lreadline -ltinfo" \
  CURSES_CFLAGS=" " \
  CURSES_LIBS=" " \
  PANEL_CFLAGS=" " \
  PANEL_LIBS=" " \
  GDBM_CFLAGS=" " \
  GDBM_LIBS=" " \
  OPENSSL_CFLAGS="-I${DEPS_DIR}/include" \
  OPENSSL_LIBS="-L${DEPS_DIR}/lib -lssl -lcrypto" \
  LIBFFI_CFLAGS="-I${DEPS_DIR}/include" \
  LIBFFI_LIBS="-L${DEPS_DIR}/lib -lffi"

# For cosmopolitan, we need all modules built statically into the binary
# Patch Setup.stdlib to use *static* instead of *shared*
log_info "patching for static module building..."
sed -i 's/^\*shared\*/*static*/' Modules/Setup.stdlib

# Enable modules that configure might not have detected
sed -i 's/^#@MODULE_READLINE_TRUE@readline/readline/' Modules/Setup.stdlib
sed -i 's/^#readline /readline /' Modules/Setup.stdlib
sed -i 's/^#@MODULE__CTYPES_TRUE@_ctypes/_ctypes/' Modules/Setup.stdlib
sed -i 's/^#_ctypes /_ctypes /' Modules/Setup.stdlib

# Remove modules that need unavailable headers
DISABLE_MODULES="_crypt _uuid _dbm _gdbm _curses _curses_panel"
for mod in $DISABLE_MODULES; do
  sed -i "s/^${mod} /#${mod} /" Modules/Setup.stdlib
done

cp Modules/Setup.stdlib Modules/Setup.local

# Regenerate Makefile
log_info "regenerating Makefile..."
make Makefile

log_info "compiling (this may take several minutes)..."
timed make -j"$(nproc)"

log_ok "Python ${PYTHON_VERSION} compiled"
log_info "  binary: ${BUILD_DIR}/python.com"
ls -lh "${BUILD_DIR}/python.com" 2>/dev/null || ls -lh "${BUILD_DIR}/python"
