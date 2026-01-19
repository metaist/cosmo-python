#!/bin/bash
# Smoke tests for Cosmopolitan Python builds
#
# Usage: ./scripts/smoke.sh <python_binary>
#        ./scripts/smoke.sh dist/python-3.12.8-cosmo.com
#
# Tests:
#   - Basic execution (--version)
#   - Standard library imports
#   - File I/O
#   - Basic networking (if available)
#   - JSON/data processing
#   - Subprocess execution

source "$(dirname "$0")/common.sh"

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

echo ""
echo "Standard library imports..."
# Note: multiprocessing spawn/Pool doesn't work in Cosmopolitan (see LIMITATIONS.md)

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
run_test "import logging" "import logging; logging.getLogger('test')"
run_test "import argparse" "import argparse; argparse.ArgumentParser()"

echo ""
echo "Data formats..."

run_test "import pickle" "import pickle; pickle.dumps({'a': 1})"
run_test "import xml.etree" "import xml.etree.ElementTree as ET; ET.fromstring('<a/>')"
run_test "import zipfile" "import zipfile"
run_test "import tarfile" "import tarfile"

echo ""
echo "Text processing..."

run_test "import difflib" "import difflib; difflib.SequenceMatcher(None, 'a', 'b')"
run_test "import textwrap" "import textwrap; textwrap.wrap('hello world', 5)"
run_test "import unicodedata" "import unicodedata; unicodedata.name('A')"

echo ""
echo "Testing modules..."

run_test "import unittest" "import unittest"
run_test "import doctest" "import doctest"

echo ""
echo "I/O multiplexing..."

run_test "import select" "import select"
run_test "import selectors" "import selectors; selectors.DefaultSelector()"

echo ""
echo "Unix modules..."

run_test "import pty" "import pty"
run_test "import termios" "import termios"
run_test "import tty" "import tty"
run_test "import fcntl" "import fcntl"
run_test "import pwd" "import pwd; pwd.getpwuid(0)"
run_test "import grp" "import grp"
run_test "import resource" "import resource; resource.getrlimit(resource.RLIMIT_NOFILE)"
run_test "import syslog" "import syslog"
run_test "import signal" "import signal; signal.SIGTERM"
run_test "import mmap" "import mmap"

echo ""
echo "Misc modules..."

run_test "import venv" "import venv"
run_test "import webbrowser" "import webbrowser"

echo ""
echo "Compression modules (our deps)..."

run_test "import zlib" "import zlib; zlib.compress(b'test')"
run_test "import gzip" "import gzip; gzip.compress(b'test')"
run_test "import bz2" "import bz2; bz2.compress(b'test')"
run_test "import lzma" "import lzma; lzma.compress(b'test')"

# zstd compression (Python 3.14+)
if "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)" 2>/dev/null; then
  run_test "import compression.zstd" "from compression import zstd; zstd.compress(b'test')"
fi

echo ""
echo "SQLite (our deps)..."

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

echo ""
echo "GDBM (our deps)..."

run_test "import dbm.gnu" "import dbm.gnu"
run_test "gdbm operations" "
import dbm.gnu as gdbm
import tempfile, os
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, 'test.db')
    with gdbm.open(path, 'c') as db:
        db['key'] = 'value'
    with gdbm.open(path, 'r') as db:
        assert db['key'] == b'value'
"

echo ""
echo "SSL/crypto (our deps)..."
# HTTPS test detects OpenSSL 3.x runtime issues
# See: https://github.com/ahgamut/superconfigure/issues/52

run_test "import ssl" "import ssl; ssl.OPENSSL_VERSION"
run_test "import hashlib" "import hashlib; hashlib.sha256(b'test').hexdigest()"
run_test "import hmac" "import hmac, hashlib; hmac.new(b'key', b'msg', hashlib.sha256).hexdigest()"
run_test "https connection" "
import urllib.request
urllib.request.urlopen('https://www.python.org/', timeout=10)
" 15

echo ""
echo "ctypes/libffi (our deps)..."
# pythonapi requires dlopen(NULL) which Cosmopolitan doesn't support.
# Our ctypes-cosmopolitan.patch sets pythonapi=None as a fallback.
# Basic ctypes functionality (structs, arrays, c types) still works.

run_test "import ctypes" "import ctypes"
run_test "ctypes.c_int" "import ctypes; x = ctypes.c_int(42); assert x.value == 42"
run_test "ctypes.Structure" "
import ctypes
class Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int)]
p = Point(10, 20)
assert p.x == 10 and p.y == 20
"
run_test "ctypes.Array" "
import ctypes
arr = (ctypes.c_int * 3)(1, 2, 3)
assert list(arr) == [1, 2, 3]
"
run_test "ctypes.pythonapi is None" "import ctypes; assert ctypes.pythonapi is None"

echo ""
echo "readline (our deps)..."

run_test "import readline" "import readline"

echo ""
echo "curses/TUI (our deps)..."

run_test "import curses" "import curses; curses.version"
run_test "import curses.panel" "import curses.panel"

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

echo ""
echo "Asyncio..."

run_test "import asyncio" "import asyncio"
run_test "asyncio.run" "
import asyncio
async def main():
    return 42
assert asyncio.run(main()) == 42
"
run_test "asyncio.gather" "
import asyncio
async def double(x):
    await asyncio.sleep(0.001)
    return x * 2
async def main():
    results = await asyncio.gather(*[double(i) for i in range(5)])
    assert results == [0, 2, 4, 6, 8]
asyncio.run(main())
"
run_test "asyncio.create_task" "
import asyncio
async def worker():
    await asyncio.sleep(0.001)
    return 'done'
async def main():
    task = asyncio.create_task(worker())
    result = await task
    assert result == 'done'
asyncio.run(main())
"

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

echo ""
echo "Networking (optional)..."

if run_test "socket module" "import socket; socket.gethostname()" 5; then
  run_test "socket create" "import socket; s = socket.socket(); s.close()" 5
else
  skip "socket tests"
fi

if run_test "urllib.request" "import urllib.request" 5; then
  : # module loads
else
  skip "urllib tests"
fi

echo ""
echo ".args file support (LoadZipArgs)..."

ARGS_TEST_BINARY="/tmp/test-args-$$.com"
cp "$PYTHON" "$ARGS_TEST_BINARY"
echo '-c
print("ARGS_TEST_SUCCESS")' > /tmp/.args
(cd /tmp && zip -q "$ARGS_TEST_BINARY" .args)

if "$ARGS_TEST_BINARY" 2>/dev/null | grep -q "ARGS_TEST_SUCCESS"; then
  pass ".args file execution"
else
  fail ".args file execution"
fi

rm -f "$ARGS_TEST_BINARY" /tmp/.args /tmp/.args-$$

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
