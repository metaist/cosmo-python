#!/bin/bash
# Smoke tests for cosmoext C extension loading
#
# NOTE: Consider using scripts/cosmoext/test.sh instead, which has
# cleaner code and integrated benchmarks. This script has more extensions
# (cxx_stl, crc32c, msgpack) that haven't been migrated yet.
#
# Usage: ./scripts/smoke-cosmoext.sh <python_binary> [--ext <extension>]...
#        ./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com
#        ./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com --ext xxhash
#        ./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com --ext xxhash,markupsafe
#        ./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com --ext all
#
# Extensions:
#   (none)      - Just test the dummy extension (default)
#   cxx_stl     - C++ STL (std::sort, std::string)
#   xxhash      - Pure C hashing library
#   markupsafe  - Cython HTML escaping
#   crc32c      - CRC32C with SSE4.2 support
#   ujson       - Fast JSON with C++ double-conversion
#   msgpack     - Cython MessagePack serialization
#   regex       - Advanced regex engine
#   all         - Test all extensions
#
# Tests that the _cosmoext module can load .cosmoext files.
# Requires: cosmoext-build tool and cosmocc toolchain.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Extension versions (pinned for reproducibility)
XXHASH_VERSION="3.5.0"
XXHASH_URL="https://github.com/ifduyue/python-xxhash/archive/refs/tags/v${XXHASH_VERSION}.tar.gz"
XXHASH_DEP_URL="https://github.com/Cyan4973/xxHash/archive/refs/tags/v0.8.2.tar.gz"

MARKUPSAFE_VERSION="3.0.2"
MARKUPSAFE_URL="https://github.com/pallets/markupsafe/archive/refs/tags/${MARKUPSAFE_VERSION}.tar.gz"

CRC32C_VERSION="2.7.1"
CRC32C_URL="https://github.com/ICRAR/crc32c/archive/refs/tags/v${CRC32C_VERSION}.tar.gz"

UJSON_VERSION="5.10.0"
UJSON_URL="https://github.com/ultrajson/ultrajson/archive/refs/tags/${UJSON_VERSION}.tar.gz"

MSGPACK_VERSION="1.1.0"
MSGPACK_URL="https://github.com/msgpack/msgpack-python/archive/refs/tags/v${MSGPACK_VERSION}.tar.gz"

REGEX_VERSION="2024.11.6"
REGEX_URL="https://github.com/mrabarnett/mrab-regex/archive/refs/tags/${REGEX_VERSION}.tar.gz"

ALL_EXTENSIONS="cxx_stl xxhash markupsafe crc32c ujson msgpack regex"

# Parse arguments
PYTHON=""
EXTENSIONS=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --ext|--extension)
      if [[ -n "$EXTENSIONS" ]]; then
        EXTENSIONS="$EXTENSIONS,$2"
      else
        EXTENSIONS="$2"
      fi
      shift 2
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

if [ -z "$PYTHON" ]; then
  log_error "usage: $0 <python_binary> [--ext <extension>]..."
  log_error "example: $0 dist/python-3.12.12-cosmo.com"
  log_error "example: $0 dist/python-3.12.12-cosmo.com --ext xxhash"
  log_error "example: $0 dist/python-3.12.12-cosmo.com --ext all"
  exit 1
fi

if [ ! -f "$PYTHON" ]; then
  log_error "binary not found: $PYTHON"
  exit 1
fi

# Make path absolute (for use after cd)
PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
chmod +x "$PYTHON"

# Expand "all" and parse comma-separated list
if [[ "$EXTENSIONS" == "all" ]]; then
  EXTENSIONS="$ALL_EXTENSIONS"
elif [[ -n "$EXTENSIONS" ]]; then
  EXTENSIONS="${EXTENSIONS//,/ }"
fi

# Get Python version
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MINOR=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
log_info "Testing cosmoext on Python ${PY_VERSION}"

if [[ -n "$EXTENSIONS" ]]; then
  log_info "Extensions to test: $EXTENSIONS"
fi

