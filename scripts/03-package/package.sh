#!/bin/bash
# Package Python build artifacts with bundled standard library
#
# This creates a self-contained Cosmopolitan Python executable with
# the standard library embedded as a ZIP archive.
#
# Dependencies: 02-python/compile.sh must have run successfully
# Outputs: ${DIST_DIR}/python-${VERSION}-cosmo-${ARCH}.com
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"
ARCH="${2:-x86_64}"

if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version> [arch]"
  log_error "example: $0 3.12.8 x86_64"
  exit 1
fi

PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"
SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"
BUILD_DIR="${WORK_DIR}/build-${PYTHON_VERSION}-${ARCH}"
STAGING_DIR="${WORK_DIR}/staging-${PYTHON_VERSION}-${ARCH}"
OUTPUT_NAME="python-${PYTHON_VERSION}-cosmo-${ARCH}.com"
OUTPUT_PATH="${DIST_DIR}/${OUTPUT_NAME}"

# Idempotency: skip if already packaged
if [ -f "${OUTPUT_PATH}" ]; then
  log_skip "already packaged at ${OUTPUT_PATH}"
  exit 0
fi

# Find the built binary
BINARY=""
for candidate in "${BUILD_DIR}/python.com" "${BUILD_DIR}/python"; do
  if [ -f "$candidate" ]; then
    BINARY="$candidate"
    break
  fi
done

if [ -z "${BINARY}" ]; then
  log_error "could not find built Python binary in ${BUILD_DIR}"
  log_error "run 02-python/compile.sh ${PYTHON_VERSION} first"
  exit 1
fi

log_build "packaging Python ${PYTHON_VERSION} (${ARCH})"

mkdir -p "${DIST_DIR}"

# Install Python to staging directory to get the standard library
log_info "installing to staging directory..."
rm -rf "${STAGING_DIR}"
cd "${BUILD_DIR}"
make install DESTDIR="${STAGING_DIR}" > /dev/null 2>&1

# Verify stdlib was installed
STDLIB_PATH="${STAGING_DIR}/zip/lib/python${PYTHON_MAJOR_MINOR}"
if [ ! -d "${STDLIB_PATH}" ]; then
  log_error "standard library not found at ${STDLIB_PATH}"
  exit 1
fi

log_info "stdlib size: $(du -sh "${STDLIB_PATH}" | cut -f1)"

# Create the output binary
cp "${BINARY}" "${OUTPUT_PATH}"
chmod +x "${OUTPUT_PATH}"

# Create a ZIP of the standard library
# The ZIP is appended to the binary and accessible via /zip/ paths
log_info "creating stdlib ZIP archive..."
STDLIB_ZIP="${WORK_DIR}/stdlib-${ARCH}.zip"
rm -f "${STDLIB_ZIP}"

cd "${STAGING_DIR}/zip"

# Remove files not needed at runtime
rm -f lib/libpython*.a
rm -rf lib/pkgconfig

# Use zip with -r recursive, -q quiet
# Could use -0 (store, no compression) for faster startup at cost of size
zip -r -q "${STDLIB_ZIP}" lib/

log_info "stdlib ZIP size: $(du -sh "${STDLIB_ZIP}" | cut -f1)"

# Append the ZIP to the binary
# For APE binaries, we can simply concatenate the ZIP
log_info "appending stdlib to binary..."
cat "${STDLIB_ZIP}" >> "${OUTPUT_PATH}"

# Adjust the ZIP offsets so the appended archive is readable
zip -A "${OUTPUT_PATH}" > /dev/null 2>&1 || true

# Generate checksum
cd "${DIST_DIR}"
sha256sum "${OUTPUT_NAME}" > "${OUTPUT_NAME}.sha256"

log_ok "packaged: ${OUTPUT_PATH}"
log_info "  size: $(du -sh "${OUTPUT_PATH}" | cut -f1)"
log_info "  checksum: ${OUTPUT_NAME}.sha256"
