#!/bin/bash
# Install system dependencies required for building Python with cosmocc
set -euo pipefail

echo "Installing system dependencies..."

# Check if we have sudo access
if command -v sudo &> /dev/null && sudo -n true 2>/dev/null; then
  SUDO="sudo"
else
  SUDO=""
  echo "Warning: No sudo access, assuming packages are already installed or running as root"
fi

$SUDO apt-get update
$SUDO apt-get install -y \
  build-essential \
  pkg-config \
  zlib1g-dev \
  liblzma-dev \
  libffi-dev \
  libssl-dev \
  libncurses-dev \
  libreadline-dev \
  libgdbm-dev \
  wget \
  unzip

echo "System dependencies installed."