# Detect architecture (for informational purposes)
ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64|arm64|aarch64) ;;  # Supported
  *)
    log_error "Unsupported architecture: $ARCH"
    exit 1
    ;;
esac

PASS=0
FAIL=0
SKIP=0

pass() {
  echo -e "  ${GREEN}✓${RESET} $1"
  PASS=$((PASS + 1))
}

fail() {
  echo -e "  ${RED}✗${RESET} $1"
  FAIL=$((FAIL + 1))
}

skip() {
  echo -e "  ${YELLOW}○${RESET} $1 (skipped)"
  SKIP=$((SKIP + 1))
}

# Create temp directory for test files
TEST_DIR=$(mktemp -d)
trap 'rm -rf $TEST_DIR' EXIT

# Paths
COSMOEXT_BUILD="${SCRIPT_DIR}/../src/cosmoext/cosmoext-build.py"
COSMOCC="/tmp/cosmo/bin/cosmocc"
COSMOCXX="/tmp/cosmo/bin/cosmoc++"

# Try to extract embedded headers from python.com first
EMBEDDED_INCLUDE=""
if "$PYTHON" -c "
import zipfile, sys
with zipfile.ZipFile(sys.executable) as zf:
    if any(f.startswith('.cosmoext/include/') for f in zf.namelist()):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
  EMBEDDED_INCLUDE="$TEST_DIR/embedded"
  mkdir -p "$EMBEDDED_INCLUDE"
  "$PYTHON" -c "
import zipfile, sys, os
with zipfile.ZipFile(sys.executable) as zf:
    for name in zf.namelist():
        if name.startswith('.cosmoext/'):
            zf.extract(name, '$EMBEDDED_INCLUDE')
"
  # Move headers to expected location
  if [ -d "$EMBEDDED_INCLUDE/.cosmoext/include" ]; then
    PY_SRC_INCLUDE="$EMBEDDED_INCLUDE/.cosmoext/include"
    PY_BUILD_INCLUDE="$EMBEDDED_INCLUDE/.cosmoext/include"  # pyconfig.h is here too
    log_info "using embedded headers from python.com"
  fi
fi

# Fall back to work/ directory if no embedded headers
if [ -z "$EMBEDDED_INCLUDE" ] || [ ! -d "$PY_SRC_INCLUDE" ]; then
  PY_SRC_INCLUDE="${SCRIPT_DIR}/../work/Python-${PY_MINOR}/Include"
  PY_BUILD_INCLUDE="${SCRIPT_DIR}/../work/build-${PY_MINOR}-x86_64"
fi

# Helper: download and extract tarball
download_and_extract() {
  local url="$1"
  local name="$2"
  local dest="$TEST_DIR/$name"
  
  if ! curl -sL "$url" -o "$TEST_DIR/$name.tar.gz"; then
    return 1
  fi
  
  mkdir -p "$dest"
  tar xzf "$TEST_DIR/$name.tar.gz" -C "$dest" --strip-components=1
  return 0
}

# Helper: compile C files with cosmocc
# Usage: compile_c [extra flags...] source_files...
# Output .o files are placed in current directory
compile_c() {
  "$COSMOCC" -c -fPIC -mcmodel=large -O2 \
    -I"$PY_SRC_INCLUDE" \
    -I"$PY_BUILD_INCLUDE" \
    "$@" \
    2>/dev/null
}

# Helper: compile C++ files with cosmoc++
# Usage: compile_cxx [extra flags...] source_files...
compile_cxx() {
  "$COSMOCXX" -c -fPIC -mcmodel=large -O2 \
    "$@" \
    2>/dev/null
}

# Helper: build .cosmoext from object files
# Uses uv to ensure pyelftools is available
build_cosmoext() {
  local output="$1"
  shift
  # Capture output; show only "Created" line on success, full output on failure
  local result
  result=$(uv run --no-project --with pyelftools -- python "$COSMOEXT_BUILD" \
    --python "$PYTHON" \
    --output "$output" \
    "$@" 2>&1)
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "$result" | grep "^Created"
  else
    echo "$result"
  fi
  return $rc
}

