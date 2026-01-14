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
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
DIST_DIR="${DIST_DIR:-${REPO_ROOT}/dist}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"
VERSIONS_FILE="${VERSIONS_FILE:-${REPO_ROOT}/versions.json}"

# Setup cosmocc compiler with optional ccache
# Usage: setup_cosmocc (call after sourcing common.sh)
# Sets: CC, CXX, AR, and basic CFLAGS/LDFLAGS
setup_cosmocc() {
  if command -v ccache &> /dev/null; then
    export CC="ccache ${COSMO_DIR}/bin/cosmocc"
    export CXX="ccache ${COSMO_DIR}/bin/cosmoc++"
  else
    export CC="${COSMO_DIR}/bin/cosmocc"
    export CXX="${COSMO_DIR}/bin/cosmoc++"
  fi
  export AR="${COSMO_DIR}/bin/cosmoar"
  export CFLAGS="${CFLAGS:--Os}"
  export LDFLAGS="${LDFLAGS:-}"
}

# Ensure work directories exist
ensure_dirs() {
  mkdir -p "${WORK_DIR}" "${DEPS_DIR}/lib" "${DEPS_DIR}/lib/.aarch64" "${DEPS_DIR}/include"
}

# Get the default version for a package
# Usage: get_pkg_default python   -> "3.12"
# Usage: get_pkg_default openssl  -> "1.1.1u"
get_pkg_default() {
  local pkg="$1"
  jq -r ".${pkg}.default" "${VERSIONS_FILE}"
}

# Get a specific version's field for a package
# Usage: get_pkg_version_field python 3.12.8 sha256  -> "5978435c..."
# Usage: get_pkg_version_field openssl 1.1.1u sha256 -> "fafe2720..."
get_pkg_version_field() {
  local pkg="$1"
  local version="$2"
  local field="$3"
  jq -r ".${pkg}.versions.\"${version}\".${field}" "${VERSIONS_FILE}"
}

# Get the SHA256 for a specific version of a package
# Usage: get_pkg_sha256 python 3.12.8   -> "5978435c..."
# Usage: get_pkg_sha256 openssl 1.1.1u  -> "fafe2720..."
get_pkg_sha256() {
  local pkg="$1"
  local version="$2"
  get_pkg_version_field "$pkg" "$version" sha256
}

# Get the default version for a dependency (convenience wrapper)
# Usage: get_dep_version openssl  -> "1.1.1u"
get_dep_version() {
  local dep="$1"
  get_pkg_default "$dep"
}

# Get SHA256 for default version of a dependency (convenience wrapper)
# Usage: get_dep_sha256 openssl  -> "fafe2720..."
get_dep_sha256() {
  local dep="$1"
  local version
  version=$(get_dep_version "$dep")
  get_pkg_sha256 "$dep" "$version"
}

# Get Python latest version from minor
# Usage: get_python_latest 3.12  -> "3.12.8"
get_python_latest() {
  local minor="$1"
  jq -r ".python.latest.\"${minor}\"" "${VERSIONS_FILE}"
}

# Get Python SHA256 for a full version
# Usage: get_python_sha256 3.12.8  -> "5978435c..."
get_python_sha256() {
  local version="$1"
  get_pkg_sha256 python "$version"
}

# Verify SHA256 checksum of a file
# Usage: verify_checksum "/path/to/file" "expected_sha256" "description"
# Returns 0 if match, exits with error if mismatch
verify_checksum() {
  local file="$1"
  local expected="$2"
  local desc="${3:-$file}"

  local actual
  actual=$(sha256sum "$file" | cut -d' ' -f1)

  if [ "$actual" != "$expected" ]; then
    log_error "checksum mismatch for $desc"
    log_error "  expected: $expected"
    log_error "  got:      $actual"
    rm -f "$file"
    exit 1
  fi
  log_info "checksum verified for $desc"
}

# Download a file and verify its checksum
# Usage: download_and_verify "url" "output_file" "expected_sha256" "description"
download_and_verify() {
  local url="$1"
  local output="$2"
  local expected_sha256="$3"
  local desc="${4:-$output}"

  log_info "downloading $desc..."
  timed curl -fsSL "$url" -o "$output"
  verify_checksum "$output" "$expected_sha256" "$desc"
}
