#!/bin/bash
# Build ncurses with cosmocc for use with Python readline
#
# Based on ahgamut/superconfigure's approach.
# Ncurses provides terminal handling for readline's line editing.
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libncurses.a, ${DEPS_DIR}/include/ncurses/
#
source "$(dirname "$0")/../common.sh"

# Get version and checksum from versions.json
NCURSES_VERSION="${NCURSES_VERSION:-$(get_dep_version ncurses)}"
NCURSES_SHA256="$(get_dep_sha256 ncurses)"
NCURSES_URL="https://ftp.gnu.org/gnu/ncurses/ncurses-${NCURSES_VERSION}.tar.gz"
NCURSES_DIR="${WORK_DIR}/ncurses-${NCURSES_VERSION}"

ensure_dirs

# Idempotency: skip if already built
skip_if_exists "${DEPS_DIR}/lib/libncurses.a" "ncurses ${NCURSES_VERSION}"

log_build "ncurses ${NCURSES_VERSION}"

# Setup cosmocc (with ccache if available)
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${NCURSES_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="ncurses-${NCURSES_VERSION}.tar.gz"
  download_and_verify "${NCURSES_URL}" "${TARBALL}" "${NCURSES_SHA256}" "ncurses ${NCURSES_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${NCURSES_DIR}"

# Apply Cosmopolitan unicode patch if not already applied
PRIV_H="ncurses/curses.priv.h"
if [ -f "${PRIV_H}" ] && ! grep -q "__COSMOPOLITAN__" "${PRIV_H}"; then
  log_info "applying Cosmopolitan unicode patch..."
  sed -i '/#include <nc_panel.h>/a\
#ifdef __COSMOPOLITAN__\
#include "libc/str/unicode.h"\
#endif' "${PRIV_H}"
fi

# Clean any previous build
make clean 2>/dev/null || true
make distclean 2>/dev/null || true

# Configure ncurses
# Key flags:
#   --without-shared    Static only (required for Cosmopolitan)
#   --enable-widec      Wide character support (UTF-8)
#   --with-fallbacks    Include common terminal definitions in binary
#   --disable-termcap   Don't use termcap compatibility
#
log_info "configuring..."

./configure \
  --host=x86_64-linux \
  --without-libtool \
  --without-shared \
  --with-normal \
  --without-debug \
  --disable-relink \
  --disable-rpath \
  --disable-termcap \
  --disable-mixed-case \
  --without-ada \
  --without-cxx \
  --without-cxx-binding \
  --without-tests \
  --with-termlib \
  --with-ticlib \
  --without-dlsym \
  --without-pcre2 \
  --without-manpages \
  --without-tack \
  --with-curses-h \
  --disable-stripping \
  --enable-widec \
  --enable-ext-colors \
  --enable-ext-mouse \
  --enable-sp-funcs \
  --enable-colorfgbg \
  --enable-tcap-names \
  --with-fallbacks=xterm,xterm-256color,screen-256color,linux,vt100 \
  --prefix="${DEPS_DIR}" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os"

log_info "compiling..."
timed make -j"$(nproc)"

log_info "installing..."
make install

# Create symlinks from wide-character variants to standard names
# (readline and other programs expect libncurses.a, not libncursesw.a)
log_info "creating compatibility symlinks..."
cd "${DEPS_DIR}/lib"
ln -sf libncursesw.a libncurses.a 2>/dev/null || true
ln -sf libformw.a libform.a 2>/dev/null || true
ln -sf libmenuw.a libmenu.a 2>/dev/null || true
ln -sf libpanelw.a libpanel.a 2>/dev/null || true
ln -sf libtinfow.a libtinfo.a 2>/dev/null || true

cd "${DEPS_DIR}/include"
rm -rf ncurses 2>/dev/null || true
ln -sf ncursesw ncurses 2>/dev/null || true

# Create top-level symlinks for headers that Python configure looks for
# (Python's configure doesn't use CURSES_CFLAGS for header detection)
ln -sf ncurses/curses.h curses.h 2>/dev/null || true
ln -sf ncurses/ncurses.h ncurses.h 2>/dev/null || true
ln -sf ncurses/panel.h panel.h 2>/dev/null || true
ln -sf ncurses/term.h term.h 2>/dev/null || true

# Handle aarch64 if objects exist
if [ -d "${NCURSES_DIR}/objects/.aarch64" ]; then
  log_info "creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  cd "${NCURSES_DIR}"
  find objects/.aarch64 -name "*.o" -exec ar rcs "${DEPS_DIR}/lib/.aarch64/libncursesw.a" {} +
  cd "${DEPS_DIR}/lib/.aarch64"
  # Create all the symlinks that x86_64 has
  ln -sf libncursesw.a libncurses.a 2>/dev/null || true
  ln -sf libncursesw.a libtinfo.a 2>/dev/null || true
  ln -sf libncursesw.a libtinfow.a 2>/dev/null || true
  ln -sf libncursesw.a libpanelw.a 2>/dev/null || true
  ln -sf libncursesw.a libpanel.a 2>/dev/null || true
  ln -sf libncursesw.a libformw.a 2>/dev/null || true
  ln -sf libncursesw.a libform.a 2>/dev/null || true
  ln -sf libncursesw.a libmenuw.a 2>/dev/null || true
  ln -sf libncursesw.a libmenu.a 2>/dev/null || true
  ln -sf libncursesw.a libticw.a 2>/dev/null || true
fi

log_ok "ncurses ${NCURSES_VERSION} installed"
log_info "  library: ${DEPS_DIR}/lib/libncurses.a"
log_info "  headers: ${DEPS_DIR}/include/ncurses/"
