#!/bin/bash
# Build a Python version for Cosmopolitan
#
# This script handles the full Python build pipeline:
#   1. Download and verify source
#   2. Compile with cosmocc
#   3. Package into distributable binary
#
# Usage:
#   ./scripts/02-python/build.sh <version>
#
# Example:
#   ./scripts/02-python/build.sh 3.12.8
#
# Prerequisites:
#   - cosmocc toolchain installed (via 00-setup/cosmocc.sh)
#   - Dependencies built (via 01-deps/build.sh)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/common.sh"

if [ $# -ne 1 ]; then
  log_error "usage: $0 <python_version>"
  exit 1
fi

VERSION="$1"

log_info "building Python ${VERSION}..."

"${SCRIPT_DIR}/download.sh" "${VERSION}"
"${SCRIPT_DIR}/compile.sh" "${VERSION}"
"${SCRIPT_DIR}/package.sh" "${VERSION}"

log_info "Python ${VERSION} build complete"
