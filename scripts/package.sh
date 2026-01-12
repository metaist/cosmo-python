#!/bin/bash
# Package Python build artifacts with bundled standard library
set -euo pipefail

PYTHON_VERSION="${1:-3.12.8}"
ARCH="${2:-x86_64}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
DIST_DIR="${DIST_DIR:-$(pwd)/dist}"
COSMO_DIR="${COSMO_DIR:-/tmp/cosmo}"

SRC_DIR="${WORK_DIR}/Python-${PYTHON_VERSION}"
BUILD_DIR="${WORK_DIR}/build-${ARCH}"
STAGING_DIR="${WORK_DIR}/staging-${ARCH}"

echo "Packaging Python ${PYTHON_VERSION} (${ARCH})..."

mkdir -p "${DIST_DIR}"

# Find the built binary
BINARY=""
for candidate in "${BUILD_DIR}/python.com" "${BUILD_DIR}/python"; do
  if [ -f "$candidate" ]; then
    BINARY="$candidate"
    break
  fi
done

if [ -z "${BINARY}" ]; then
  echo "Error: Could not find built Python binary in ${BUILD_DIR}"
  ls -la "${BUILD_DIR}"
  exit 1
fi

# Install Python to staging directory to get the standard library
echo "Installing Python to staging directory..."
rm -rf "${STAGING_DIR}"
cd "${BUILD_DIR}"
make install DESTDIR="${STAGING_DIR}" > /dev/null 2>&1

# Verify stdlib was installed
if [ ! -d "${STAGING_DIR}/zip/lib/python3.12" ]; then
  echo "Error: Standard library not found in staging directory"
  exit 1
fi

echo "Standard library size: $(du -sh "${STAGING_DIR}/zip/lib/python3.12" | cut -f1)"

# Create the output binary by copying the base binary
OUTPUT_NAME="python-${PYTHON_VERSION}-cosmo-${ARCH}.com"
OUTPUT_PATH="${DIST_DIR}/${OUTPUT_NAME}"
cp "${BINARY}" "${OUTPUT_PATH}"
chmod +x "${OUTPUT_PATH}"

# Create a ZIP of the standard library
# The ZIP is appended to the binary and accessible via /zip/ paths
echo "Creating stdlib ZIP archive..."
STDLIB_ZIP="${WORK_DIR}/stdlib-${ARCH}.zip"
rm -f "${STDLIB_ZIP}"

cd "${STAGING_DIR}/zip"
# Remove files not needed at runtime
rm -f lib/libpython*.a
rm -rf lib/pkgconfig

# Use zip with -0 (store, no compression) for faster startup, or remove for smaller size
# The -r flag is recursive, -q is quiet
zip -r -q "${STDLIB_ZIP}" lib/

echo "Stdlib ZIP size: $(du -sh "${STDLIB_ZIP}" | cut -f1)"

# Append the ZIP to the binary
# For APE binaries, we can simply concatenate the ZIP
echo "Appending stdlib to binary..."
cat "${STDLIB_ZIP}" >> "${OUTPUT_PATH}"

# Adjust the ZIP offsets so the appended archive is readable
# The -A flag adjusts stored offsets for a self-extracting archive
zip -A "${OUTPUT_PATH}" > /dev/null 2>&1 || true

echo "Final binary size: $(du -sh "${OUTPUT_PATH}" | cut -f1)"

# Generate checksum
cd "${DIST_DIR}"
sha256sum "${OUTPUT_NAME}" > "${OUTPUT_NAME}.sha256"

echo ""
echo "Packaged: ${OUTPUT_PATH}"
echo "Checksum: ${OUTPUT_NAME}.sha256"
ls -lh "${DIST_DIR}/${OUTPUT_NAME}"*
