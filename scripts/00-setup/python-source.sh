#!/bin/bash
# Download and extract Python source code
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"

# Get expected SHA256 from versions.json
PYTHON_SHA256="$(get_python_sha256 "$PYTHON_MAJOR_MINOR")"
EXPECTED_VERSION="$(get_python_version "$PYTHON_MAJOR_MINOR")"

# Verify requested version matches versions.json
if [ "$PYTHON_VERSION" != "$EXPECTED_VERSION" ]; then
  log_warn "requested ${PYTHON_VERSION} but versions.json has ${EXPECTED_VERSION}"
  log_warn "checksum verification will use ${EXPECTED_VERSION}'s hash"
fi

PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"

# Check if already downloaded and extracted
if [ -f "${SRC_DIR}/configure" ]; then
  log_skip "Python ${PYTHON_VERSION} source already at ${SRC_DIR}"
  exit 0
fi

log_build "downloading Python ${PYTHON_VERSION} source"

mkdir -p "${WORK_DIR}"
cd "${WORK_DIR}"

TARBALL="Python-${PYTHON_VERSION}.tgz"

# Download and verify checksum
download_and_verify "${PYTHON_URL}" "${TARBALL}" "${PYTHON_SHA256}" "Python ${PYTHON_VERSION}"

log_info "extracting..."
tar xzf "${TARBALL}"
rm "${TARBALL}"

# Apply version-specific patches if they exist
PATCHES_DIR="${REPO_ROOT}/patches/${PYTHON_MAJOR_MINOR}"

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
