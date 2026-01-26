#!/usr/bin/env bash
# Build libcxx-large.a archives for C++ extension support
#
# These archives are rebuilt versions of Cosmopolitan's libcxx.a with:
#   - -mcmodel=large: Forces 64-bit addressing (required for runtime loading)
#   - -std=c++23: Required for expected.cpp
#   - Patched contention_t.h: Fixes int64_t vs int32_t type mismatch
#
# The archives are NOT tied to any Python version - one set works for all.
#
# Usage:
#   ./scripts/libcxx-large.sh [--clean]
#
# Requirements:
#   - cosmocc toolchain (downloads automatically if not present)
#   - cosmopolitan source (clones automatically if not present)
#
# Output:
#   src/cosmoext/lib/libcxx-large-x86_64.a
#   src/cosmoext/lib/libcxx-large-aarch64.a

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR="$ROOT_DIR/work"
OUTPUT_DIR="$ROOT_DIR/src/cosmoext/lib"

# Versions - update these as needed
COSMOCC_VERSION="4.0.2"
COSMO_COMMIT="master"  # or pin to specific commit

COSMOCC_DIR="$WORK_DIR/cosmocc-$COSMOCC_VERSION"
COSMO_SRC_DIR="$WORK_DIR/cosmopolitan"
BUILD_DIR="$WORK_DIR/libcxx-large-build"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}WARNING:${NC} $1"; }
error() { echo -e "${RED}ERROR:${NC} $1"; exit 1; }

# Parse arguments
CLEAN=false
for arg in "$@"; do
  case $arg in
    --clean) CLEAN=true ;;
    --help|-h)
      echo "Usage: $0 [--clean]"
      echo ""
      echo "Build libcxx-large.a archives for C++ extension support."
      echo ""
      echo "Options:"
      echo "  --clean  Remove build artifacts and rebuild from scratch"
      echo ""
      exit 0
      ;;
    *) error "Unknown argument: $arg" ;;
  esac
done

if $CLEAN; then
  log "Cleaning build directory..."
  rm -rf "$BUILD_DIR"
fi

mkdir -p "$WORK_DIR" "$OUTPUT_DIR" "$BUILD_DIR"

# === Download/verify cosmocc ===
if [[ ! -d "$COSMOCC_DIR" ]]; then
  log "Downloading cosmocc $COSMOCC_VERSION..."
  cd "$WORK_DIR"
  
  COSMOCC_URL="https://cosmo.zip/pub/cosmocc/cosmocc-$COSMOCC_VERSION.zip"
  curl -fSL -o "cosmocc-$COSMOCC_VERSION.zip" "$COSMOCC_URL"
  unzip -q "cosmocc-$COSMOCC_VERSION.zip" -d "cosmocc-$COSMOCC_VERSION"
  rm "cosmocc-$COSMOCC_VERSION.zip"
fi

COSMOC="$COSMOCC_DIR/bin/cosmoc++"
COSMO_AR_X86="$COSMOCC_DIR/bin/x86_64-linux-cosmo-ar"
COSMO_AR_ARM="$COSMOCC_DIR/bin/aarch64-linux-cosmo-ar"

[[ -x "$COSMOC" ]] || error "cosmoc++ not found at $COSMOC"

# === Clone/update cosmopolitan source ===
if [[ ! -d "$COSMO_SRC_DIR" ]]; then
  log "Cloning cosmopolitan source..."
  git clone --depth=1 https://github.com/jart/cosmopolitan.git "$COSMO_SRC_DIR"
else
  log "Updating cosmopolitan source..."
  cd "$COSMO_SRC_DIR"
  git fetch origin
  git checkout "$COSMO_COMMIT"
  git pull origin "$COSMO_COMMIT" 2>/dev/null || true
fi

LIBCXX_SRC="$COSMO_SRC_DIR/third_party/libcxx"
[[ -d "$LIBCXX_SRC" ]] || error "libcxx source not found at $LIBCXX_SRC"

# === Create patched headers ===
# The cosmocc toolchain's contention_t.h doesn't include __COSMOPOLITAN__ in the
# int32_t condition, but cosmo_futex_wait expects int*. This patch fixes it.
log "Creating patched headers..."
PATCH_DIR="$BUILD_DIR/patched-headers/__atomic"
mkdir -p "$PATCH_DIR"

cat > "$PATCH_DIR/contention_t.h" << 'HEADER'
//===----------------------------------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
// PATCHED for cosmo-python: Added __COSMOPOLITAN__ to int32_t condition
// to match cosmo_futex_wait(int*, ...) signature.

