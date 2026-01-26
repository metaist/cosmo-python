#!/bin/bash
# Test cosmoext extensions: download, build, smoke test, benchmark
#
# Usage: ./scripts/cosmoext/test.sh <python_binary> [options]
#
# Options:
#   --ext <name>      Extension to test (can repeat, or use 'all')
#   --no-benchmark    Skip benchmarks
#   --no-download     Skip download (use cached sources)
#   --force           Force rebuild even if .cosmoext exists
#   --verbose         Show build output
#
# Examples:
#   ./scripts/cosmoext/test.sh dist/python-3.12.12-cosmo.com --ext all
#   ./scripts/cosmoext/test.sh python.com --ext markupsafe --ext xxhash
#   ./scripts/cosmoext/test.sh python.com --ext ujson --no-benchmark

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "${ROOT_DIR}/scripts/common.sh"

# Extension definitions: name|version|url|dep_url|sources|test_code
declare -A EXT_VERSION EXT_URL EXT_DEP_URL EXT_SOURCES EXT_INCLUDES EXT_TEST

EXT_VERSION[markupsafe]="3.0.2"
EXT_URL[markupsafe]="https://github.com/pallets/markupsafe/archive/refs/tags/3.0.2.tar.gz"
EXT_SOURCES[markupsafe]="src/markupsafe/_speedups.c"
EXT_TEST[markupsafe]='
import _cosmoext
ms = _cosmoext.load("{path}")
assert ms._escape_inner("<b>") == "&lt;b&gt;", "escape failed"
print("  ✓ _escape_inner works")
'

EXT_VERSION[xxhash]="3.5.0"
EXT_URL[xxhash]="https://github.com/ifduyue/python-xxhash/archive/refs/tags/v3.5.0.tar.gz"
EXT_DEP_URL[xxhash]="https://github.com/Cyan4973/xxHash/archive/refs/tags/v0.8.2.tar.gz"
EXT_SOURCES[xxhash]="deps/xxhash/xxhash.c src/_xxhash.c"
EXT_INCLUDES[xxhash]="deps/xxhash"
EXT_TEST[xxhash]='
import _cosmoext
xxh = _cosmoext.load("{path}")
assert xxh.xxh64(b"hello").intdigest() == 0x26c7827d889f6da3, "hash mismatch"
print("  ✓ xxh64 works")
'

EXT_VERSION[ujson]="5.10.0"
EXT_URL[ujson]="https://github.com/ultrajson/ultrajson/archive/refs/tags/5.10.0.tar.gz"
EXT_SOURCES[ujson]="python/ujson.c python/objToJSON.c python/JSONtoObj.c lib/ultrajsondec.c lib/ultrajsonenc.c lib/dconv_wrapper.cc deps/double-conversion/double-conversion/bignum.cc deps/double-conversion/double-conversion/bignum-dtoa.cc deps/double-conversion/double-conversion/cached-powers.cc deps/double-conversion/double-conversion/double-to-string.cc deps/double-conversion/double-conversion/fast-dtoa.cc deps/double-conversion/double-conversion/fixed-dtoa.cc deps/double-conversion/double-conversion/string-to-double.cc deps/double-conversion/double-conversion/strtod.cc"
EXT_INCLUDES[ujson]="lib python deps/double-conversion/double-conversion"
EXT_TEST[ujson]='
import _cosmoext
uj = _cosmoext.load("{path}")
assert uj.dumps([1,2,3]) == "[1,2,3]", "encode failed"
assert uj.loads("[1,2,3]") == [1,2,3], "decode failed"
print("  ✓ dumps/loads work")
'

EXT_VERSION[regex]="2024.11.6"
EXT_URL[regex]="https://github.com/mrabarnett/mrab-regex/archive/refs/tags/2024.11.6.tar.gz"
EXT_SOURCES[regex]="regex_3/_regex.c regex_3/_regex_unicode.c"
EXT_TEST[regex]='
import _cosmoext
rx = _cosmoext.load("{path}")
assert hasattr(rx, "compile"), "missing compile"
print("  ✓ module loads")
'

ALL_EXTENSIONS="markupsafe xxhash ujson regex"

# Parse arguments
PYTHON=""
EXTENSIONS=""
DO_BENCHMARK=1
DO_DOWNLOAD=1
FORCE_BUILD=0
VERBOSE=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --ext|--extension)
      EXTENSIONS="${EXTENSIONS:+$EXTENSIONS,}$2"
      shift 2
      ;;
    --no-benchmark)
      DO_BENCHMARK=0
      shift
      ;;
    --no-download)
      DO_DOWNLOAD=0
      shift
      ;;
    --force|-f)
      FORCE_BUILD=1
      shift
      ;;
    --verbose|-v)
      VERBOSE=1
      shift
      ;;
    -*)
      log_error "Unknown option: $1"
      exit 1
      ;;
    *)
      if [[ -z "$PYTHON" ]]; then
        PYTHON="$1"
      else
        log_error "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$PYTHON" ]]; then
  echo "Usage: $0 <python_binary> [--ext <name>]..."
  echo "       $0 python.com --ext all"
  echo "       $0 python.com --ext markupsafe,xxhash"
  exit 1
fi

[[ ! -f "$PYTHON" ]] && { log_error "Not found: $PYTHON"; exit 1; }
PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
chmod +x "$PYTHON"

