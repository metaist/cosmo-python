#!/bin/bash
# Build all dependencies for cosmo-python
#
# This script:
#   1. Installs system dependencies (via apt)
#   2. Sets up cosmocc toolchain
#   3. Builds all library dependencies
#
# Dependencies are built in parallel when GNU parallel is available.
# ncurses must complete before readline (readline depends on ncurses).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/common.sh"

# Setup
"${ROOT_DIR}/scripts/00-setup/system-deps.sh"
"${ROOT_DIR}/scripts/00-setup/cosmocc.sh"

# Build dependencies
if command -v parallel >/dev/null 2>&1; then
  log_info "building dependencies in parallel..."
  
  # Wave 1: ncurses + all independent deps
  parallel --line-buffer --halt now,fail=1 ::: \
    "${SCRIPT_DIR}/ncurses.sh" \
    "${SCRIPT_DIR}/bz2.sh" \
    "${SCRIPT_DIR}/gdbm.sh" \
    "${SCRIPT_DIR}/libffi.sh" \
    "${SCRIPT_DIR}/openssl.sh" \
    "${SCRIPT_DIR}/sqlite.sh" \
    "${SCRIPT_DIR}/xz.sh"
  
  # Wave 2: readline (needs ncurses)
  "${SCRIPT_DIR}/readline.sh"
else
  log_info "building dependencies sequentially (install 'parallel' for faster builds)..."
  
  # ncurses must be built before readline
  "${SCRIPT_DIR}/ncurses.sh"
  "${SCRIPT_DIR}/readline.sh"
  
  # Remaining deps in any order
  "${SCRIPT_DIR}/bz2.sh"
  "${SCRIPT_DIR}/gdbm.sh"
  "${SCRIPT_DIR}/libffi.sh"
  "${SCRIPT_DIR}/openssl.sh"
  "${SCRIPT_DIR}/sqlite.sh"
  "${SCRIPT_DIR}/xz.sh"
fi

log_info "all dependencies built successfully"
