#!/bin/bash
# Build Cosmopolitan Python
#
# This is the main orchestrator that runs all build phases in order.
# Each phase is idempotent - it will skip if outputs already exist.
#
# Usage:
#   ./scripts/build.sh <python_version>           # Build single version
#   ./scripts/build.sh <version1> <version2> ...  # Build multiple versions
#   ./scripts/build.sh --all                      # Build all versions from versions.json
#
# Examples:
#   ./scripts/build.sh 3.12.8
#   ./scripts/build.sh 3.11.11 3.12.8 3.13.1
#   ./scripts/build.sh --all
#
# Build phases:
#   00-setup     Download toolchain and Python source
#   01-deps      Build dependencies (ncurses, readline, openssl, etc.)
#   02-python    Compile Python
#   03-package   Create distributable archive
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Parse arguments
VERSIONS=()

if [ $# -eq 0 ]; then
  log_error "usage: $0 <python_version> [version2 ...]"
  log_error "       $0 --all"
  exit 1
fi

if [ "$1" = "--all" ]; then
  # Read versions from versions.json using jq
  if [ ! -f "$VERSIONS_FILE" ]; then
    log_error "versions.json not found at $VERSIONS_FILE"
    exit 1
  fi
  
  # Extract all Python versions from .python.versions
  mapfile -t VERSIONS < <(jq -r '.python.versions | keys[]' "$VERSIONS_FILE")
  
  if [ ${#VERSIONS[@]} -eq 0 ]; then
    log_error "no versions found in versions.json"
    exit 1
  fi
  log_info "building all versions: ${VERSIONS[*]}"
else
  VERSIONS=("$@")
fi

# Track timing
BUILD_START=$(date +%s)

echo ""
echo "========================================"
echo "  Cosmopolitan Python Build"
echo "========================================"
echo ""
echo "  Versions: ${VERSIONS[*]}"
echo "  Work dir: ${WORK_DIR}"
echo "  Dist dir: ${DIST_DIR}"
echo ""

#
# Phase 0: Setup
#
echo ""
echo "========================================"
echo "  Phase 0: Setup"
echo "========================================"

log_info "checking system dependencies..."
"${SCRIPT_DIR}/00-setup/system-deps.sh"

log_info "setting up cosmocc toolchain..."
"${SCRIPT_DIR}/00-setup/cosmocc.sh"

for version in "${VERSIONS[@]}"; do
  log_info "downloading Python ${version} source..."
  "${SCRIPT_DIR}/00-setup/python-source.sh" "${version}"
done

#
# Phase 1: Dependencies
#
echo ""
echo "========================================"
echo "  Phase 1: Dependencies"
echo "========================================"

# Order matters! ncurses must be built before readline
log_info "building ncurses..."
"${SCRIPT_DIR}/01-deps/ncurses.sh"

log_info "building readline..."
"${SCRIPT_DIR}/01-deps/readline.sh"

# These can be built in any order
log_info "building openssl..."
"${SCRIPT_DIR}/01-deps/openssl.sh"

log_info "building libffi..."
"${SCRIPT_DIR}/01-deps/libffi.sh"

log_info "building bzip2..."
"${SCRIPT_DIR}/01-deps/bz2.sh"

log_info "building xz/liblzma..."
"${SCRIPT_DIR}/01-deps/xz.sh"

log_info "building sqlite..."
"${SCRIPT_DIR}/01-deps/sqlite.sh"

#
# Phase 2: Compile Python
#
echo ""
echo "========================================"
echo "  Phase 2: Compile Python"
echo "========================================"

for version in "${VERSIONS[@]}"; do
  log_info "compiling Python ${version}..."
  "${SCRIPT_DIR}/02-python/compile.sh" "${version}"
done

#
# Phase 3: Package
#
echo ""
echo "========================================"
echo "  Phase 3: Package"
echo "========================================"

for version in "${VERSIONS[@]}"; do
  log_info "packaging Python ${version}..."
  "${SCRIPT_DIR}/03-package/package.sh" "${version}"
done

#
# Summary
#
BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))

echo ""
echo "========================================"
echo "  Build Complete"
echo "========================================"
echo ""
echo "  Duration: $((BUILD_DURATION / 60))m $((BUILD_DURATION % 60))s"
echo ""
echo "  Artifacts:"
for artifact in "${DIST_DIR}"/python-*-cosmo-*.com; do
  if [ -f "$artifact" ]; then
    size=$(du -h "$artifact" | cut -f1)
    echo "    $(basename "$artifact") ($size)"
  fi
done
echo ""
echo "  To generate a release manifest:"
echo "    ./scripts/03-package/manifest.sh <release-tag>"
echo ""
