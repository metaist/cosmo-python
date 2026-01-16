#!/bin/bash
# Validate build scripts without running a full build
#
# Usage: ./scripts/test-scripts.sh
#
# This checks:
#   - All scripts have valid bash syntax
#   - common.sh sources correctly and logging works
#   - versions.cdx.json parsing works
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
  scripts/00-setup/*.sh \
  scripts/01-deps/*.sh \
  scripts/02-python/*.sh
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
echo "Checking versions.cdx.json parsing..."
if [ -f "${REPO_ROOT}/versions.cdx.json" ]; then
  versions=$(uv run -m ci.cdx versions 2>/dev/null)
  
  if [ -n "$versions" ]; then
    pass "parsed versions: $versions"
  else
    fail "no versions parsed from versions.cdx.json"
  fi
else
  fail "versions.cdx.json not found"
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


