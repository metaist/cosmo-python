#!/bin/bash
# Smoke tests for cosmoext C extension loading
#
# Usage: ./scripts/smoke-cosmoext.sh <python_binary>
#        ./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com
#
# Tests that the _cosmoext module can load .cosmoext files.
# Requires: cosmoext-build tool and cosmocc toolchain.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

PYTHON="${1:-}"

if [ -z "$PYTHON" ]; then
  log_error "usage: $0 <python_binary>"
  log_error "example: $0 dist/python-3.12.12-cosmo.com"
  exit 1
fi

if [ ! -f "$PYTHON" ]; then
  log_error "binary not found: $PYTHON"
  exit 1
fi

chmod +x "$PYTHON"

# Get Python version
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Testing cosmoext on Python ${PY_VERSION}"

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
if [ -x "/tmp/cosmo/bin/cosmocc" ]; then
  pass "cosmocc toolchain available"
  COSMOCC="/tmp/cosmo/bin/cosmocc"
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
COSMOEXT_BUILD="${SCRIPT_DIR}/../src/cosmoext/cosmoext-build.py"
if [ -f "$COSMOEXT_BUILD" ]; then
  pass "cosmoext-build tool available"
else
  skip "cosmoext-build not found"
  exit 0
fi

# Build a minimal test extension
echo ""
echo "Building test extension..."

# Create test extension source
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

# Get Python include path from work directory (not from binary - that's /zip/...)
PY_MINOR=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
PY_SRC_INCLUDE="${SCRIPT_DIR}/../work/Python-${PY_MINOR}/Include"
PY_BUILD_INCLUDE="${SCRIPT_DIR}/../work/build-${PY_MINOR}-x86_64"

if [ ! -d "$PY_SRC_INCLUDE" ]; then
  skip "Python source not found at $PY_SRC_INCLUDE (need to keep work/ after build)"
  echo ""
  echo "=== Summary ==="
  echo "  Passed:  $PASS"
  echo "  Failed:  $FAIL"  
  echo "  Skipped: $SKIP"
  exit 0
fi

# Compile to .o with cosmocc using -mcmodel=large
if "$COSMOCC" -c -fPIC -mcmodel=large \
    -I"$PY_SRC_INCLUDE" \
    -I"$PY_BUILD_INCLUDE" \
    -o "$TEST_DIR/test_ext.o" \
    "$TEST_DIR/test_ext.c" 2>/dev/null; then
  pass "compiled test extension"
else
  fail "failed to compile test extension"
  exit 1
fi

# Build .cosmoext using cosmoext-build (fat binary with both architectures)
COSMOEXT_OUT="$TEST_DIR/_cosmoext_test.cosmoext"
if "$PYTHON" "$COSMOEXT_BUILD" \
    --python "$PYTHON" \
    --output "$COSMOEXT_OUT" \
    "$TEST_DIR/test_ext.o" 2>/dev/null && [ -f "$COSMOEXT_OUT" ]; then
  SIZE=$(stat -f%z "$COSMOEXT_OUT" 2>/dev/null || stat -c%s "$COSMOEXT_OUT" 2>/dev/null)
  pass "built .cosmoext file (${SIZE} bytes)"
else
  fail "failed to build .cosmoext file"
  # Show error for debugging
  "$PYTHON" "$COSMOEXT_BUILD" \
    --python "$PYTHON" \
    --output "$COSMOEXT_OUT" \
    "$TEST_DIR/test_ext.o" 2>&1 | tail -20
  exit 1
fi

# Test loading the extension
echo ""
echo "Loading extension..."

# Test basic load
LOAD_RESULT=$("$PYTHON" -c "
import _cosmoext
import os
path = '$COSMOEXT_OUT'
m = _cosmoext.load(path)
print(f'module:{m.__name__}')
print(f'add:{m.add(2, 3)}')
print(f'echo:{m.echo(\"hello\")}')
" 2>&1)

if echo "$LOAD_RESULT" | grep -q "module:_cosmoext_test"; then
  pass "loaded module"
else
  fail "failed to load module"
  echo "  Output: $LOAD_RESULT"
fi

if echo "$LOAD_RESULT" | grep -q "add:5"; then
  pass "add(2, 3) = 5"
else
  fail "add function failed"
fi

if echo "$LOAD_RESULT" | grep -q "echo:hello"; then
  pass "echo('hello') = 'hello'"
else
  fail "echo function failed"
fi

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
