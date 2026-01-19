#!/bin/bash
# Validate build scripts without running a full build
#
# Usage: ./scripts/test-scripts.sh
#
# This checks:
#   - All scripts have valid bash syntax
#   - common.sh sources correctly and logging works
#   - upstream.cdx.json parsing works
#   - Required scripts exist
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."

PASS=0
FAIL=0

pass() {
  echo "  ✓ $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  ✗ $1"
  FAIL=$((FAIL + 1))
}

echo ""
echo "=== Script Validation ==="
echo ""

echo "Checking syntax..."
for f in \
  scripts/common.sh \
  scripts/build.sh \
  scripts/build-deps.sh \
  scripts/setup.sh \
  scripts/cosmocc.sh \
  scripts/smoke.sh \
  scripts/bzip2.sh \
  scripts/cacert.sh \
  scripts/gdbm.sh \
  scripts/libffi.sh \
  scripts/ncurses.sh \
  scripts/openssl.sh \
  scripts/readline.sh \
  scripts/sqlite.sh \
  scripts/xz.sh \
  scripts/zstd.sh \
  scripts/python/build.sh \
  scripts/python/download.sh \
  scripts/python/compile.sh \
  scripts/python/package.sh
do
  if [ -f "${REPO_ROOT}/${f}" ]; then
    if bash -n "${REPO_ROOT}/${f}" 2>/dev/null; then
      pass "$f"
    else
      fail "$f (syntax error)"
    fi
  else
    fail "$f (not found)"
  fi
done

echo ""
echo "Checking common.sh..."
cd "${REPO_ROOT}"
if output=$(bash -c 'source scripts/common.sh && log_info "test"' 2>&1); then
  if [[ "$output" == *"test"* ]]; then
    pass "log_info works"
  else
    fail "log_info output unexpected: $output"
  fi
else
  fail "common.sh failed to source"
fi

if output=$(bash -c 'source scripts/common.sh && log_skip "skipped"' 2>&1); then
  if [[ "$output" == *"SKIP"* ]]; then
    pass "log_skip works"
  else
    fail "log_skip output unexpected: $output"
  fi
else
  fail "log_skip failed"
fi

echo ""
echo "Checking upstream.cdx.json parsing..."
if [ -f "${REPO_ROOT}/upstream.cdx.json" ]; then
  versions=$(uv run -m ci.cdx versions 2>/dev/null)
  
  if [ -n "$versions" ]; then
    pass "parsed versions: $versions"
  else
    fail "no versions parsed from upstream.cdx.json"
  fi
else
  fail "upstream.cdx.json not found"
fi

echo ""
echo "=== Summary ==="
echo ""
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [ $FAIL -gt 0 ]; then
  exit 1
fi
