#!/bin/bash
# Build readline with cosmocc for use with Python
#
# Usage: ./readline.sh [VERSION] [--clean]
#
# Based on ahgamut/superconfigure's approach.
# Readline provides line editing for Python's interactive REPL.
#
# Dependencies: ncurses (run ncurses.sh first)
# Outputs: ${DEPS_DIR}/lib/libreadline.a, ${DEPS_DIR}/include/readline/
#
source "$(dirname "$0")/../common.sh"

# Parse arguments
parse_dep_args "readline" "$@"

READLINE_VERSION="$DEP_VERSION"
READLINE_SHA256="$(get_pkg_sha256 readline "$READLINE_VERSION")"
READLINE_URL="https://ftp.gnu.org/gnu/readline/readline-${READLINE_VERSION}.tar.gz"
READLINE_DIR="${WORK_DIR}/readline-${READLINE_VERSION}"

# Validate version exists
if [ "$READLINE_SHA256" = "null" ] || [ -z "$READLINE_SHA256" ]; then
  log_error "readline ${READLINE_VERSION} not found in versions.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "readline" "$READLINE_VERSION" \
    "${DEPS_DIR}/lib/libreadline.a" \
    "${DEPS_DIR}/lib/libhistory.a" \
    "${DEPS_DIR}/lib/.aarch64/libreadline.a" \
    "${DEPS_DIR}/include/readline"
fi

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libreadline.a" "readline ${READLINE_VERSION}"

# Check dependency
if [ ! -f "${DEPS_DIR}/lib/libncurses.a" ]; then
  log_error "ncurses not found at ${DEPS_DIR}/lib/libncurses.a"
  log_error "run 01-deps/ncurses.sh first"
  exit 1
fi

log_build "readline ${READLINE_VERSION}"

# Setup cosmocc
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${READLINE_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="readline-${READLINE_VERSION}.tar.gz"
  download_verify_gpg "readline" "${READLINE_VERSION}" "${READLINE_URL}" "${TARBALL}" "readline ${READLINE_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${READLINE_DIR}"

# Clean any previous build
make clean 2>/dev/null || true
make distclean 2>/dev/null || true

# Configure readline
# Key flags:
#   --disable-shared    Static only (required for Cosmopolitan)
#   --with-curses       Use ncurses for terminal handling
#
run_configure ./configure \
  --host=x86_64-linux \
  --disable-shared \
  --enable-static \
  --with-curses \
  --prefix="${DEPS_DIR}" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os -I${DEPS_DIR}/include -I${DEPS_DIR}/include/ncurses" \
  LDFLAGS="-L${DEPS_DIR}/lib"

log_info "compiling..."
timed run_dep_make -j"$(nproc)"

log_info "installing..."
make install

# Handle aarch64 if objects exist
if ls shlib/.aarch64/*.o 1> /dev/null 2>&1 || ls .aarch64/*.o 1> /dev/null 2>&1; then
  log_info "creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  READLINE_OBJS=$(find . -path "*/.aarch64/*.o" -name "*.o" 2>/dev/null)
  if [ -n "${READLINE_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libreadline.a" ${READLINE_OBJS}
  fi
fi

log_ok "readline ${READLINE_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libreadline.a"
log_info "  headers: ${DEPS_DIR}/include/readline/"
