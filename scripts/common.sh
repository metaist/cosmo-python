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

# Get script name for logging prefix (strip path, keep just XX-dir/name)
_SCRIPT_NAME="${BASH_SOURCE[1]:-$0}"
_SCRIPT_NAME="${_SCRIPT_NAME##*/scripts/}"  # Strip everything up to /scripts/
_SCRIPT_NAME="${_SCRIPT_NAME#./scripts/}"   # Strip ./scripts/ prefix
_SCRIPT_NAME="${_SCRIPT_NAME%.sh}"          # Strip .sh suffix

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

#------------------------------------------------------------------------------
# Timeouts for long-running commands
#------------------------------------------------------------------------------

# Timeouts (override with env vars)
# Generous defaults to avoid false failures while catching runaway processes
CONFIGURE_TIMEOUT="${CONFIGURE_TIMEOUT:-5m}"       # 5 min for configure scripts
DEP_MAKE_TIMEOUT="${DEP_MAKE_TIMEOUT:-15m}"        # 15 min for dependency builds
PYTHON_MAKE_TIMEOUT="${PYTHON_MAKE_TIMEOUT:-45m}"  # 45 min for Python compile

# Run make with timeout for dependency builds
# Usage: run_dep_make -j$(nproc)
run_dep_make() {
  if ! timeout "$DEP_MAKE_TIMEOUT" make "$@"; then
    local status=$?
    if [ $status -eq 124 ]; then
      log_error "make timed out after $DEP_MAKE_TIMEOUT"
      log_error "increase DEP_MAKE_TIMEOUT if this is expected"
    fi
    return $status
  fi
}

# Run make with timeout for Python builds
# Usage: run_python_make -j$(nproc)
run_python_make() {
  if ! timeout "$PYTHON_MAKE_TIMEOUT" make "$@"; then
    local status=$?
    if [ $status -eq 124 ]; then
      log_error "make timed out after $PYTHON_MAKE_TIMEOUT"
      log_error "increase PYTHON_MAKE_TIMEOUT if this is expected"
    fi
    return $status
  fi
}

# Common directories (can be overridden by environment)
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
DIST_DIR="${DIST_DIR:-${REPO_ROOT}/dist}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"
DEPS_DIR="${DEPS_DIR:-${WORK_DIR}/deps}"
VERSIONS_FILE="${VERSIONS_FILE:-${REPO_ROOT}/versions.json}"

# Setup cosmocc compiler
# Usage: setup_cosmocc (call after sourcing common.sh)
# Sets: CC, CXX, AR, and basic CFLAGS/LDFLAGS
#
# NOTE: ccache is NOT compatible with cosmocc. cosmocc creates companion
# .aarch64/*.o files alongside each .o file for fat APE builds. ccache
# caches the output and skips creating these companion files, breaking builds.
setup_cosmocc() {
  export CC="${COSMO_DIR}/bin/cosmocc"
  export CXX="${COSMO_DIR}/bin/cosmoc++"
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

#------------------------------------------------------------------------------
# Dependency script helpers
#------------------------------------------------------------------------------

# Parse arguments for dependency scripts
# Usage: parse_dep_args "$@"
# Sets: DEP_VERSION (version to build), DEP_CLEAN (true if --clean passed)
#
# Examples:
#   parse_dep_args                -> DEP_VERSION=(default), DEP_CLEAN=false
#   parse_dep_args 6.6            -> DEP_VERSION=6.6, DEP_CLEAN=false
#   parse_dep_args --clean        -> DEP_VERSION=(default), DEP_CLEAN=true
#   parse_dep_args 6.6 --clean    -> DEP_VERSION=6.6, DEP_CLEAN=true
#
DEP_VERSION=""
DEP_CLEAN=false

parse_dep_args() {
  local dep_name="$1"
  shift
  
  DEP_VERSION=""
  # shellcheck disable=SC2034  # DEP_CLEAN is used by callers after sourcing
  DEP_CLEAN=false
  
  while [ $# -gt 0 ]; do
    case "$1" in
      --clean)
        # shellcheck disable=SC2034
        DEP_CLEAN=true
        ;;
      --help|-h)
        echo "Usage: $0 [VERSION] [--clean]"
        echo ""
        echo "Build ${dep_name} dependency for Cosmopolitan Python."
        echo ""
        echo "Arguments:"
        echo "  VERSION    Version to build (default: from versions.json)"
        echo "  --clean    Remove existing build artifacts before building"
        echo ""
        echo "Examples:"
        echo "  $0                  # Build default version"
        echo "  $0 6.6              # Build specific version"
        echo "  $0 --clean          # Clean and rebuild default"
        echo "  $0 6.6 --clean      # Clean and rebuild specific version"
        exit 0
        ;;
      *)
        if [ -z "$DEP_VERSION" ]; then
          DEP_VERSION="$1"
        else
          log_error "unexpected argument: $1"
          exit 1
        fi
        ;;
    esac
    shift
  done
  
  # Default to versions.json if no version specified
  if [ -z "$DEP_VERSION" ]; then
    DEP_VERSION=$(get_dep_version "$dep_name")
  fi
}

