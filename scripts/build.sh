#!/bin/bash
# Build Cosmopolitan Python
#
# This is the main orchestrator that runs all build phases in order.
# Each phase is idempotent - it will skip if outputs already exist.
#
# Usage:
#   ./scripts/build.sh <python_version>           # Build single version
#   ./scripts/build.sh <version1> <version2> ...  # Build multiple versions
#   ./scripts/build.sh --all                      # Build all versions
#
# Examples:
#   ./scripts/build.sh 3.12.8
#   ./scripts/build.sh 3.11.11 3.12.8 3.13.1
#   ./scripts/build.sh --all
#
# Build phases:
#   1: Deps       System deps, cosmocc, library dependencies
#   2: Python     Download, compile, package Python
#   3: Test       Run smoke tests
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
  all_versions=$($CDX_CLI versions)
  
  if [ -z "$all_versions" ]; then
    log_error "no versions found in upstream.cdx.json"
    exit 1
  fi
  
  read -ra VERSIONS <<< "$all_versions"
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

# Print diagnostics if VERBOSE is set or if running in CI
if [ "${VERBOSE:-}" = "1" ] || [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
  print_diagnostics
fi

echo ""
echo "========================================"
echo "  Phase 1: Dependencies"
echo "========================================"

${SCRIPT_DIR}/01-deps/build.sh

echo ""
echo "========================================"
echo "  Phase 2: Python"
echo "========================================"

for version in "${VERSIONS[@]}"; do
  "${SCRIPT_DIR}/02-python/build.sh" "${version}"
done

echo ""
echo "========================================"
echo "  Phase 3: Smoke Tests"
echo "========================================"

for version in "${VERSIONS[@]}"; do
  BINARY="${DIST_DIR}/python-${version}-cosmo.com"

  if [ -f "$BINARY" ]; then
    log_info "testing Python ${version}..."
    "${SCRIPT_DIR}/02-python/smoke.sh" "${BINARY}"
  else
    log_error "binary not found: ${BINARY}"
    exit 1
  fi
done

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
for artifact in "${DIST_DIR}"/python-*-cosmo.com; do
  if [ -f "$artifact" ]; then
    size=$(du -h "$artifact" | cut -f1)
    echo "    $(basename "$artifact") ($size)"
  fi
done
echo ""
echo "  To generate a release manifest:"
echo "    uv run ci/manifest.py <release-tag>"
echo ""
