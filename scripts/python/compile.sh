#!/bin/bash
# Compile Python with cosmocc
#
# cosmocc automatically compiles for both x86_64 and aarch64 architectures,
# creating a "fat" APE binary that runs on both.
#
# Dependencies: all scripts/*.sh must be built first
# Outputs: ${WORK_DIR}/build-${PYTHON_VERSION}-x86_64/python (fat APE)
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
FORCE_REBUILD=""
ENABLE_COSMOEXT=""

# Parse arguments
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --force)
      FORCE_REBUILD="--force"
      ;;
    --cosmoext)
      ENABLE_COSMOEXT="1"
      ;;
    *)
      log_error "unknown option: $1"
      exit 1
      ;;
  esac
  shift
done

if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version> [--force] [--cosmoext]"
  log_error "example: $0 3.12.8"
  log_error "example: $0 3.12.8 --force        # incremental rebuild"
  log_error "example: $0 3.12.8 --cosmoext     # enable experimental cosmoext support"
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
  log_error "run scripts/python/download.sh ${PYTHON_VERSION} first"
  exit 1
fi

# Apply patches from scripts/python/all/ and scripts/python/{version}/
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
    log_error "run all scripts/*.sh.sh scripts first"
    exit 1
  fi
done

log_build "compiling Python ${PYTHON_VERSION} (fat APE: x86_64 + aarch64)"

# Config files (like Setup.local) are in scripts/python/{version}/

# Setup compiler with cosmocc include paths only
# DO NOT mix system headers - they conflict with cosmopolitan
setup_cosmocc
export CFLAGS="-Os -D__USE_SYSTEM_ENDIAN_H__ -I${COSMO_DIR}/include/third_party/zlib -I${DEPS_DIR}/include --sysroot=${COSMO_DIR}"
export LDFLAGS="-L${COSMO_DIR}/lib -L${DEPS_DIR}/lib"
export LIBS="-lreadline -ltinfo -lffi"

# Experimental cosmoext support
# When enabled, we add the C++ runtime to support C++ extensions like ujson.
# This adds ~1.5MB to the binary but enables loading C++ extensions at runtime.
if [ -n "$ENABLE_COSMOEXT" ]; then
  log_info "cosmoext support enabled (experimental)"
  log_info "adding C++ runtime for extension support (~1.5MB)"
  export LDFLAGS="${LDFLAGS} -Wl,--whole-archive -lcxx -Wl,--no-whole-archive"
fi

# Python 3.10's setup.py adds /usr/include to include paths unless cross-compiling.
# Setting _PYTHON_HOST_PLATFORM triggers cross-compile mode, and --sysroot above
# ensures sysroot_paths() won't find /usr/include (since $COSMO_DIR/usr/include
# doesn't exist). This prevents system header conflicts with cosmopolitan.
export _PYTHON_HOST_PLATFORM="cosmo"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run scripts/cosmocc.sh first"
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
# - _curses_panel: requires ncurses panel library (panel.h) which we don't build
#   see: https://github.com/jart/cosmopolitan/tree/master/third_party/ncurses
cat > "${SRC_DIR}/Modules/Setup.local" << 'SETUP'
*disabled*
_tkinter
_dbm
nis
_curses
_curses_panel
SETUP

