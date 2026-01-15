#!/bin/bash
# Validate build scripts without running a full build
#
# Usage: ./scripts/test-scripts.sh
#
# This checks:
#   - All scripts have valid bash syntax
#   - common.sh sources correctly and logging works
#   - versions.json parsing works
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

#
# Check all scripts have valid syntax
#
echo "Checking syntax..."
for f in \
  scripts/common.sh \
  scripts/build.sh \
  scripts/check-updates.sh \
  scripts/00-setup/*.sh \
  scripts/01-deps/*.sh \
  scripts/02-python/*.sh \
  scripts/03-package/*.sh
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

#
# Check common.sh sources and logging works
#
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

#
# Check versions.json parsing
#
echo ""
echo "Checking versions.json parsing..."
if [ -f "${REPO_ROOT}/versions.json" ]; then
  # Flattened structure: .python.versions has version keys
  versions=$(jq -r '.python.versions | keys[]' versions.json 2>/dev/null | tr '\n' ' ')
  
  if [ -n "$versions" ]; then
    pass "parsed versions: $versions"
  else
    fail "no versions parsed from versions.json"
  fi
else
  fail "versions.json not found"
fi

#
# Check required directory structure
#
echo ""
echo "Checking directory structure..."
for dir in scripts/00-setup scripts/01-deps scripts/02-python scripts/03-package; do
  if [ -d "${REPO_ROOT}/${dir}" ]; then
    pass "$dir exists"
  else
    fail "$dir missing"
  fi
done

#
# Check required scripts exist
#
echo ""
echo "Checking required scripts..."
required_scripts=(
  "scripts/build.sh"
  "scripts/common.sh"
  "scripts/00-setup/cosmocc.sh"
  "scripts/00-setup/system-deps.sh"
  "scripts/01-deps/bz2.sh"
  "scripts/01-deps/libffi.sh"
  "scripts/01-deps/ncurses.sh"
  "scripts/01-deps/openssl.sh"
  "scripts/01-deps/readline.sh"
  "scripts/01-deps/xz.sh"
  "scripts/02-python/source.sh"
  "scripts/02-python/compile.sh"
  "scripts/03-package/package.sh"
  "scripts/03-package/manifest.sh"
)

for script in "${required_scripts[@]}"; do
  if [ -x "${REPO_ROOT}/${script}" ]; then
    pass "$script (executable)"
  elif [ -f "${REPO_ROOT}/${script}" ]; then
    fail "$script (not executable)"
  else
    fail "$script (missing)"
  fi
done

#
# Summary
#
echo ""
echo "=== Summary ==="
echo ""
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [ $FAIL -gt 0 ]; then
  exit 1
fi

#
# Check test scripts
#
echo ""
echo "Checking test scripts..."
for script in scripts/04-test/*.sh; do
  if [ -f "$script" ]; then
    if [ -x "$script" ]; then
      pass "$script (executable)"
    else
      fail "$script (not executable)"
    fi
  fi
done