# Clean dependency build artifacts
# Usage: clean_dep "ncurses" "6.4" "/path/to/lib.a" [additional_paths...]
clean_dep() {
  local dep_name="$1"
  local version="$2"
  shift 2
  
  log_info "cleaning ${dep_name} ${version} build artifacts..."
  
  # Remove source directory
  local src_dir="${WORK_DIR}/${dep_name}-${version}"
  if [ -d "$src_dir" ]; then
    log_info "  removing $src_dir"
    rm -rf "$src_dir"
  fi
  
  # Remove any additional paths passed as arguments
  for path in "$@"; do
    if [ -e "$path" ]; then
      log_info "  removing $path"
      rm -rf "$path"
    fi
  done
}

# Save config.log on configure failure
# Usage: run_configure ./configure [args...]
# On failure, outputs config.log and exits
run_configure() {
  log_info "configuring..."
  if ! timeout "$CONFIGURE_TIMEOUT" "$@" > /tmp/configure-output.log 2>&1; then
    local status=$?
    if [ $status -eq 124 ]; then
      log_error "configure timed out after $CONFIGURE_TIMEOUT"
      log_error "increase CONFIGURE_TIMEOUT if this is expected"
    else
      log_error "configure failed!"
    fi
    log_error "--- configure output ---"
    cat /tmp/configure-output.log >&2
    if [ -f config.log ]; then
      log_error "--- config.log (last 100 lines) ---"
      tail -100 config.log >&2
    fi
    exit 1
  fi
}

# Print environment diagnostics (useful for debugging CI)
# Usage: print_diagnostics
print_diagnostics() {
  log_info "=== Environment Diagnostics ==="
  log_info "uname: $(uname -a)"
  log_info "pwd: $(pwd)"
  log_info "user: $(whoami)"
  
  # Check binfmt_misc
  if [ -d /proc/sys/fs/binfmt_misc ]; then
    if [ -f /proc/sys/fs/binfmt_misc/APE ]; then
      log_info "binfmt_misc APE: registered"
    else
      log_warn "binfmt_misc APE: NOT registered"
    fi
  else
    log_warn "binfmt_misc: not available"
  fi
  
  # Check APE loader
  if [ -f /usr/bin/ape ]; then
    log_info "APE loader: /usr/bin/ape exists"
  else
    log_warn "APE loader: /usr/bin/ape NOT found"
  fi
  
  # Check cosmocc
  if [ -x "${COSMO_DIR}/bin/cosmocc" ]; then
    log_info "cosmocc: ${COSMO_DIR}/bin/cosmocc"
    # Quick sanity check
    if echo 'int main(){return 0;}' | "${COSMO_DIR}/bin/cosmocc" -x c - -o /tmp/cc_test 2>/dev/null; then
      log_info "cosmocc: compiler works"
      if /tmp/cc_test 2>/dev/null; then
        log_info "cosmocc: can run compiled binaries"
      else
        log_warn "cosmocc: cannot run compiled binaries (APE loader issue?)"
      fi
      rm -f /tmp/cc_test /tmp/cc_test.aarch64.elf /tmp/cc_test.com.dbg
    else
      log_warn "cosmocc: compiler test failed"
    fi
  else
    log_warn "cosmocc: not found at ${COSMO_DIR}/bin/cosmocc"
  fi
  
  log_info "=== End Diagnostics ==="
}