# Expand extensions
[[ "$EXTENSIONS" == "all" ]] && EXTENSIONS="${ALL_EXTENSIONS// /,}"
[[ -z "$EXTENSIONS" ]] && EXTENSIONS="markupsafe"  # default
IFS=',' read -ra EXT_LIST <<< "$EXTENSIONS"

# Work directory
WORK_DIR="${TMPDIR:-/tmp}/cosmoext-test"
mkdir -p "$WORK_DIR"

log_info "Testing cosmoext extensions"
log_info "Python: $PYTHON"
log_info "Extensions: ${EXT_LIST[*]}"
echo

# Check prerequisites
log_info "Checking prerequisites..."
"$PYTHON" -c "import _cosmoext" 2>/dev/null || { log_error "_cosmoext not available"; exit 1; }
echo "  ✓ _cosmoext module"

[[ -x /tmp/cosmo/bin/cosmocc ]] || { log_error "cosmocc not found"; exit 1; }
echo "  ✓ cosmocc toolchain"

command -v python3 &>/dev/null || { log_error "python3 not found"; exit 1; }
echo "  ✓ python3 (for cosmoext-build)"
echo

# Process each extension
RESULTS=()
for ext in "${EXT_LIST[@]}"; do
  log_info "Testing $ext ${EXT_VERSION[$ext]:-}..."
  
  EXT_DIR="$WORK_DIR/$ext"
  COSMOEXT_FILE="$WORK_DIR/${ext}.cosmoext"
  
  # Download
  if [[ $DO_DOWNLOAD -eq 1 ]] && [[ ! -d "$EXT_DIR" ]]; then
    echo "  Downloading..."
    mkdir -p "$EXT_DIR"
    curl -sL "${EXT_URL[$ext]}" | tar xz -C "$EXT_DIR" --strip-components=1
    
    # Handle dependencies
    if [[ -n "${EXT_DEP_URL[$ext]:-}" ]]; then
      DEP_DIR="$EXT_DIR/deps/xxhash"
      mkdir -p "$DEP_DIR"
      curl -sL "${EXT_DEP_URL[$ext]}" | tar xz -C "$DEP_DIR" --strip-components=1
    fi
    
    # ujson needs version.h
    if [[ "$ext" == "ujson" ]]; then
      echo "#define UJSON_VERSION \"${EXT_VERSION[$ext]}\"" > "$EXT_DIR/python/version.h"
    fi
  fi
  
  # Build (only if .cosmoext doesn't exist or --force)
  if [[ ! -f "$COSMOEXT_FILE" ]] || [[ $FORCE_BUILD -eq 1 ]]; then
    echo "  Building..."
    
    # Prepare source files
    SOURCES=""
    for src in ${EXT_SOURCES[$ext]}; do
      SOURCES="$SOURCES $EXT_DIR/$src"
    done
    
    # Prepare includes
    INCLUDE_ARGS=""
    for inc in ${EXT_INCLUDES[$ext]:-}; do
      INCLUDE_ARGS="$INCLUDE_ARGS --include $EXT_DIR/$inc"
    done
    
    # Add libcxx for C++ extensions
    if [[ "$ext" == "ujson" ]]; then
      INCLUDE_ARGS="$INCLUDE_ARGS --include /tmp/cosmo/include/third_party/libcxx"
    fi
    
    BUILD_CMD="python3 $ROOT_DIR/src/cosmoext/cosmoext-build.py \
      --python $PYTHON \
      --output $COSMOEXT_FILE \
      $INCLUDE_ARGS \
      $SOURCES"
    
    if [[ $VERBOSE -eq 1 ]]; then
      eval "$BUILD_CMD" || { log_error "Build failed"; RESULTS+=("$ext:build_failed"); continue; }
    else
      eval "$BUILD_CMD" 2>&1 | tail -3 || { log_error "Build failed"; RESULTS+=("$ext:build_failed"); continue; }
    fi
    echo "  ✓ Built $(basename $COSMOEXT_FILE) ($(stat -c%s "$COSMOEXT_FILE" 2>/dev/null || stat -f%z "$COSMOEXT_FILE") bytes)"
  fi
  
  # Smoke test
  echo "  Smoke testing..."
  TEST_CODE="${EXT_TEST[$ext]//\{path\}/$COSMOEXT_FILE}"
  if "$PYTHON" -c "$TEST_CODE" 2>&1 | grep -v "^\[cosmoext\]"; then
    RESULTS+=("$ext:pass")
  else
    log_error "Smoke test failed"
    RESULTS+=("$ext:smoke_failed")
    continue
  fi
  
  echo
done

# Benchmark
if [[ $DO_BENCHMARK -eq 1 ]]; then
  log_info "Running benchmarks..."
  
  # Copy cosmoext files to /tmp for benchmark script to find
  for ext in "${EXT_LIST[@]}"; do
    cp "$WORK_DIR/${ext}.cosmoext" "/tmp/${ext}.cosmoext" 2>/dev/null || true
  done
  
  "$PYTHON" "$SCRIPT_DIR/benchmark.py" "${EXT_LIST[@]}" 2>&1 | grep -v "^\[cosmoext\]"
  echo
fi

# Summary
log_info "Summary"
for result in "${RESULTS[@]}"; do
  ext="${result%%:*}"
  status="${result##*:}"
  case $status in
    pass) echo "  ✓ $ext" ;;
    *) echo "  ✗ $ext ($status)" ;;
  esac
done
