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
FORCE_REBUILD="${2:-}"

if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version> [--force]"
  log_error "example: $0 3.12.8"
  log_error "example: $0 3.12.8 --force  # incremental rebuild"
  exit 1
fi

SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"
# Note: cosmocc names the build dir with x86_64 suffix but builds both archs
BUILD_DIR="${WORK_DIR}/build-${PYTHON_VERSION}-x86_64"

# Idempotency: skip if already built (unless --force)
if [ -f "${BUILD_DIR}/python.com" ] && [ "$FORCE_REBUILD" != "--force" ]; then
  log_skip "Python ${PYTHON_VERSION} already compiled at ${BUILD_DIR}/python.com"
  exit 0
fi

# Check source exists
if [ ! -d "${SRC_DIR}" ]; then
  log_error "Python source not found at ${SRC_DIR}"
  log_error "run 02-python/download.sh ${PYTHON_VERSION} first"
  exit 1
fi

# Apply patches from 02-python/all/ and 02-python/{version}/
# Uses -N (--forward) to skip already-applied patches
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"

apply_patches() {
  local patch_dir="$1"
  local label="${2:-}"
  
  [ -d "$patch_dir" ] || return 0
  
  for patch in "$patch_dir"/*.patch; do
    [ -f "$patch" ] || continue
    local patch_name
    patch_name=$(basename "$patch")
    if patch -p1 -N --dry-run < "$patch" >/dev/null 2>&1; then
      log_info "applying patch: ${patch_name}${label:+ ($label)}..."
      patch -p1 -N < "$patch"
    else
      log_info "patch already applied: ${patch_name}${label:+ ($label)}"
    fi
  done
}

cd "${SRC_DIR}"
apply_patches "${SCRIPT_DIR}/all"
apply_patches "${SCRIPT_DIR}/${PYTHON_MAJOR_MINOR}" "${PYTHON_MAJOR_MINOR}"

# Check dependencies
REQUIRED_LIBS=(
  "${DEPS_DIR}/lib/libssl.a"
  "${DEPS_DIR}/lib/libcrypto.a"
  "${DEPS_DIR}/lib/libreadline.a"
  "${DEPS_DIR}/lib/libncurses.a"
  "${DEPS_DIR}/lib/libffi.a"
  "${DEPS_DIR}/lib/libbz2.a"
  "${DEPS_DIR}/lib/liblzma.a"
  "${DEPS_DIR}/lib/libsqlite3.a"
  "${DEPS_DIR}/lib/libgdbm.a"
)

for lib in "${REQUIRED_LIBS[@]}"; do
  if [ ! -f "$lib" ]; then
    log_error "missing dependency: $lib"
    log_error "run all 01-deps/*.sh scripts first"
    exit 1
  fi
done

log_build "compiling Python ${PYTHON_VERSION} (fat APE: x86_64 + aarch64)"

# Config files (like Setup.local) are in 02-python/{version}/

# Setup compiler with cosmocc include paths only
# DO NOT mix system headers - they conflict with cosmopolitan
setup_cosmocc
export CFLAGS="-Os -I${COSMO_DIR}/include/third_party/zlib -I${DEPS_DIR}/include --sysroot=${COSMO_DIR}"
export LDFLAGS="-L${COSMO_DIR}/lib -L${DEPS_DIR}/lib"
export LIBS="-lreadline -ltinfo -lffi"

# Python 3.10's setup.py adds /usr/include to include paths unless cross-compiling.
# Setting _PYTHON_HOST_PLATFORM triggers cross-compile mode, and --sysroot above
# ensures sysroot_paths() won't find /usr/include (since $COSMO_DIR/usr/include
# doesn't exist). This prevents system header conflicts with cosmopolitan.
export _PYTHON_HOST_PLATFORM="cosmo"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Build out-of-tree
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# Disable modules that need headers/libraries not available or working in cosmocc
# - _tkinter: requires Tk/Tcl GUI toolkit (not portable)
# - _dbm: requires ndbm/gdbm library
# - _gdbm: requires GNU dbm library  
# - nis: deprecated, requires NIS/YP (network service)
# - _curses/_curses_panel: ncurses build incomplete, missing symbols
#   see: https://github.com/jart/cosmopolitan/tree/master/third_party/ncurses
cat > "${SRC_DIR}/Modules/Setup.local" << 'SETUP'
*disabled*
_tkinter
_dbm
nis
SETUP

# Skip configure if Makefile exists (for incremental rebuilds)
if [ ! -f "${BUILD_DIR}/Makefile" ]; then
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
  CURSES_CFLAGS="-I${DEPS_DIR}/include/ncurses" \
  CURSES_LIBS="-L${DEPS_DIR}/lib -lncursesw -ltinfow" \
  PANEL_CFLAGS="-I${DEPS_DIR}/include/ncurses" \
  PANEL_LIBS="-L${DEPS_DIR}/lib -lpanelw -lncursesw -ltinfow" \
  GDBM_CFLAGS="-I${DEPS_DIR}/include" \
  GDBM_LIBS="-L${DEPS_DIR}/lib -lgdbm" \
  OPENSSL_CFLAGS="-I${DEPS_DIR}/include" \
  OPENSSL_LIBS="-L${DEPS_DIR}/lib -lssl -lcrypto" \
  LIBFFI_CFLAGS="-I${DEPS_DIR}/include" \
  LIBFFI_LIBS="-L${DEPS_DIR}/lib -lffi" \
  LIBSQLITE3_CFLAGS="-I${DEPS_DIR}/include" \
  LIBSQLITE3_LIBS="-L${DEPS_DIR}/lib -lsqlite3"
else
  log_info "skipping configure (Makefile exists)"
fi

# For cosmopolitan, we need all modules built statically into the binary
#
# Python 3.11+ has Modules/Setup.stdlib which lists all modules
# Python 3.10 has most modules built by setup.py which uses -shared (unsupported)
# We provide a custom Setup.local.3.10 file with all modules listed for static build
log_info "patching for static module building..."

if [ -f "${BUILD_DIR}/Modules/Setup.stdlib" ]; then
  # Python 3.11+: Patch Setup.stdlib to use *static* instead of *shared*
  SETUP_FILE="${BUILD_DIR}/Modules/Setup.stdlib"
  sed -i 's/^\*shared\*/*static*/' "$SETUP_FILE"

  # Enable modules that configure might not have detected, and append library flags.
  # Setup.stdlib relies on makefile variables for flags, but those aren't set when
  # configure doesn't detect the library. We append -l flags directly.
  
  # readline
  sed -i 's/^#@MODULE_READLINE_TRUE@readline/readline/' "$SETUP_FILE"
  sed -i 's/^#readline /readline /' "$SETUP_FILE"
  sed -i "s|^\(readline .*\)$|\1 -L${DEPS_DIR}/lib -lreadline -ltinfo|" "$SETUP_FILE"
  
  # ctypes
  sed -i 's/^#@MODULE__CTYPES_TRUE@_ctypes/_ctypes/' "$SETUP_FILE"
  sed -i 's/^#_ctypes /_ctypes /' "$SETUP_FILE"
  sed -i "s|^\(_ctypes .*\)$|\1 -L${DEPS_DIR}/lib -lffi|" "$SETUP_FILE"
  
  # curses
  sed -i 's/^#@MODULE__CURSES_TRUE@_curses/_curses/' "$SETUP_FILE"
  sed -i 's/^#_curses /_curses /' "$SETUP_FILE"
  sed -i "s|^\(_curses .*\)$|\1 -L${DEPS_DIR}/lib -lncursesw -ltinfo|" "$SETUP_FILE"
  
  # curses panel
  sed -i 's/^#@MODULE__CURSES_PANEL_TRUE@_curses_panel/_curses_panel/' "$SETUP_FILE"
  sed -i 's/^#_curses_panel /_curses_panel /' "$SETUP_FILE"
  sed -i "s|^\(_curses_panel .*\)$|\1 -L${DEPS_DIR}/lib -lpanelw -lncursesw -ltinfo|" "$SETUP_FILE"
  
  # sqlite3 (our sqlite is built without shared cache support)
  sed -i 's/^#@MODULE__SQLITE3_TRUE@_sqlite3/_sqlite3/' "$SETUP_FILE"
  sed -i 's/^#_sqlite3 /_sqlite3 /' "$SETUP_FILE"
  sed -i "s|^\(_sqlite3 .*\)$|\1 -DSQLITE_OMIT_SHARED_CACHE -L${DEPS_DIR}/lib -lsqlite3|" "$SETUP_FILE"

  # Remove modules that need unavailable headers/libraries
  #
  # _crypt: Deprecated 3.11, removed 3.13 (PEP 594). Security concerns:
  #   - Only DES guaranteed (2^56 key space - extremely weak)
  #   - Not cross-platform (doesn't exist on Windows)
  #   - Can't interact with system passwords (must use PAM)
  #   - Better alternatives: hashlib.pbkdf2_hmac(), hashlib.scrypt()
  #   - Would require building libxcrypt for a deprecated insecure module
  #
  # _uuid: Requires libuuid (part of util-linux, complex to extract/build).
  #   Python's fallback is sufficient:
  #   - uuid4() (most common) uses os.urandom(), doesn't need libuuid
  #   - uuid1() fallback uses time.time_ns() + random + getnode()
  #   - Only downside: potential race under heavy multi-threaded uuid1()
  #   - superconfigure also skips libuuid
  #
  # _dbm: Requires ndbm library (part of glibc, not worth extracting).
  #   gdbm's --enable-libgdbm-compat provides ndbm API compatibility,
  #   but Python's _dbm module specifically wants ndbm.h which we don't have.
  #
  DISABLE_MODULES="_crypt _uuid _dbm"
  for mod in $DISABLE_MODULES; do
    sed -i "s/^${mod} /#${mod} /" "$SETUP_FILE"
  done
  
  cp "${BUILD_DIR}/Modules/Setup.stdlib" "${BUILD_DIR}/Modules/Setup.local"
else
  # Python 3.10: Use our custom Setup.local that lists all modules for static build
  # This is necessary because Python 3.10's setup.py builds modules as shared
  # libraries, which cosmocc doesn't support (-shared flag not available)
  SETUP_LOCAL="${SCRIPT_DIR}/${PYTHON_MAJOR_MINOR}/Setup.local"
  if [ -f "$SETUP_LOCAL" ]; then
    log_info "using custom Setup.local for Python ${PYTHON_MAJOR_MINOR}"
    # Substitute variables in the Setup.local file
    # Write to BUILD_DIR, not SRC_DIR - the Makefile expects it there
    sed -e "s|\$(srcdir)|${SRC_DIR}|g" \
        -e "s|-lz|-L${DEPS_DIR}/lib -L${COSMO_DIR}/lib -lz|g" \
        -e "s|-lbz2|-L${DEPS_DIR}/lib -lbz2|g" \
        -e "s|-llzma|-L${DEPS_DIR}/lib -llzma|g" \
        -e "s|-lssl|-L${DEPS_DIR}/lib -lssl|g" \
        -e "s|-lcrypto|-L${DEPS_DIR}/lib -lcrypto|g" \
        -e "s|-lsqlite3|-L${DEPS_DIR}/lib -lsqlite3|g" \
        -e "s|-lgdbm|-L${DEPS_DIR}/lib -lgdbm|g" \
        -e "s|-lffi|-L${DEPS_DIR}/lib -lffi|g" \
        -e "s|-lreadline|-L${DEPS_DIR}/lib -lreadline|g" \
        -e "s|-ltermcap|-L${DEPS_DIR}/lib -ltinfo|g" \
        "$SETUP_LOCAL" > "${BUILD_DIR}/Modules/Setup.local"
  else
    log_error "Setup.local not found for Python ${PYTHON_MAJOR_MINOR}"
    log_error "expected: ${SETUP_LOCAL}"
    exit 1
  fi
fi

# Regenerate Makefile
log_info "regenerating Makefile..."
make Makefile

# Python 3.14+: Fix HACL HMAC duplicate object file issue
# When building statically, LIBHACL_HMAC_OBJS includes all hash objects which
# causes "multiple definition" linker errors since those objects are also
# included by each individual hash module. Fix by removing the duplicates.
if grep -q "^LIBHACL_HMAC_LIB_SHARED=\$(LIBHACL_HMAC_OBJS)" Makefile 2>/dev/null; then
  log_info "patching Makefile for HACL static linking..."
  sed -i 's|^LIBHACL_HMAC_LIB_SHARED=.*|LIBHACL_HMAC_LIB_SHARED=Modules/_hacl/Hacl_HMAC.o Modules/_hacl/Hacl_Streaming_HMAC.o|' Makefile
fi

log_info "compiling (this may take several minutes)..."
# For Python 3.10, we need to add _math.o to the library manually
# since it's normally handled by setup.py for shared builds
if [ ! -f "${BUILD_DIR}/Modules/Setup.stdlib" ]; then
  # Build everything except the final link (library, objects, but not python binary)
  timed run_python_make -j"$(nproc)" "libpython${PYTHON_MAJOR_MINOR}.a" Modules/_math.o
  log_info "adding _math.o to library..."
  ${COSMO_DIR}/bin/cosmoar rcs "libpython${PYTHON_MAJOR_MINOR}.a" Modules/_math.o
  # Now build python binary
  timed run_python_make -j"$(nproc)" python
else
  timed run_python_make -j"$(nproc)"
fi

log_ok "Python ${PYTHON_VERSION} compiled"
log_info "  binary: ${BUILD_DIR}/python.com"
ls -lh "${BUILD_DIR}/python.com" 2>/dev/null || ls -lh "${BUILD_DIR}/python"
