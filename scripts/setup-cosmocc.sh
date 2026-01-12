#!/bin/bash
# Setup cosmocc toolchain
set -euo pipefail

COSMOCC_VERSION="${COSMOCC_VERSION:-4.0.2}"
COSMOCC_URL="https://cosmo.zip/pub/cosmocc/cosmocc-${COSMOCC_VERSION}.zip"
INSTALL_DIR="${INSTALL_DIR:-/tmp/cosmo}"

echo "Setting up cosmocc ${COSMOCC_VERSION}..."

# Download if not already present
if [ ! -f "${INSTALL_DIR}/bin/cosmocc" ]; then
  mkdir -p "${INSTALL_DIR}"
  cd "${INSTALL_DIR}"

  echo "Downloading cosmocc..."
  wget -q "${COSMOCC_URL}" -O cosmocc.zip

  echo "Extracting..."
  unzip -q cosmocc.zip
  rm cosmocc.zip
fi

echo "cosmocc installed at ${INSTALL_DIR}"
echo "Add to PATH: export PATH=\"${INSTALL_DIR}/bin:\$PATH\""

# Verify installation
"${INSTALL_DIR}/bin/cosmocc" --version
