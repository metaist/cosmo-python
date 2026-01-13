#!/bin/bash
# Build readline with cosmocc for use with Python
#
# Based on ahgamut/superconfigure's approach.
# Readline provides line editing for Python's interactive REPL.
#
# DEPENDENCY: Requires ncurses to be built first (run build-ncurses.sh)
#
set -euo pipefail

READLINE_VERSION="${READLINE_VERSION:-8.2}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

READLINE_URL="https://mirrors.ocf.berkeley.edu/gnu/readline/readline-${READLINE_VERSION}.tar.gz"
READLINE_DIR="${WORK_DIR}/readline-${READLINE_VERSION}"

echo "Building readline ${READLINE_VERSION} with cosmocc..."

# Check for ncurses dependency
if [ ! -f "${DEPS_DIR}/lib/libncurses.a" ] && [ ! -f "${DEPS_DIR}/lib/libncursesw.a" ]; then
  echo "Error: ncurses not found at ${DEPS_DIR}/lib/"
  echo "Run build-ncurses.sh first"
  exit 1
fi

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
if [ ! -d "${READLINE_DIR}" ]; then
  echo "Downloading readline ${READLINE_VERSION}..."
  cd "${WORK_DIR}"
  curl -fsSL "${READLINE_URL}" -o "readline-${READLINE_VERSION}.tar.gz"
  tar xzf "readline-${READLINE_VERSION}.tar.gz"
  rm "readline-${READLINE_VERSION}.tar.gz"
fi

cd "${READLINE_DIR}"

# Apply input.c patch if not already applied
# This disables the select/pselect-based input checking that doesn't work reliably with Cosmopolitan
# We make _rl_input_available() always return 0 (no input available)
INPUT_C="input.c"
if [ -f "${INPUT_C}" ] && ! grep -q "COSMO_PATCH" "${INPUT_C}"; then
  echo "Applying input.c patch..."
  # Insert "return 0; /* COSMO_PATCH */" right after the function opening brace
  # This skips all the select/pselect code that doesn't work with Cosmopolitan
  sed -i '/_rl_input_available (void)/{n;s/{/{\n  return 0; \/* COSMO_PATCH: skip select\/pselect code *\//}' "${INPUT_C}"
fi

# Clean any previous build
make clean 2>/dev/null || true
make distclean 2>/dev/null || true

# Configure readline
# Key flags:
#   --disable-shared     Static only
#   --enable-multibyte   UTF-8 support
#   --with-curses        Use ncurses for terminal handling
#
echo "Configuring readline..."
./configure \
  --host=x86_64-linux \
  --disable-shared \
  --enable-static \
  --enable-multibyte \
  --with-curses \
  --prefix="${DEPS_DIR}" \
  CC="${CC}" \
  AR="${AR}" \
  RANLIB="${RANLIB}" \
  CFLAGS="-Os -I${DEPS_DIR}/include -I${DEPS_DIR}/include/ncurses" \
  LDFLAGS="-L${DEPS_DIR}/lib"

echo "Compiling readline..."
make -j"$(nproc)"

echo "Installing to ${DEPS_DIR}..."
make install

# Handle aarch64 if objects exist
if find . -name ".aarch64" -type d 2>/dev/null | head -1 | grep -q .; then
  echo "Creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"

  READLINE_OBJS=$(find . -path "*/.aarch64/*.o" -name "*.o" 2>/dev/null || true)
  if [ -n "${READLINE_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libreadline.a" ${READLINE_OBJS}
    echo "  Created: ${DEPS_DIR}/lib/.aarch64/libreadline.a"
  fi
fi

echo ""
echo "readline ${READLINE_VERSION} built successfully!"
echo "  Library: ${DEPS_DIR}/lib/libreadline.a"
echo "  Headers: ${DEPS_DIR}/include/readline/"
ls -la "${DEPS_DIR}/lib/libreadline.a"
