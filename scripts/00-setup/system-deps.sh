#!/bin/bash
# Install system dependencies required for building Python with cosmocc
source "$(dirname "$0")/../common.sh"

log_info "checking system dependencies..."

# Check if required tools are available
MISSING=()

for cmd in wget curl unzip tar patch make gcc; do
  if ! command -v "$cmd" &> /dev/null; then
    MISSING+=("$cmd")
  fi
done

if [ ${#MISSING[@]} -eq 0 ]; then
  log_skip "all system dependencies already installed"
  exit 0
fi

log_build "installing: ${MISSING[*]}"

# Check if we have sudo access
if command -v sudo &> /dev/null && sudo -n true 2>/dev/null; then
  SUDO="sudo"
elif [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  log_error "need root access to install: ${MISSING[*]}"
  log_error "run: sudo apt-get install -y build-essential pkg-config wget curl unzip"
  exit 1
fi

# Detect package manager and install
if command -v apt-get &> /dev/null; then
  $SUDO apt-get update
  $SUDO apt-get install -y build-essential pkg-config wget curl unzip
elif command -v dnf &> /dev/null; then
  $SUDO dnf install -y gcc gcc-c++ make pkg-config wget curl unzip patch
elif command -v yum &> /dev/null; then
  $SUDO yum install -y gcc gcc-c++ make pkgconfig wget curl unzip patch
else
  log_error "unsupported package manager; install manually: ${MISSING[*]}"
  exit 1
fi

log_ok "system dependencies installed"
