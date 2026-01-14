#!/bin/bash
# Common utilities for build scripts
# Source this file: source "$(dirname "$0")/../common.sh"

set -euo pipefail

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  BLUE=''
  BOLD=''
  RESET=''
fi

# Get script name for logging prefix
_SCRIPT_NAME="${BASH_SOURCE[1]:-$0}"
_SCRIPT_NAME="${_SCRIPT_NAME#./scripts/}"
_SCRIPT_NAME="${_SCRIPT_NAME%.sh}"

# Logging functions
log_info() {
  echo -e "${BLUE}[${_SCRIPT_NAME}]${RESET} $*"
}

log_ok() {
  echo -e "${GREEN}[${_SCRIPT_NAME}]${RESET} $*"
}

log_warn() {
  echo -e "${YELLOW}[${_SCRIPT_NAME}]${RESET} $*"
}

log_error() {
  echo -e "${RED}[${_SCRIPT_NAME}]${RESET} $*" >&2
}

log_skip() {
  echo -e "${GREEN}[${_SCRIPT_NAME}]${RESET} ${BOLD}SKIP${RESET} $*"
}

log_build() {
  echo -e "${BLUE}[${_SCRIPT_NAME}]${RESET} ${BOLD}BUILD${RESET} $*"
}

# Idempotency helpers

# Check if a file exists; if so, log skip and exit 0
# Usage: skip_if_exists "/path/to/output" "description"
skip_if_exists() {
  local path="$1"
  local desc="${2:-$path}"
  if [ -f "$path" ]; then
    log_skip "$desc already exists"
    exit 0
  fi
}

# Check if all files in a list exist; if so, log skip and exit 0
# Usage: skip_if_all_exist "description" file1 file2 ...
skip_if_all_exist() {
  local desc="$1"
  shift
  local all_exist=true
  for f in "$@"; do
    if [ ! -f "$f" ]; then
      all_exist=false
      break
    fi
  done
  if [ "$all_exist" = true ]; then
    log_skip "$desc"
    exit 0
  fi
}

# Check if a directory exists and is non-empty; if so, log skip and exit 0
# Usage: skip_if_dir_exists "/path/to/dir" "description"
skip_if_dir_exists() {
  local path="$1"
  local desc="${2:-$path}"
  if [ -d "$path" ] && [ -n "$(ls -A "$path" 2>/dev/null)" ]; then
    log_skip "$desc already exists"
    exit 0
  fi
}

# Time a command and report duration
# Usage: timed make -j$(nproc)
timed() {
  local start end duration
  start=$(date +%s)
  "$@"
  local status=$?
  end=$(date +%s)
  duration=$((end - start))
  if [ $duration -ge 60 ]; then
    log_info "completed in $((duration / 60))m $((duration % 60))s"
  elif [ $duration -ge 5 ]; then
    log_info "completed in ${duration}s"
  fi
  return $status
}

# Common directories (can be overridden by environment)
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
DIST_DIR="${DIST_DIR:-$(pwd)/dist}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"

# Ensure work directories exist
ensure_dirs() {
  mkdir -p "${WORK_DIR}" "${DEPS_DIR}/lib" "${DEPS_DIR}/lib/.aarch64" "${DEPS_DIR}/include"
}