# Skip configure if Makefile exists (for incremental rebuilds)
if [ ! -f "${BUILD_DIR}/Makefile" ]; then
  log_info "configuring..."
  
  # Set pkg-config vars to empty to prevent detection of system libs
  # Note: We do NOT use --host for cross-compilation because:
  # 1. It requires --with-build-python (a host Python to freeze modules)
  # 2. Cosmocc produces APE binaries that run on the build machine anyway
  # Instead, we patch Darwin-specific flags out of the Makefile after configure
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
  LIBSQLITE3_LIBS="-L${DEPS_DIR}/lib -lsqlite3" \
  LIBZSTD_CFLAGS="-I${DEPS_DIR}/include" \
  LIBZSTD_LIBS="-L${DEPS_DIR}/lib -lzstd" \

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
  sed_i 's/^\*shared\*/*static*/' "$SETUP_FILE"

  # Enable modules that configure might not have detected, and append library flags.
  # Setup.stdlib relies on makefile variables for flags, but those aren't set when
  # configure doesn't detect the library. We append -l flags directly.
  
  # readline
  sed_i 's/^#@MODULE_READLINE_TRUE@readline/readline/' "$SETUP_FILE"
  sed_i 's/^#readline /readline /' "$SETUP_FILE"
  sed_i "s|^\(readline .*\)$|\1 -L${DEPS_DIR}/lib -lreadline -ltinfo|" "$SETUP_FILE"
  
  # ctypes
  sed_i 's/^#@MODULE__CTYPES_TRUE@_ctypes/_ctypes/' "$SETUP_FILE"
  sed_i 's/^#_ctypes /_ctypes /' "$SETUP_FILE"
  sed_i "s|^\(_ctypes .*\)$|\1 -L${DEPS_DIR}/lib -lffi|" "$SETUP_FILE"
  
  # curses - DISABLED: ncurses build has missing _nc_fallback2 symbol
  # see: https://github.com/jart/cosmopolitan/tree/master/third_party/ncurses
  # TODO: Fix ncurses build to include fallback data
  # sed_i 's/^#@MODULE__CURSES_TRUE@_curses/_curses/' "$SETUP_FILE"
  # sed_i 's/^#_curses /_curses /' "$SETUP_FILE"
  # sed_i "s|^\(_curses .*\)$|\1 -L${DEPS_DIR}/lib -lncursesw -ltinfo|" "$SETUP_FILE"
  
  # curses panel - DISABLED: we don't build ncurses panel library
  # sed_i 's/^#@MODULE__CURSES_PANEL_TRUE@_curses_panel/_curses_panel/' "$SETUP_FILE"
  # sed_i 's/^#_curses_panel /_curses_panel /' "$SETUP_FILE"
  # sed_i "s|^\(_curses_panel .*\)$|\1 -L${DEPS_DIR}/lib -lpanelw -lncursesw -ltinfo|" "$SETUP_FILE"
  
  # sqlite3 (our sqlite is built without shared cache support)
  sed_i 's/^#@MODULE__SQLITE3_TRUE@_sqlite3/_sqlite3/' "$SETUP_FILE"
  sed_i 's/^#_sqlite3 /_sqlite3 /' "$SETUP_FILE"
  sed_i "s|^\(_sqlite3 .*\)$|\1 -DSQLITE_OMIT_SHARED_CACHE -L${DEPS_DIR}/lib -lsqlite3|" "$SETUP_FILE"

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
  # Disable modules that require unavailable headers/libraries:
  # - _crypt: Deprecated 3.11, removed 3.13 (requires libxcrypt, security concerns)
  # - _uuid: Requires libuuid (Python fallback is sufficient for uuid4)
  # - _dbm: Requires specific dbm libraries that conflict with gdbm
  # - _scproxy: macOS-only (SystemConfiguration framework for proxy settings)
  DISABLE_MODULES="_crypt _uuid _dbm _scproxy"
  for mod in $DISABLE_MODULES; do
    sed_i "s/^${mod} /#${mod} /" "$SETUP_FILE"
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

# Regenerate Modules/config.c to include all modules from Setup.local
# This is critical: configure generates config.c with only bootstrap modules,
# but we need all stdlib modules (math, datetime, etc.) to be built-in.
# Note: This also regenerates Makefile from Makefile.pre via makesetup,
# but does NOT run config.status (which would overwrite our Setup.local patches).
# 
# We must remove config.c to force regeneration, because configure generates
# both Makefile and config.c at the same time, and Makefile is a dependency.
log_info "regenerating config.c with all modules..."
rm -f Modules/config.c
make Modules/config.c