# Helper: run Python test code
run_test() {
  "$PYTHON" -c "$1" 2>&1
}

# Check prerequisites
echo ""
echo "Prerequisites..."

# Check _cosmoext module
if "$PYTHON" -c "import _cosmoext" 2>/dev/null; then
  pass "_cosmoext module available"
else
  fail "_cosmoext module not available"
  echo "  Binary was not built with --cosmoext flag"
  exit 1
fi

# Check cosmocc
if [ -x "$COSMOCC" ]; then
  pass "cosmocc toolchain available"
else
  skip "cosmocc not found - cannot build test extensions"
  echo ""
  echo "=== Summary ==="
  echo "  Passed:  $PASS"
  echo "  Failed:  $FAIL"
  echo "  Skipped: $SKIP"
  exit 0
fi

# Check cosmoext-build
if [ -f "$COSMOEXT_BUILD" ]; then
  pass "cosmoext-build tool available"
else
  skip "cosmoext-build not found"
  exit 0
fi

# Check Python headers available (embedded or work/)
if [ ! -d "$PY_SRC_INCLUDE" ]; then
  skip "Python headers not found (not embedded and work/ cleaned)"
  echo ""
  echo "=== Summary ==="
  echo "  Passed:  $PASS"
  echo "  Failed:  $FAIL"
  echo "  Skipped: $SKIP"
  exit 0
fi

if [ -n "$EMBEDDED_INCLUDE" ]; then
  pass "Python headers available (embedded)"
else
  pass "Python headers available (work/)"
fi

###############################################################################
# Dummy test extension (always runs)
###############################################################################

test_dummy() {
  echo ""
  echo "Building dummy test extension..."

  cat > "$TEST_DIR/test_ext.c" << 'EOF'
#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject* test_add(PyObject* self, PyObject* args) {
    int a, b;
    if (!PyArg_ParseTuple(args, "ii", &a, &b))
        return NULL;
    return PyLong_FromLong(a + b);
}

static PyObject* test_echo(PyObject* self, PyObject* args) {
    const char* msg;
    if (!PyArg_ParseTuple(args, "s", &msg))
        return NULL;
    return PyUnicode_FromString(msg);
}