#ifndef _LIBCPP___ATOMIC_CONTENTION_T_H
#define _LIBCPP___ATOMIC_CONTENTION_T_H

#include <__atomic/cxx_atomic_impl.h>
#include <__config>
#include <cstdint>

#if !defined(_LIBCPP_HAS_NO_PRAGMA_SYSTEM_HEADER)
#  pragma GCC system_header
#endif

_LIBCPP_BEGIN_NAMESPACE_STD

// PATCH: Added __COSMOPOLITAN__ - cosmo_futex_wait expects int*, not long int*
#if defined(__linux__) || defined(__COSMOPOLITAN__) || (defined(_AIX) && !defined(__64BIT__))
using __cxx_contention_t = int32_t;
#else
using __cxx_contention_t = int64_t;
#endif

using __cxx_atomic_contention_t = __cxx_atomic_impl<__cxx_contention_t>;

_LIBCPP_END_NAMESPACE_STD

#endif // _LIBCPP___ATOMIC_CONTENTION_T_H
HEADER

# === Build object files ===
log "Building libcxx with -mcmodel=large..."

OBJ_X86="$BUILD_DIR/obj-x86_64"
OBJ_ARM="$BUILD_DIR/obj-aarch64"
mkdir -p "$OBJ_X86" "$OBJ_ARM"

# Compiler flags
# -mcmodel=large: Required for runtime loading (64-bit addresses)
# -std=c++23: Required for expected.cpp (bad_expected_access<void>)
# -ffunction-sections -fdata-sections: Enable linker garbage collection
# -fexceptions -frtti: C++ features needed by STL
# -I patched headers: Fix contention_t.h type mismatch
FLAGS="-c -std=c++23 -mcmodel=large"
FLAGS="$FLAGS -ffunction-sections -fdata-sections"
FLAGS="$FLAGS -fexceptions -frtti"
FLAGS="$FLAGS -O2 -fno-stack-protector"
FLAGS="$FLAGS -Wno-alloc-size-larger-than"
FLAGS="$FLAGS -DLIBCXX_BUILDING_LIBCXXABI -D_LIBCPP_BUILDING_LIBRARY"
FLAGS="$FLAGS -I$BUILD_DIR/patched-headers"

count=0
failed=0
failed_files=""

for src in "$LIBCXX_SRC"/*.cpp; do
  name=$(basename "$src" .cpp)
  printf "  %-40s" "$name.cpp"
  
  if $COSMOC $FLAGS -o "$OBJ_X86/$name.o" "$src" 2>/dev/null; then
    # cosmoc++ creates .aarch64 subdirectory with ARM objects
    if [[ -f "$OBJ_X86/.aarch64/$name.o" ]]; then
      mv "$OBJ_X86/.aarch64/$name.o" "$OBJ_ARM/$name.o"
    fi
    echo -e "${GREEN}ok${NC}"
    ((count++)) || true
  else
    echo -e "${RED}FAILED${NC}"
    ((failed++)) || true
    failed_files="$failed_files $name.cpp"
  fi
done

# Clean up empty .aarch64 directory
rmdir "$OBJ_X86/.aarch64" 2>/dev/null || true

echo ""
log "Built: $count files, Failed: $failed files"

if [[ $failed -gt 0 ]]; then
  warn "Failed files:$failed_files"
fi

# === Create archives ===
log "Creating archives..."

$COSMO_AR_X86 rcs "$OUTPUT_DIR/libcxx-large-x86_64.a" "$OBJ_X86"/*.o
$COSMO_AR_ARM rcs "$OUTPUT_DIR/libcxx-large-aarch64.a" "$OBJ_ARM"/*.o

echo ""
log "Created archives:"
ls -lh "$OUTPUT_DIR"/libcxx-large-*.a

# === Verify ===
log "Verifying archives..."
x86_count=$($COSMO_AR_X86 t "$OUTPUT_DIR/libcxx-large-x86_64.a" | wc -l)
arm_count=$($COSMO_AR_ARM t "$OUTPUT_DIR/libcxx-large-aarch64.a" | wc -l)
echo "  x86_64:  $x86_count object files"
echo "  aarch64: $arm_count object files"

if [[ $x86_count -ne $arm_count ]]; then
  warn "Object file count mismatch between architectures!"
fi

echo ""
log "Done! Archives ready at:"
echo "  $OUTPUT_DIR/libcxx-large-x86_64.a"
echo "  $OUTPUT_DIR/libcxx-large-aarch64.a"
