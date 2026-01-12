#!/bin/bash
# Download and extract Python source
set -euo pipefail

PYTHON_VERSION="${1:-3.12.8}"
WORK_DIR="${WORK_DIR:-$(pwd)/work}"
PATCHES_DIR="${PATCHES_DIR:-$(dirname "$0")/../patches}"

PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"

echo "Downloading Python ${PYTHON_VERSION}..."

mkdir -p "${WORK_DIR}"
cd "${WORK_DIR}"

# Download if not already present
if [ ! -d "Python-${PYTHON_VERSION}" ]; then
  echo "Fetching ${PYTHON_URL}..."
  wget -q "${PYTHON_URL}" -O "Python-${PYTHON_VERSION}.tgz"

  echo "Extracting..."
  tar xzf "Python-${PYTHON_VERSION}.tgz"
  rm "Python-${PYTHON_VERSION}.tgz"
fi

# Apply patches if they exist
PATCH_DIR="${PATCHES_DIR}/${PYTHON_MAJOR_MINOR}"
if [ -d "${PATCH_DIR}" ]; then
  echo "Applying patches from ${PATCH_DIR}..."
  cd "Python-${PYTHON_VERSION}"
  for patch in "${PATCH_DIR}"/*.patch; do
    if [ -f "$patch" ]; then
      echo "  Applying $(basename "$patch")..."
      patch -p1 < "$patch"
    fi
  done
  cd ..
fi

echo "Python source ready at ${WORK_DIR}/Python-${PYTHON_VERSION}"
