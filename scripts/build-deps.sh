#!/bin/bash
# Build all dependencies for cosmo-python
#
# This script:
#   1. Installs system dependencies (via apt)
#   2. Builds all library dependencies via toposort
#
# Dependencies are built in parallel by level when GNU parallel is available.
# Build order is determined by upstream.cdx.json dependency graph.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Install system dependencies first (not in toposort)
"${SCRIPT_DIR}/setup.sh"

# Get build order for all Python versions (union of deps), excluding python itself
# This ensures we build all deps needed by any Python version
BUILD_ORDER=$($CDX_CLI build-order-all --exclude python)

# Build a single dep by name
build_dep() {
  local ref="$1"
  local name="${ref%@*}"  # strip @version
  local script="${SCRIPT_DIR}/${name}.sh"
  if [[ -f "$script" ]]; then
    "$script"
  else
    log_info "skipping $name (no build script)"
  fi
}

# Build dependencies by level
if command -v parallel >/dev/null 2>&1; then
  log_info "building dependencies in parallel..."
  
  last_level=-1
  level_deps=""
  
  while IFS=' ' read -r level ref; do
    if [[ "$level" != "$last_level" && -n "$level_deps" ]]; then
      # Build previous level in parallel
      # shellcheck disable=SC2086
      parallel --line-buffer --halt now,fail=1 ::: $level_deps
      level_deps=""
    fi
    name="${ref%@*}"
    script="${SCRIPT_DIR}/${name}.sh"
    if [[ -f "$script" ]]; then
      level_deps+=" $script"
    fi
    last_level="$level"
  done <<< "$BUILD_ORDER"
  
  # Build final level
  if [[ -n "$level_deps" ]]; then
    # shellcheck disable=SC2086
    parallel --line-buffer --halt now,fail=1 ::: $level_deps
  fi
else
  log_info "building dependencies sequentially (install 'parallel' for faster builds)..."
  
  while IFS=' ' read -r _ ref; do
    build_dep "$ref"
  done <<< "$BUILD_ORDER"
fi

log_info "all dependencies built successfully"
