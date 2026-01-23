#!/bin/bash
# Build SQLite with cosmocc for use with Python's _sqlite3 module
#
# Usage: ./sqlite.sh [VERSION] [--clean]
#
# SQLite is the most widely deployed database engine and is used by
# many Python applications and frameworks.
#
# Dependencies: cosmocc
# Outputs: ${DEPS_DIR}/lib/libsqlite3.a, ${DEPS_DIR}/include/sqlite3.h
#
source "$(dirname "$0")/common.sh"

# Parse arguments
parse_dep_args "sqlite" "$@"

SQLITE_VERSION="$DEP_VERSION"
SQLITE_SHA256="$(get_pkg_sha256 sqlite "$SQLITE_VERSION")"
SQLITE_AUTOCONF="$(sqlite_autoconf "$SQLITE_VERSION")"
SQLITE_URL="$(get_pkg_url sqlite "$SQLITE_VERSION")"
SQLITE_DIR="${WORK_DIR}/sqlite-autoconf-${SQLITE_AUTOCONF}"

# Validate version exists
if [ "$SQLITE_SHA256" = "null" ] || [ -z "$SQLITE_SHA256" ]; then
  log_error "sqlite ${SQLITE_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "sqlite-autoconf-${SQLITE_AUTOCONF}" "" \
    "${DEPS_DIR}/lib/libsqlite3.a" \
    "${DEPS_DIR}/lib/.aarch64/libsqlite3.a" \
    "${DEPS_DIR}/include/sqlite3.h" \
    "${DEPS_DIR}/include/sqlite3ext.h"
fi

# Idempotency: skip if already built
skip_if_all_exist "sqlite ${SQLITE_VERSION}" \
  "${DEPS_DIR}/lib/libsqlite3.a" \
  "${DEPS_DIR}/include/sqlite3.h"

log_build "sqlite ${SQLITE_VERSION}"

# Setup cosmocc
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run scripts/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${SQLITE_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="sqlite-autoconf-${SQLITE_AUTOCONF}.tar.gz"
  download_verify_gpg "sqlite" "${SQLITE_VERSION}" "${SQLITE_URL}" "${TARBALL}" "sqlite ${SQLITE_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${SQLITE_DIR}"

# Clean any previous build
make clean 2>/dev/null || true

# Configure SQLite
# Key flags:
#   --disable-shared         - Static library only
#   --disable-load-extension - No dlopen for loading extensions at runtime
#   CFLAGS includes recommended options from SQLite docs
#
run_configure ./configure \
  --host=x86_64-linux \
  --disable-shared \
  --disable-load-extension \
  --prefix="${DEPS_DIR}" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os -DSQLITE_DQS=0 -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_DEFAULT_WAL_SYNCHRONOUS=1 -DSQLITE_LIKE_DOESNT_MATCH_BLOBS -DSQLITE_OMIT_DEPRECATED -DSQLITE_OMIT_SHARED_CACHE -DSQLITE_OMIT_LOAD_EXTENSION"

log_info "compiling..."
timed run_dep_make -j"$(nproc)"

log_info "installing..."
make install

# Handle aarch64 objects if they exist (for fat binary support)
# cosmocc creates .aarch64/sqlite3.o alongside sqlite3.o
if [ -f ".aarch64/sqlite3.o" ]; then
  log_info "creating aarch64 library..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  "${COSMO_DIR}/bin/aarch64-linux-cosmo-ar" rcs "${DEPS_DIR}/lib/.aarch64/libsqlite3.a" .aarch64/sqlite3.o
fi

log_ok "sqlite ${SQLITE_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libsqlite3.a"
log_info "  header:  ${DEPS_DIR}/include/sqlite3.h"
