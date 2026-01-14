#!/bin/bash
# Download and extract Python source code
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"
SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"

# Check if already downloaded and extracted
if [ -f "${SRC_DIR}/configure" ]; then
  log_skip "Python ${PYTHON_VERSION} source already at ${SRC_DIR}"
  exit 0
fi

log_build "downloading Python ${PYTHON_VERSION} source"

mkdir -p "${WORK_DIR}"
cd "${WORK_DIR}"

log_info "fetching ${PYTHON_URL}..."
timed wget -q "${PYTHON_URL}" -O "Python-${PYTHON_VERSION}.tgz"

log_info "extracting..."
tar xzf "Python-${PYTHON_VERSION}.tgz"
rm "Python-${PYTHON_VERSION}.tgz"

# Apply version-specific patches if they exist
SCRIPT_DIR="$(dirname "$0")"
PATCHES_DIR="${SCRIPT_DIR}/../../patches/${PYTHON_MAJOR_MINOR}"

if [ -d "${PATCHES_DIR}" ]; then
  log_info "applying patches from ${PATCHES_DIR}..."
  cd "${SRC_DIR}"
  for patch in "${PATCHES_DIR}"/*.patch; do
    if [ -f "$patch" ]; then
      patch_name=$(basename "$patch")
      log_info "  applying ${patch_name}..."
      patch -p1 < "$patch"
    fi
  done
fi

log_ok "Python ${PYTHON_VERSION} source ready at ${SRC_DIR}"
