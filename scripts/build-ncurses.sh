#!/bin/bash
# Build ncurses with cosmocc for use with Python readline
#
# Based on ahgamut/superconfigure's approach.
# Ncurses provides terminal handling for readline's line editing.
#
set -euo pipefail

NCURSES_VERSION="${NCURSES_VERSION:-6.4}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

NCURSES_URL="https://mirrors.ocf.berkeley.edu/gnu/ncurses/ncurses-${NCURSES_VERSION}.tar.gz"
NCURSES_DIR="${WORK_DIR}/ncurses-${NCURSES_VERSION}"

echo "Building ncurses ${NCURSES_VERSION} with cosmocc..."

# Setup cosmocc
export CC="${COSMO_DIR}/bin/cosmocc"
export CXX="${COSMO_DIR}/bin/cosmoc++"
export AR="${COSMO_DIR}/bin/cosmoar"
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${CC}" ]; then
  echo "Error: cosmocc not found at ${CC}"
  echo "Run setup-cosmocc.sh first"
  exit 1
fi

mkdir -p "${WORK_DIR}" "${DEPS_DIR}/lib" "${DEPS_DIR}/include"

# Download if needed
if [ ! -d "${NCURSES_DIR}" ]; then
  echo "Downloading ncurses ${NCURSES_VERSION}..."
  cd "${WORK_DIR}"
  curl -fsSL "${NCURSES_URL}" -o "ncurses-${NCURSES_VERSION}.tar.gz"
  tar xzf "ncurses-${NCURSES_VERSION}.tar.gz"
  rm "ncurses-${NCURSES_VERSION}.tar.gz"
fi

cd "${NCURSES_DIR}"

# Apply Cosmopolitan unicode patch if not already applied
PRIV_H="ncurses/curses.priv.h"
if [ -f "${PRIV_H}" ] && ! grep -q "__COSMOPOLITAN__" "${PRIV_H}"; then
  echo "Applying Cosmopolitan unicode patch..."
  # Add include for Cosmopolitan's unicode support
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
echo "Configuring ncurses..."
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

echo "Compiling ncurses..."
make -j"$(nproc)"

echo "Installing to ${DEPS_DIR}..."
make install

# Create symlinks from wide-character variants to standard names
# (readline and other programs expect libncurses.a, not libncursesw.a)
echo "Creating compatibility symlinks..."
cd "${DEPS_DIR}/lib"
ln -sf libncursesw.a libncurses.a 2>/dev/null || true
ln -sf libformw.a libform.a 2>/dev/null || true
ln -sf libmenuw.a libmenu.a 2>/dev/null || true
ln -sf libpanelw.a libpanel.a 2>/dev/null || true
ln -sf libtinfow.a libtinfo.a 2>/dev/null || true

cd "${DEPS_DIR}/include"
rm -rf ncurses 2>/dev/null || true
ln -sf ncursesw ncurses 2>/dev/null || true

# Handle aarch64 if objects exist
if [ -d "${NCURSES_DIR}/objects/.aarch64" ]; then
  echo "Creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"
  cd "${NCURSES_DIR}"
  find objects/.aarch64 -name "*.o" -exec ar rcs "${DEPS_DIR}/lib/.aarch64/libncursesw.a" {} +
  cd "${DEPS_DIR}/lib/.aarch64"
  ln -sf libncursesw.a libncurses.a 2>/dev/null || true
  ln -sf libncursesw.a libtinfo.a 2>/dev/null || true
  echo "  Created: ${DEPS_DIR}/lib/.aarch64/libncursesw.a (with symlinks)"
fi

echo ""
echo "ncurses ${NCURSES_VERSION} built successfully!"
echo "  Libraries: ${DEPS_DIR}/lib/libncurses.a"
echo "  Headers:   ${DEPS_DIR}/include/ncurses/"
ls -la "${DEPS_DIR}/lib/libncurses"*.a 2>/dev/null || ls -la "${DEPS_DIR}/lib/libncursesw.a"