# macOS: Remove macOS-specific flags that configure adds when building on macOS
# Cosmopolitan doesn't support macOS frameworks or linker flags
if grep -q -- "-framework \|-Wl,-stack_size" Makefile 2>/dev/null; then
  log_info "removing macOS-specific flags from Makefile..."
  # Remove all -framework X flags (CoreFoundation, SystemConfiguration, etc.)
  sed_i 's/ -framework [A-Za-z_][A-Za-z_]*//g' Makefile
  # -Wl,-stack_size,N is macOS linker syntax; cosmocc sets stack size differently
  # Match with optional leading whitespace (tab or space) or start of value
  sed_i 's/-Wl,-stack_size,[0-9]* *//g' Makefile
fi

# Python 3.13+: Remove -latomic from LIBS
# Cosmopolitan provides atomic operations built-in; there's no separate libatomic
if grep -q "\-latomic" Makefile 2>/dev/null; then
  log_info "removing -latomic from Makefile..."
  sed_i 's/ -latomic//g' Makefile
fi

# Remove system libb2 references - we want Python's built-in blake2 implementation
# for portability. System libb2 might be detected via pkg-config on macOS/Linux.
if grep -q "HAVE_LIBB2" pyconfig.h 2>/dev/null; then
  log_info "removing system libb2 (using built-in blake2)..."
  # Remove from Makefile
  sed_i 's/MODULE__BLAKE2_CFLAGS=.*/MODULE__BLAKE2_CFLAGS=/g' Makefile
  sed_i 's/MODULE__BLAKE2_LDFLAGS=.*/MODULE__BLAKE2_LDFLAGS=/g' Makefile
  # Remove from pyconfig.h so code uses built-in implementation
  sed_i 's/#define HAVE_LIBB2 1/\/* #undef HAVE_LIBB2 *\//g' pyconfig.h
fi

# Experimental cosmoext support: copy _cosmoextmodule.c and add to Setup.local
# Note: We only ADD the module here. The actual config.c regeneration happens
# AFTER all Makefile patching is complete (see below)
if [ -n "$ENABLE_COSMOEXT" ]; then
  COSMOEXT_SRC="${SCRIPT_DIR}/../../src/cosmoext/_cosmoextmodule.c"
  if [ -f "$COSMOEXT_SRC" ]; then
    log_info "adding _cosmoext module (experimental)..."
    cp "$COSMOEXT_SRC" "${SRC_DIR}/Modules/_cosmoextmodule.c"
    echo "" >> "${BUILD_DIR}/Modules/Setup.local"
    echo "# Experimental cosmoext loader for dynamic C extension loading" >> "${BUILD_DIR}/Modules/Setup.local"
    echo "_cosmoext _cosmoextmodule.c" >> "${BUILD_DIR}/Modules/Setup.local"
  else
    log_error "_cosmoextmodule.c not found at ${COSMOEXT_SRC}"
    exit 1
  fi
fi

# Remove disabled modules from Makefile (they were already disabled in Setup.local,
# but configure bakes module lists into the Makefile before our patches apply)
# _scproxy is macOS-only (requires SystemConfiguration framework)
if grep -q "_scproxy" Makefile 2>/dev/null; then
  log_info "removing _scproxy module from Makefile..."
  # Remove from various module lists (space or end-of-line delimited)
  sed_i 's/ _scproxy / /g' Makefile
  sed_i 's/ _scproxy$//g' Makefile
  # Remove the build rules for _scproxy
  sed_i '/Modules\/_scproxy\.o:/d' Makefile
  # shellcheck disable=SC2016
  sed_i '/Modules\/_scproxy\$(EXT_SUFFIX)/d' Makefile
fi

