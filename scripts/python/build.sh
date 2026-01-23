#!/bin/bash
# Build a Python version for Cosmopolitan
#
# This script handles the full Python build pipeline:
#   1. Download and verify source
#   2. Compile with cosmocc
#   3. Package into distributable binary
#
# Usage:
#   ./scripts/python/build.sh <version> [--cosmoext]
#
# Options:
#   --cosmoext    Include _cosmoext module for loading C extensions at runtime
#
# Example:
#   ./scripts/python/build.sh 3.12.8
#   ./scripts/python/build.sh 3.12.8 --cosmoext
#
# Prerequisites:
#   - cosmocc toolchain installed (via scripts/cosmocc.sh)
#   - Dependencies built (via scripts/build-deps.sh)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/common.sh"

if [ $# -lt 1 ]; then
  log_error "usage: $0 <python_version> [--cosmoext]"
  exit 1
fi

VERSION="$1"
shift
EXTRA_FLAGS="$*"

log_info "building Python ${VERSION}..."

"${SCRIPT_DIR}/download.sh" "${VERSION}"
"${SCRIPT_DIR}/compile.sh" "${VERSION}" ${EXTRA_FLAGS}
"${SCRIPT_DIR}/package.sh" "${VERSION}"

log_info "Python ${VERSION} build complete"
