#!/usr/bin/env bash
# Build LLVM compiler-rt builtins for cosmoext
# These provide intrinsics needed by Rust extensions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR="$ROOT_DIR/work/compiler-rt"
OUTPUT_DIR="$ROOT_DIR/src/cosmoext/lib"

COSMOCC="${COSMOCC:-/tmp/cosmo/bin/cosmocc}"
LLVM_REPO="https://github.com/llvm/llvm-project.git"

log_info() { echo "[compiler-rt] $*"; }
log_error() { echo "[compiler-rt] ERROR: $*" >&2; }

# Check prerequisites
if [[ ! -x "$COSMOCC" ]]; then
  log_error "cosmocc not found at $COSMOCC"
  exit 1
fi

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

# Clone compiler-rt if needed
if [[ ! -d "$WORK_DIR/llvm-project" ]]; then
  log_info "Cloning LLVM compiler-rt..."
  cd "$WORK_DIR"
  git clone --depth 1 --filter=blob:none --sparse "$LLVM_REPO"
  cd llvm-project
  git sparse-checkout set compiler-rt/lib/builtins
fi

BUILTINS_DIR="$WORK_DIR/llvm-project/compiler-rt/lib/builtins"

# Build for an architecture
build_arch() {
  local arch="$1"
  local cc_flag="$2"
  local build_dir="$WORK_DIR/build-$arch"
  local output="$OUTPUT_DIR/libcompiler_rt-$arch.a"
  
  log_info "Building for $arch..."
  rm -rf "$build_dir"
  mkdir -p "$build_dir"
  
  cd "$BUILTINS_DIR"
  local succeeded=0
  local failed=0
  
  for f in *.c; do
    # Skip files that don't compile or aren't needed
    case "$f" in
      atomic*.c|*xf*.c|*xc3.c|apple_versioning.c|gcc_personality_v0.c|emutls.c|enable_execute_stack.c|clear_cache.c)
        continue
        ;;
    esac
    
    if "$COSMOCC" $cc_flag -c -mcmodel=large -fno-stack-protector -I. \
        "$f" -o "$build_dir/${f%.c}.o" 2>/dev/null; then
      succeeded=$((succeeded + 1))
    else
      failed=$((failed + 1))
      echo "  FAIL: $f"
    fi
  done
  
  log_info "  Compiled: $succeeded, Failed: $failed"
  
  # Create archive
  cd "$build_dir"
  ar rcs "$output" ./*.o
  local size
  size=$(stat -c%s "$output" 2>/dev/null || stat -f%z "$output" 2>/dev/null)
  log_info "  Created $output ($size bytes)"
}

# Build both architectures
build_arch "x86_64" ""
build_arch "aarch64" "--target=aarch64-linux-cosmo"

log_info "Done!"
ls -la "$OUTPUT_DIR"/libcompiler_rt-*.a