# Python 3.11+: Fix _decimal module CFLAGS for libmpdec
# Configure can't detect 64-bit config for cross-compilation, so we set it manually.
# -DCONFIG_64: Use 64-bit limbs (uint64_t)
# -DHAVE_UINT128_T: Use __uint128_t for efficient 128-bit arithmetic
# -DANSI: Use standard C (not K&R)
# Note: $(srcdir) is a Makefile variable, not a shell variable
# Both MODULE__DECIMAL_CFLAGS (for _decimal.c) and LIBMPDEC_CFLAGS (for libmpdec/*.c) need patching
if grep -q "^MODULE__DECIMAL_CFLAGS=" Makefile 2>/dev/null; then
  log_info "patching Makefile for _decimal module..."
  # shellcheck disable=SC2016
  sed_i 's|^MODULE__DECIMAL_CFLAGS=.*|MODULE__DECIMAL_CFLAGS=-I$(srcdir)/Modules/_decimal/libmpdec -DCONFIG_64 -DANSI -DHAVE_UINT128_T|' Makefile
  # shellcheck disable=SC2016
  sed_i 's|^LIBMPDEC_CFLAGS=.*|LIBMPDEC_CFLAGS=-I$(srcdir)/Modules/_decimal/libmpdec -DCONFIG_64 -DANSI -DHAVE_UINT128_T $(PY_STDMODULE_CFLAGS) $(CCSHARED)|' Makefile
fi

# Python 3.14+: Fix HACL HMAC duplicate object file issue
# When building statically, LIBHACL_HMAC_OBJS includes all hash objects which
# causes "multiple definition" linker errors since those objects are also
# included by each individual hash module. Fix by removing the duplicates.
if grep -q "^LIBHACL_HMAC_LIB_SHARED=\$(LIBHACL_HMAC_OBJS)" Makefile 2>/dev/null; then
  log_info "patching Makefile for HACL static linking..."
  sed_i 's|^LIBHACL_HMAC_LIB_SHARED=.*|LIBHACL_HMAC_LIB_SHARED=Modules/_hacl/Hacl_HMAC.o Modules/_hacl/Hacl_Streaming_HMAC.o|' Makefile
fi

# Experimental cosmoext: add _cosmoext to config.c and Makefile
# Instead of regenerating with makesetup (which breaks many things), we manually
# patch the files to add just the _cosmoext module.
if [ -n "$ENABLE_COSMOEXT" ]; then
  log_info "patching config.c and Makefile for _cosmoext..."
  
  # Add extern declaration for PyInit__cosmoext to config.c
  sed_i 's|extern PyObject\* PyInit__string(void);|extern PyObject* PyInit__string(void);\nextern PyObject* PyInit__cosmoext(void);|' Modules/config.c
  
  # Add _cosmoext entry before the sentinel in _PyImport_Inittab
  sed_i 's|{0, 0}|{"_cosmoext", PyInit__cosmoext},\n    {0, 0}|' Modules/config.c
  
  # Add _cosmoext to MODOBJS in Makefile
  # shellcheck disable=SC2016
  sed_i 's|^MODOBJS=|MODOBJS=Modules/_cosmoextmodule.o |' Makefile
  
  # Add build rule for _cosmoextmodule.o
  # shellcheck disable=SC2016
  echo 'Modules/_cosmoextmodule.o: $(srcdir)/Modules/_cosmoextmodule.c $(MODULE_DEPS_STATIC) $(PYTHON_HEADERS); $(CC) $(PY_BUILTIN_MODULE_CFLAGS) -c $(srcdir)/Modules/_cosmoextmodule.c -o Modules/_cosmoextmodule.o' >> Makefile
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
  # Note: On case-insensitive filesystems (macOS), configure sets BUILDEXE=.exe
  timed run_python_make -j"$(nproc)" python.exe
else
  timed run_python_make -j"$(nproc)"
fi

# Rename to .com (cosmopolitan convention)
# On case-insensitive filesystems, configure produces python.exe instead of python.com
if [ -f "${BUILD_DIR}/python.exe" ] && [ ! -f "${BUILD_DIR}/python.com" ]; then
  log_info "renaming python.exe to python.com..."
  mv "${BUILD_DIR}/python.exe" "${BUILD_DIR}/python.com"
fi

log_ok "Python ${PYTHON_VERSION} compiled"
log_info "  binary: ${BUILD_DIR}/python.com"
ls -lh "${BUILD_DIR}/python.com" 2>/dev/null || ls -lh "${BUILD_DIR}/python"