static PyMethodDef TestMethods[] = {
    {"add", test_add, METH_VARARGS, "Add two integers"},
    {"echo", test_echo, METH_VARARGS, "Echo a string"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef testmodule = {
    PyModuleDef_HEAD_INIT,
    "_cosmoext_test",
    "Test module for cosmoext",
    -1,
    TestMethods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC PyInit__cosmoext_test(void) {
    return PyModule_Create(&testmodule);
}
EOF

  if compile_c -o "$TEST_DIR/test_ext.o" "$TEST_DIR/test_ext.c"; then
    pass "compiled dummy extension"
  else
    fail "failed to compile dummy extension"
    return 1
  fi

  if build_cosmoext "$TEST_DIR/_cosmoext_test.cosmoext" "$TEST_DIR/test_ext.o"; then
    local size
    size=$(stat -f%z "$TEST_DIR/_cosmoext_test.cosmoext" 2>/dev/null || stat -c%s "$TEST_DIR/_cosmoext_test.cosmoext" 2>/dev/null)
    pass "built dummy.cosmoext (${size} bytes)"
  else
    fail "failed to build dummy.cosmoext"
    return 1
  fi

  echo ""
  echo "Testing dummy extension..."

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$TEST_DIR/_cosmoext_test.cosmoext')
print(f'module:{m.__name__}')
print(f'add:{m.add(2, 3)}')
print(f'echo:{m.echo(\"hello\")}')
")

  if echo "$result" | grep -q "module:_cosmoext_test"; then
    pass "loaded module"
  else
    fail "failed to load module: $result"
    return 1
  fi

  if echo "$result" | grep -q "add:5"; then
    pass "add(2, 3) = 5"
  else
    fail "add function failed"
  fi

  if echo "$result" | grep -q "echo:hello"; then
    pass "echo('hello') = 'hello'"
  else
    fail "echo function failed"
  fi
}

###############################################################################
# C++ STL test - std::sort, std::string
###############################################################################

test_cxx_stl() {
  echo ""
  echo "Building C++ STL test extension..."

  # Check if cosmoc++ exists
  if [[ ! -x "$COSMOCXX" ]]; then
    skip "cosmoc++ not found at $COSMOCXX"
    return 0
  fi

  # Check if libcxx-large archives exist
  local LIBCXX_LARGE="$SCRIPT_DIR/../src/cosmoext/lib/libcxx-large-x86_64.a"
  if [[ ! -f "$LIBCXX_LARGE" ]]; then
    skip "libcxx-large archives not found (run scripts/libcxx-large.sh)"
    return 0
  fi

  cat > "$TEST_DIR/stl_test.cpp" << 'EOF'
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <algorithm>
#include <vector>
#include <string>

static PyObject* sort_list(PyObject* self, PyObject* args) {
    PyObject* list;
    if (!PyArg_ParseTuple(args, "O", &list)) return NULL;

    // Convert to std::vector
    std::vector<long> vec;
    Py_ssize_t size = PyList_Size(list);
    for (Py_ssize_t i = 0; i < size; i++) {
        vec.push_back(PyLong_AsLong(PyList_GetItem(list, i)));
    }

    // Use STL algorithm
    std::sort(vec.begin(), vec.end());

    // Convert back to Python list
    PyObject* result = PyList_New(size);
    for (Py_ssize_t i = 0; i < size; i++) {
        PyList_SetItem(result, i, PyLong_FromLong(vec[i]));
    }
    return result;
}

static PyObject* reverse_string(PyObject* self, PyObject* args) {
    const char* input;
    if (!PyArg_ParseTuple(args, "s", &input)) return NULL;

    std::string s(input);
    std::reverse(s.begin(), s.end());
    return PyUnicode_FromString(s.c_str());
}

static PyMethodDef methods[] = {
    {"sort_list", sort_list, METH_VARARGS, "Sort a list using std::sort"},
    {"reverse_string", reverse_string, METH_VARARGS, "Reverse a string using std::reverse"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_stltest", NULL, -1, methods
};

PyMODINIT_FUNC PyInit__stltest(void) {
    return PyModule_Create(&module);
}
EOF

  # Build with --cxx flag
  if uv run --with pyelftools "$COSMOEXT_BUILD" \
      --python "$PYTHON" \
      --output "$TEST_DIR/_stltest.cosmoext" \
      --cxx \
      -I "$PY_SRC_INCLUDE" \
      -I "$PY_BUILD_INCLUDE" \
      "$TEST_DIR/stl_test.cpp" 2>/dev/null; then
    local size
    size=$(stat -f%z "$TEST_DIR/_stltest.cosmoext" 2>/dev/null || stat -c%s "$TEST_DIR/_stltest.cosmoext" 2>/dev/null)
    pass "built _stltest.cosmoext (${size} bytes)"
  else
    fail "failed to build C++ STL extension"
    return 1
  fi

  echo ""
  echo "Testing C++ STL extension..."

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$TEST_DIR/_stltest.cosmoext')
print(f'module:{m.__name__}')
sorted_list = m.sort_list([5, 2, 8, 1, 9, 3])
print(f'sorted:{sorted_list}')
reversed_str = m.reverse_string('hello')
print(f'reversed:{reversed_str}')
")

  if echo "$result" | grep -q "module:_stltest"; then
    pass "loaded C++ module"
  else
    fail "failed to load C++ module: $result"
    return 1
  fi

  if echo "$result" | grep -q "sorted:\[1, 2, 3, 5, 8, 9\]"; then
    pass "std::sort works"
  else
    fail "std::sort failed: $result"
  fi

  if echo "$result" | grep -q "reversed:olleh"; then
    pass "std::reverse works"
  else
    fail "std::reverse failed: $result"
  fi
}

###############################################################################
# xxhash - Pure C hashing library
###############################################################################

test_xxhash() {
  echo ""
  echo "Testing xxhash ${XXHASH_VERSION}..."

  if ! download_and_extract "$XXHASH_URL" "xxhash"; then
    fail "failed to download xxhash"
    return 1
  fi

  # Download xxhash dependency (header-only library)
  if ! download_and_extract "$XXHASH_DEP_URL" "xxhash-dep"; then
    fail "failed to download xxhash dependency"
    return 1
  fi
  cp -r "$TEST_DIR/xxhash-dep/"* "$TEST_DIR/xxhash/deps/xxhash/"

  local src_dir="$TEST_DIR/xxhash"
  cd "$src_dir" || return 1

  if compile_c \
      -I./deps/xxhash \
      -DXXH_INLINE_ALL \
      src/_xxhash.c; then
    pass "compiled xxhash"
  else
    fail "failed to compile xxhash"
    return 1
  fi

  if build_cosmoext "$src_dir/_xxhash.cosmoext" _xxhash.o; then
    local size
    size=$(stat -f%z "$src_dir/_xxhash.cosmoext" 2>/dev/null || stat -c%s "$src_dir/_xxhash.cosmoext" 2>/dev/null)
    pass "built xxhash.cosmoext (${size} bytes)"
  else
    fail "failed to build xxhash.cosmoext"
    return 1
  fi

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$src_dir/_xxhash.cosmoext')
h = m.xxh64(b'hello world').hexdigest()
print(f'hash:{h}')
")

  if echo "$result" | grep -q "hash:"; then
    pass "xxh64('hello world') works"
  else
    fail "xxhash test failed: $result"
    return 1
  fi
}

###############################################################################
# markupsafe - Cython HTML escaping
###############################################################################

test_markupsafe() {
  echo ""
  echo "Testing markupsafe ${MARKUPSAFE_VERSION}..."

  if ! download_and_extract "$MARKUPSAFE_URL" "markupsafe"; then
    fail "failed to download markupsafe"
    return 1
  fi

  local src_dir="$TEST_DIR/markupsafe"
  cd "$src_dir" || return 1

  if compile_c src/markupsafe/_speedups.c; then
    pass "compiled markupsafe"
  else
    fail "failed to compile markupsafe"
    return 1
  fi

  if build_cosmoext "$src_dir/_speedups.cosmoext" _speedups.o; then
    local size
    size=$(stat -f%z "$src_dir/_speedups.cosmoext" 2>/dev/null || stat -c%s "$src_dir/_speedups.cosmoext" 2>/dev/null)
    pass "built markupsafe.cosmoext (${size} bytes)"
  else
    fail "failed to build markupsafe.cosmoext"
    return 1
  fi

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$src_dir/_speedups.cosmoext')
escaped = m._escape_inner('<script>')
print(f'escaped:{escaped}')
")

  if echo "$result" | grep -q "escaped:&lt;script&gt;"; then
    pass "_escape_inner('<script>') works"
  else
    fail "markupsafe test failed: $result"
    return 1
  fi
}

###############################################################################
# crc32c - CRC32C with optional SSE4.2
###############################################################################

test_crc32c() {
  echo ""
  echo "Testing crc32c ${CRC32C_VERSION}..."

  if ! download_and_extract "$CRC32C_URL" "crc32c"; then
    fail "failed to download crc32c"
    return 1
  fi

  local src_dir="$TEST_DIR/crc32c"
  cd "$src_dir" || return 1

  if compile_c \
      -I./src/crc32c/ext \
      src/crc32c/ext/_crc32c.c \
      src/crc32c/ext/crc32c_sw.c \
      src/crc32c/ext/crc32c_adler.c \
      src/crc32c/ext/checksse42.c; then
    pass "compiled crc32c"
  else
    fail "failed to compile crc32c"
    return 1
  fi

  if build_cosmoext "$src_dir/_crc32c.cosmoext" \
      _crc32c.o crc32c_sw.o crc32c_adler.o checksse42.o; then
    local size
    size=$(stat -f%z "$src_dir/_crc32c.cosmoext" 2>/dev/null || stat -c%s "$src_dir/_crc32c.cosmoext" 2>/dev/null)
    pass "built crc32c.cosmoext (${size} bytes)"
  else
    fail "failed to build crc32c.cosmoext"
    return 1
  fi

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$src_dir/_crc32c.cosmoext')
crc = m.crc32c(b'hello world')
print(f'crc:{crc:#010x}')
")

  if echo "$result" | grep -q "crc:0x"; then
    pass "crc32c(b'hello world') works"
  else
    fail "crc32c test failed: $result"
    return 1
  fi
}

###############################################################################
# ujson - Fast JSON with C++ double-conversion
###############################################################################

test_ujson() {
  echo ""
  echo "Testing ujson ${UJSON_VERSION}..."

  if ! download_and_extract "$UJSON_URL" "ujson"; then
    fail "failed to download ujson"
    return 1
  fi

  local src_dir="$TEST_DIR/ujson"
  cd "$src_dir" || return 1

  # Create version.h
  echo "#define UJSON_VERSION \"${UJSON_VERSION}\"" > python/version.h

  # Compile double-conversion C++ files
  if compile_cxx \
      -I./deps/double-conversion/double-conversion \
      deps/double-conversion/double-conversion/bignum.cc \
      deps/double-conversion/double-conversion/bignum-dtoa.cc \
      deps/double-conversion/double-conversion/cached-powers.cc \
      deps/double-conversion/double-conversion/double-to-string.cc \
      deps/double-conversion/double-conversion/fast-dtoa.cc \
      deps/double-conversion/double-conversion/fixed-dtoa.cc \
      deps/double-conversion/double-conversion/string-to-double.cc \
      deps/double-conversion/double-conversion/strtod.cc \
      lib/dconv_wrapper.cc; then
    pass "compiled double-conversion"
  else
    fail "failed to compile double-conversion"
    return 1
  fi

  # Compile ujson C files
  if compile_c \
      -I./python \
      -I./lib \
      python/ujson.c \
      python/JSONtoObj.c \
      python/objToJSON.c \
      lib/ultrajsonenc.c \
      lib/ultrajsondec.c; then
    pass "compiled ujson"
  else
    fail "failed to compile ujson"
    return 1
  fi

  # Build cosmoext with all objects
  if build_cosmoext "$src_dir/ujson.cosmoext" \
      ujson.o JSONtoObj.o objToJSON.o ultrajsonenc.o ultrajsondec.o \
      bignum.o bignum-dtoa.o cached-powers.o dconv_wrapper.o \
      double-to-string.o fast-dtoa.o fixed-dtoa.o string-to-double.o strtod.o; then
    local size
    size=$(stat -f%z "$src_dir/ujson.cosmoext" 2>/dev/null || stat -c%s "$src_dir/ujson.cosmoext" 2>/dev/null)
    pass "built ujson.cosmoext (${size} bytes)"
  else
    fail "failed to build ujson.cosmoext"
    return 1
  fi

  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$src_dir/ujson.cosmoext')
data = {'key': 'value', 'num': 42}
encoded = m.dumps(data)
decoded = m.loads(encoded)
print(f'roundtrip:{decoded}')
")

  if echo "$result" | grep -q "roundtrip:{'key': 'value', 'num': 42}"; then
    pass "ujson encode/decode works"
  else
    fail "ujson test failed: $result"
    return 1
  fi
}

###############################################################################
# msgpack - Cython MessagePack serialization
###############################################################################

test_msgpack() {
  echo ""
  echo "Testing msgpack ${MSGPACK_VERSION}..."

  if ! download_and_extract "$MSGPACK_URL" "msgpack"; then
    fail "failed to download msgpack"
    return 1
  fi

  local src_dir="$TEST_DIR/msgpack"
  cd "$src_dir" || return 1

  # Generate C from Cython (needs cython)
  if ! command -v cython &>/dev/null && ! uv run --no-project --with cython -- cython --version &>/dev/null; then
    skip "cython not available for msgpack"
    return 0
  fi

  # Run cython to generate C file
  if uv run --no-project --with cython -- cython -3 \
      msgpack/_cmsgpack.pyx \
      -o msgpack/_cmsgpack.c 2>/dev/null; then
    pass "generated C from Cython"
  else
    fail "failed to run cython"
    return 1
  fi

  if compile_c -I. msgpack/_cmsgpack.c; then
    pass "compiled msgpack"
  else
    fail "failed to compile msgpack"
    return 1
  fi

  if build_cosmoext "$src_dir/_cmsgpack.cosmoext" _cmsgpack.o; then
    local size
    size=$(stat -f%z "$src_dir/_cmsgpack.cosmoext" 2>/dev/null || stat -c%s "$src_dir/_cmsgpack.cosmoext" 2>/dev/null)
    pass "built msgpack.cosmoext (${size} bytes)"
  else
    fail "failed to build msgpack.cosmoext"
    return 1
  fi

  # msgpack needs its Python package for relative imports
  local result
  result=$(run_test "
import sys
sys.path.insert(0, '$src_dir')
import msgpack
data = {'key': 'value', 'num': 42}
packed = msgpack.packb(data)
unpacked = msgpack.unpackb(packed)
print(f'roundtrip:{unpacked}')
")

  if echo "$result" | grep -q "roundtrip:{'key': 'value', 'num': 42}"; then
    pass "msgpack pack/unpack works"
  else
    fail "msgpack test failed: $result"
    return 1
  fi
}

###############################################################################
# regex - Advanced regex engine
###############################################################################

test_regex() {
  echo ""
  echo "Testing regex ${REGEX_VERSION}..."

  if ! download_and_extract "$REGEX_URL" "regex"; then
    fail "failed to download regex"
    return 1
  fi

  local src_dir="$TEST_DIR/regex"
  cd "$src_dir" || return 1

  if compile_c \
      -I./regex_3 \
      regex_3/_regex.c \
      regex_3/_regex_unicode.c; then
    pass "compiled regex"
  else
    fail "failed to compile regex"
    return 1
  fi

  if build_cosmoext "$src_dir/_regex.cosmoext" \
      _regex.o _regex_unicode.o; then
    local size
    size=$(stat -f%z "$src_dir/_regex.cosmoext" 2>/dev/null || stat -c%s "$src_dir/_regex.cosmoext" 2>/dev/null)
    pass "built regex.cosmoext (${size} bytes)"
  else
    fail "failed to build regex.cosmoext"
    return 1
  fi

  # Test low-level functions (full regex needs Python wrapper)
  local result
  result=$(run_test "
import _cosmoext
m = _cosmoext.load('$src_dir/_regex.cosmoext')
magic = m.MAGIC
folded = m.fold_case(0, 'ABC')
print(f'magic:{magic}')
print(f'folded:{folded}')
")

  if echo "$result" | grep -q "magic:20100116" && echo "$result" | grep -q "folded:ABC"; then
    pass "regex low-level functions work"
  else
    fail "regex test failed: $result"
    return 1
  fi
}

###############################################################################
# Main
###############################################################################

# Always run dummy test
test_dummy

# Run requested extension tests
for ext in $EXTENSIONS; do
  case "$ext" in
    cxx_stl)    test_cxx_stl ;;
    xxhash)     test_xxhash ;;
    markupsafe) test_markupsafe ;;
    crc32c)     test_crc32c ;;
    ujson)      test_ujson ;;
    msgpack)    test_msgpack ;;
    regex)      test_regex ;;
    *)
      log_error "Unknown extension: $ext"
      log_error "Available: $ALL_EXTENSIONS"
      exit 1
      ;;
  esac
done

# Summary
echo ""
echo "=== Summary ==="
echo ""
echo "  Passed:  $PASS"
echo "  Failed:  $FAIL"
echo "  Skipped: $SKIP"

if [ $FAIL -gt 0 ]; then
  exit 1
fi
