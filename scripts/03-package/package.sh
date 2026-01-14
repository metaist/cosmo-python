#!/bin/bash
# Package Python build artifacts with bundled standard library
#
# This creates a self-contained Cosmopolitan Python executable with
# the standard library embedded as a ZIP archive.
#
# The output is a "fat" APE binary that runs on both x86_64 and aarch64.
# cosmocc automatically compiles for both architectures and embeds both
# in a single binary.
#
# Dependencies: 02-python/compile.sh must have run successfully
# Outputs: ${DIST_DIR}/python-${VERSION}-cosmo.com
#
source "$(dirname "$0")/../common.sh"

PYTHON_VERSION="${1:-}"

if [ -z "$PYTHON_VERSION" ]; then
  log_error "usage: $0 <python_version>"
  log_error "example: $0 3.12.8"
  exit 1
fi

PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"
# Note: BUILD_DIR still uses x86_64 suffix because that's how cosmocc names it,
# but the binary inside contains both x86_64 and aarch64 code
BUILD_DIR="${WORK_DIR}/build-${PYTHON_VERSION}-x86_64"
STAGING_DIR="${WORK_DIR}/staging-${PYTHON_VERSION}"
OUTPUT_NAME="python-${PYTHON_VERSION}-cosmo.com"
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

log_build "packaging Python ${PYTHON_VERSION} (fat APE: x86_64 + aarch64)"

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
STDLIB_ZIP="${WORK_DIR}/stdlib-${PYTHON_VERSION}.zip"
rm -f "${STDLIB_ZIP}"

cd "${STAGING_DIR}/zip"

# Remove files not needed at runtime
rm -f lib/libpython*.a
rm -rf lib/pkgconfig

# Add CA certificates for SSL verification
# These will be accessible at /zip/share/ssl/ inside the binary
if [ -d "${DEPS_DIR}/share/ssl" ]; then
  log_info "including CA certificates..."
  mkdir -p share/ssl
  cp -r "${DEPS_DIR}/share/ssl/certs" share/ssl/ 2>/dev/null || true
  cp "${DEPS_DIR}/share/ssl/cert.pem" share/ssl/ 2>/dev/null || true
fi

# Use zip with -r recursive, -q quiet
# Could use -0 (store, no compression) for faster startup at cost of size
zip -r -q "${STDLIB_ZIP}" lib/ share/

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
