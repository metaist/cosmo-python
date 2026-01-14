#!/bin/bash
# Smoke tests for Cosmopolitan Python builds
#
# Usage: ./scripts/04-test/smoke.sh <python_binary>
#        ./scripts/04-test/smoke.sh dist/python-3.12.8-cosmo-x86_64.com
#
# Tests:
#   - Basic execution (--version)
#   - Standard library imports
#   - File I/O
#   - Basic networking (if available)
#   - JSON/data processing
#   - Subprocess execution
#
source "$(dirname "$0")/../common.sh"

PYTHON="${1:-}"

if [ -z "$PYTHON" ]; then
  log_error "usage: $0 <python_binary>"
  log_error "example: $0 dist/python-3.12.8-cosmo-x86_64.com"
  exit 1
fi

if [ ! -f "$PYTHON" ]; then
  log_error "binary not found: $PYTHON"
  exit 1
fi

# Make sure it's executable
chmod +x "$PYTHON"

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

run_test() {
  local name="$1"
  local code="$2"
  local timeout="${3:-10}"
  
  if timeout "$timeout" "$PYTHON" -c "$code" > /dev/null 2>&1; then
    pass "$name"
    return 0
  else
    fail "$name"
    return 1
  fi
}

echo ""
echo "=== Smoke Tests ==="
echo ""
echo "Binary: $PYTHON"
echo ""

#
# Basic execution
#
echo "Basic execution..."

if version=$("$PYTHON" --version 2>&1); then
  pass "--version: $version"
else
  fail "--version"
fi

if "$PYTHON" -c "import sys; print(sys.executable)" > /dev/null 2>&1; then
  pass "sys.executable"
else
  fail "sys.executable"
fi

#
# Core standard library
#
echo ""
echo "Standard library imports..."

run_test "import os" "import os; os.getcwd()"
run_test "import sys" "import sys; sys.version"
run_test "import json" "import json; json.dumps({'test': 1})"
run_test "import re" "import re; re.match('test', 'test')"
run_test "import math" "import math; math.sqrt(4)"
run_test "import datetime" "import datetime; datetime.datetime.now()"
run_test "import collections" "import collections; collections.Counter('test')"
run_test "import itertools" "import itertools; list(itertools.chain([1], [2]))"
run_test "import functools" "import functools; functools.reduce(lambda a,b: a+b, [1,2,3])"
run_test "import pathlib" "import pathlib; pathlib.Path('.')"
run_test "import tempfile" "import tempfile; tempfile.gettempdir()"
run_test "import shutil" "import shutil; shutil.which('ls')"
run_test "import subprocess" "import subprocess"
run_test "import threading" "import threading; threading.current_thread()"
run_test "import multiprocessing" "import multiprocessing"

#
# Compression modules (our deps)
#
echo ""
echo "Compression modules..."

run_test "import zlib" "import zlib; zlib.compress(b'test')"
run_test "import gzip" "import gzip; gzip.compress(b'test')"
run_test "import bz2" "import bz2; bz2.compress(b'test')"
run_test "import lzma" "import lzma; lzma.compress(b'test')"

#
# SQLite (our deps)
#
echo ""
echo "SQLite module..."

run_test "import sqlite3" "import sqlite3; sqlite3.sqlite_version"
run_test "sqlite3 operations" "
import sqlite3
conn = sqlite3.connect(':memory:')
c = conn.cursor()
c.execute('CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)')
c.execute('INSERT INTO test (value) VALUES (?)', ('hello',))
c.execute('SELECT value FROM test')
assert c.fetchone()[0] == 'hello'
conn.close()
"

#
# SSL/crypto (our deps)
#
echo ""
echo "SSL/crypto modules..."

run_test "import ssl" "import ssl; ssl.OPENSSL_VERSION"
run_test "import hashlib" "import hashlib; hashlib.sha256(b'test').hexdigest()"
run_test "import hmac" "import hmac; hmac.new(b'key', b'msg', 'sha256').hexdigest()"

# HTTPS connection test - critical for detecting OpenSSL 3.x runtime issues
# See: https://github.com/ahgamut/superconfigure/issues/52
run_test "https connection" "
import urllib.request
urllib.request.urlopen('https://www.python.org/', timeout=10)
" 15

#
# ctypes/libffi (our deps)
# Note: ctypes module-level code calls PyDLL(None) which requires dlopen.
# This fails on Cosmopolitan. The _ctypes C extension is linked, but
# the Python wrapper isn't compatible. Skip for now.
#
echo ""
echo "FFI modules..."

# ctypes doesn't work due to dlopen limitation
skip "import ctypes (dlopen not supported)"

#
# readline (our deps)
#
echo ""
echo "Interactive modules..."

run_test "import readline" "import readline"

#
# File I/O
#
echo ""
echo "File I/O..."

run_test "write/read file" "
import tempfile, os
with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
    f.write('test')
    name = f.name
with open(name) as f:
    assert f.read() == 'test'
os.unlink(name)
"

run_test "pathlib operations" "
import pathlib, tempfile
p = pathlib.Path(tempfile.gettempdir()) / 'cosmo_test'
p.write_text('hello')
assert p.read_text() == 'hello'
p.unlink()
"

#
# Data processing
#
echo ""
echo "Data processing..."

run_test "json encode/decode" "
import json
data = {'key': 'value', 'num': 42, 'list': [1,2,3]}
s = json.dumps(data)
assert json.loads(s) == data
"

run_test "csv processing" "
import csv, io
f = io.StringIO()
w = csv.writer(f)
w.writerow(['a', 'b', 'c'])
f.seek(0)
r = csv.reader(f)
assert next(r) == ['a', 'b', 'c']
"

run_test "struct pack/unpack" "
import struct
packed = struct.pack('iif', 1, 2, 3.0)
assert struct.unpack('iif', packed) == (1, 2, 3.0)
"

#
# Subprocess (may not work in all environments)
#
echo ""
echo "Subprocess..."

if run_test "subprocess.run echo" "
import subprocess
r = subprocess.run(['echo', 'hello'], capture_output=True, text=True)
assert r.stdout.strip() == 'hello'
" 5; then
  : # passed
else
  log_info "  (subprocess may require APE loader)"
fi

#
# Networking (may not work in all environments)
#
echo ""
echo "Networking (optional)..."

if run_test "socket module" "import socket; socket.gethostname()" 5; then
  run_test "socket create" "import socket; s = socket.socket(); s.close()" 5
else
  skip "socket tests"
fi

# urllib may hang without network, use short timeout
if run_test "urllib.request" "import urllib.request" 5; then
  : # module loads
else
  skip "urllib tests"
fi

#
# Summary
#
echo ""
echo "=== Summary ==="
echo ""
echo "  Passed:  $PASS"
echo "  Failed:  $FAIL"
echo "  Skipped: $SKIP"
echo ""

if [ $FAIL -gt 0 ]; then
  log_error "Some tests failed"
  exit 1
else
  log_ok "All tests passed"
  exit 0
fi
