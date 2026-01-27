#!/usr/bin/env bash
# Build PyO3/Rust extensions for cosmoext loading.
#
# Usage:
#   ./build-pyo3.sh <crate-dir> [--output <file.cosmoext>] [--python <python.com>]
#   ./build-pyo3.sh --setup   # Install Rust nightly + rust-src
#
# Example:
#   ./build-pyo3.sh /path/to/my-pyo3-crate --output my_module.cosmoext
#
# Requirements:
#   - Rust nightly toolchain with rust-src component (use --setup to install)
#   - cosmocc compiler (for libc stubs)
#   - Python with pyelftools (for relocation processing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default values
OUTPUT=""
PYTHON_COM=""
VERBOSE=0
ARCH="x86_64"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Setup Rust nightly with rust-src component
setup_rust() {
    log_info "Setting up Rust nightly for PyO3 builds..."

    # Check if rustup is installed
    if ! command -v rustup &>/dev/null; then
        log_error "rustup not found. Install from https://rustup.rs"
        exit 1
    fi

    # Install nightly
    log_info "Installing Rust nightly toolchain..."
    rustup install nightly

    # Add rust-src component (required for -Z build-std)
    log_info "Adding rust-src component..."
    rustup +nightly component add rust-src

    log_info "Setup complete! You can now build PyO3 extensions."
    exit 0
}

usage() {
    cat << EOF
Usage: $(basename "$0") <crate-dir> [options]
       $(basename "$0") --setup

Build a PyO3/Rust extension for cosmoext loading.

Arguments:
    crate-dir           Path to the Rust crate directory (must have Cargo.toml)

Options:
    -o, --output FILE   Output .cosmoext file (default: <crate-name>.cosmoext)
    -p, --python FILE   Path to python.com for symbol table (default: auto-detect)
    -a, --arch ARCH     Target architecture: x86_64 or aarch64 (default: x86_64)
    -v, --verbose       Verbose output
    -h, --help          Show this help message
    --setup             Install Rust nightly + rust-src component

Requirements:
    - Rust nightly with rust-src (run with --setup to install)
    - cosmocc: Available in PATH or at /tmp/cosmo/bin/cosmocc
    - pyelftools: pip install pyelftools

Example:
    $(basename "$0") --setup                         # First-time setup
    $(basename "$0") ./my-pyo3-crate -o my_module.cosmoext
EOF
    exit "${1:-0}"
}

# Parse arguments
CRATE_DIR=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --setup)
            setup_rust
            ;;
        -o|--output)
            OUTPUT="$2"
            shift 2
            ;;
        -p|--python)
            PYTHON_COM="$2"
            shift 2
            ;;
        -a|--arch)
            ARCH="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage 0
            ;;
        -*)
            log_error "Unknown option: $1"
            usage 1
            ;;
        *)
            if [[ -z "$CRATE_DIR" ]]; then
                CRATE_DIR="$1"
            else
                log_error "Unexpected argument: $1"
                usage 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$CRATE_DIR" ]]; then
    log_error "Missing required argument: crate-dir"
    usage 1
fi

if [[ ! -d "$CRATE_DIR" ]]; then
    log_error "Crate directory does not exist: $CRATE_DIR"
    exit 1
fi

if [[ ! -f "$CRATE_DIR/Cargo.toml" ]]; then
    log_error "No Cargo.toml found in: $CRATE_DIR"
    exit 1
fi

# Get crate name from Cargo.toml
CRATE_NAME=$(grep -m1 '^name' "$CRATE_DIR/Cargo.toml" | sed 's/.*= *"\([^"]*\)".*/\1/' | tr '-' '_')
if [[ -z "$CRATE_NAME" ]]; then
    log_error "Could not determine crate name from Cargo.toml"
    exit 1
fi

# Set default output
if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${CRATE_NAME}.cosmoext"
fi

# Find python.com if not specified
if [[ -z "$PYTHON_COM" ]]; then
    # Try common locations
    for candidate in \
        "$REPO_ROOT/work/build-3.12.12-x86_64/python.com" \
        "$REPO_ROOT/dist/python-3.12.12-cosmo.com" \
        "$(command -v python.com 2>/dev/null || true)"; do
        if [[ -f "$candidate" ]]; then
            PYTHON_COM="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON_COM" || ! -f "$PYTHON_COM" ]]; then
    log_error "Could not find python.com. Specify with --python"
    exit 1
fi

# Find cosmocc
COSMOCC=""
for candidate in \
    "$(command -v cosmocc 2>/dev/null || true)" \
    "/tmp/cosmo/bin/cosmocc" \
    "$HOME/.cosmo/bin/cosmocc"; do
    if [[ -x "$candidate" ]]; then
        COSMOCC="$candidate"
        break
    fi
done

if [[ -z "$COSMOCC" ]]; then
    log_error "cosmocc not found. Install cosmopolitan toolchain."
    exit 1
fi

# Check for nightly Rust
if ! rustup run nightly rustc --version &>/dev/null; then
    log_error "Rust nightly not installed. Run: rustup install nightly"
    exit 1
fi

# Check for rust-src
if ! rustup +nightly component list | grep -q "rust-src (installed)"; then
    log_error "rust-src not installed. Run: rustup +nightly component add rust-src"
    exit 1
fi

log_info "Building PyO3 extension: $CRATE_NAME"
log_info "  Crate: $CRATE_DIR"
log_info "  Output: $OUTPUT"
log_info "  Python: $PYTHON_COM"
log_info "  Arch: $ARCH"

# Create temporary directory
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Create custom target spec
# Note: filename must look like a standard target to avoid confusing pyo3-build-config
TARGET_SPEC="$TMPDIR/x86_64-unknown-linux-musl.json"
if [[ "$ARCH" == "x86_64" ]]; then
    cat > "$TARGET_SPEC" << 'TARGETEOF'
{
  "llvm-target": "x86_64-unknown-linux-musl",
  "target-pointer-width": 64,
  "arch": "x86_64",
  "data-layout": "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128",
  "cpu": "x86-64",
  "os": "linux",
  "env": "musl",
  "vendor": "unknown",
  "panic-strategy": "abort",
  "requires-uwtable": false,
  "dynamic-linking": false,
  "executables": false,
  "crt-static-default": true,
  "crt-static-respected": true,
  "linker-is-gnu": true,
  "allows-weak-linkage": true,
  "has-rpath": false,
  "has-thread-local": false,
  "trap-unreachable": true,
  "position-independent-executables": false,
  "static-position-independent-executables": false,
  "relocation-model": "static",
  "code-model": "large",
  "tls-model": "local-dynamic",
  "disable-redzone": true,
  "frame-pointer": "always",
  "requires-lto": false,
  "eh-frame-header": false,
  "no-default-libraries": true,
  "max-atomic-width": 64,
  "stack-probes": {
    "kind": "none"
  },
  "target-family": [
    "unix"
  ]
}
TARGETEOF
elif [[ "$ARCH" == "aarch64" ]]; then
    TARGET_SPEC="$TMPDIR/aarch64-unknown-linux-musl.json"
    cat > "$TARGET_SPEC" << 'TARGETEOF'
{
  "llvm-target": "aarch64-unknown-linux-musl",
  "target-pointer-width": 64,
  "arch": "aarch64",
  "data-layout": "e-m:e-i8:8:32-i16:16:32-i64:64-i128:128-n32:64-S128",
  "os": "linux",
  "env": "musl",
  "vendor": "unknown",
  "panic-strategy": "abort",
  "requires-uwtable": false,
  "dynamic-linking": false,
  "executables": false,
  "crt-static-default": true,
  "crt-static-respected": true,
  "linker-is-gnu": true,
  "allows-weak-linkage": true,
  "has-rpath": false,
  "has-thread-local": false,
  "trap-unreachable": true,
  "position-independent-executables": false,
  "static-position-independent-executables": false,
  "relocation-model": "static",
  "code-model": "small",
  "tls-model": "local-dynamic",
  "disable-redzone": true,
  "frame-pointer": "always",
  "requires-lto": false,
  "eh-frame-header": false,
  "no-default-libraries": true,
  "max-atomic-width": 128,
  "stack-probes": {
    "kind": "none"
  },
  "target-family": [
    "unix"
  ],
  "features": "+v8a"
}
TARGETEOF
else
    log_error "Architecture $ARCH not supported. Use x86_64 or aarch64."
    exit 1
fi

# Step 1: Build with Cargo
log_info "Step 1/4: Building Rust crate with nightly..."
cd "$CRATE_DIR"

# Check if Cargo.toml needs crate-type modification
# Patch crate-type to staticlib (handles cdylib, rlib, or combinations)
if grep -q 'crate-type' Cargo.toml; then
    log_info "  Patching Cargo.toml: crate-type -> staticlib"
    # Create backup
    cp Cargo.toml Cargo.toml.bak
    # Replace any crate-type line with staticlib only
    sed -i 's/crate-type *= *\[.*\]/crate-type = ["staticlib"]/' Cargo.toml
fi

# Set up environment for C dependencies (cc-rs crate)
# This allows building crates that have C code (like orjson's yyjson)
COSMO_BIN_DIR="$(dirname "$COSMOCC")"
export CC="$COSMOCC"
export CXX="${COSMO_BIN_DIR}/cosmoc++"
export AR="${COSMO_BIN_DIR}/cosmoar"
export RANLIB="${COSMO_BIN_DIR}/cosmoar s"
export CFLAGS="-mcmodel=large -fno-stack-protector"
export CXXFLAGS="-mcmodel=large -fno-stack-protector -fno-exceptions -fno-rtti"

# Copy target spec to crate directory (some build scripts expect it there)
cp "$TARGET_SPEC" "$CRATE_DIR/"

CARGO_ARGS=(
    +nightly build --release
    -Z "build-std=std,panic_abort"
    --target "$TARGET_SPEC"
)

if [[ $VERBOSE -eq 1 ]]; then
    cargo "${CARGO_ARGS[@]}"
else
    cargo "${CARGO_ARGS[@]}" 2>&1 | tail -5
fi

# Restore Cargo.toml if we modified it
if [[ -f Cargo.toml.bak ]]; then
    mv Cargo.toml.bak Cargo.toml
fi

# Find the built library based on architecture
# Note: Cargo may use hyphens or underscores in lib names
CRATE_NAME_UNDERSCORE="${CRATE_NAME//-/_}"
if [[ "$ARCH" == "x86_64" ]]; then
    TARGET_DIR="$CRATE_DIR/target/x86_64-unknown-linux-musl/release"
else
    TARGET_DIR="$CRATE_DIR/target/aarch64-unknown-linux-musl/release"
fi

# Try various naming conventions
LIB_PATH=""
for name in "lib${CRATE_NAME}.a" "lib${CRATE_NAME_UNDERSCORE}.a" "lib_${CRATE_NAME_UNDERSCORE}.a"; do
    if [[ -f "$TARGET_DIR/$name" ]]; then
        LIB_PATH="$TARGET_DIR/$name"
        break
    fi
done

# Fallback: search for any .a file in release directory
if [[ -z "$LIB_PATH" || ! -f "$LIB_PATH" ]]; then
    # shellcheck disable=SC2012
    LIB_PATH=$(ls "$TARGET_DIR"/lib*.a 2>/dev/null | head -1)
fi

if [[ -z "$LIB_PATH" || ! -f "$LIB_PATH" ]]; then
    log_error "Could not find built library. Expected: lib${CRATE_NAME}.a"
    exit 1
fi

log_info "  Built: $LIB_PATH"

# Step 2: Extract and link objects
log_info "Step 2/4: Linking objects..."

OBJDIR="$TMPDIR/objects"
mkdir -p "$OBJDIR"
cd "$OBJDIR"

ar x "$LIB_PATH"

# Find the linker based on architecture
COSMO_LD=""
if [[ "$ARCH" == "x86_64" ]]; then
    for candidate in \
        "/tmp/cosmo/libexec/gcc/x86_64-linux-cosmo/14.1.0/ld.bfd" \
        "$(dirname "$COSMOCC")/../libexec/gcc/x86_64-linux-cosmo/14.1.0/ld.bfd"; do
        if [[ -x "$candidate" ]]; then
            COSMO_LD="$candidate"
            break
        fi
    done
else
    for candidate in \
        "/tmp/cosmo/libexec/gcc/aarch64-linux-cosmo/14.1.0/ld.bfd" \
        "$(dirname "$COSMOCC")/../libexec/gcc/aarch64-linux-cosmo/14.1.0/ld.bfd"; do
        if [[ -x "$candidate" ]]; then
            COSMO_LD="$candidate"
            break
        fi
    done
fi

if [[ -z "$COSMO_LD" ]]; then
    log_error "Could not find cosmopolitan linker (ld.bfd) for $ARCH"
    exit 1
fi

"$COSMO_LD" -r -o "$TMPDIR/combined.o" ./*.o

# Step 3: Add libc stubs
log_info "Step 3/4: Adding libc stubs..."

STUBS_SRC="$REPO_ROOT/src/cosmoext/libc_stubs.c"
if [[ ! -f "$STUBS_SRC" ]]; then
    log_error "libc_stubs.c not found at: $STUBS_SRC"
    exit 1
fi

"$COSMOCC" -c -mcmodel=large -fno-stack-protector \
    -o "$TMPDIR/libc_stubs.o" "$STUBS_SRC" 2>&1 || true

"$COSMO_LD" -r -o "$TMPDIR/final.o" "$TMPDIR/combined.o" "$TMPDIR/libc_stubs.o"

# Step 4: Build cosmoext blob
log_info "Step 4/4: Building cosmoext blob..."

RELOCATE_PY="$REPO_ROOT/src/cosmoext/relocate.py"
if [[ ! -f "$RELOCATE_PY" ]]; then
    log_error "relocate.py not found at: $RELOCATE_PY"
    exit 1
fi

cd "$REPO_ROOT"

PYTHON_CMD="python3"
if command -v uv &>/dev/null; then
    PYTHON_CMD="uv run --with pyelftools python3"
fi

$PYTHON_CMD -c "
import sys
sys.path.insert(0, 'src/cosmoext')
from relocate import build_cosmoext, CosmoExtFatBlob
from pathlib import Path

result = build_cosmoext(
    obj_path=Path('$TMPDIR/final.o'),
    symtab_path=Path('$PYTHON_COM'),
    arch='$ARCH',
    load_address=0x200000000,
    verbose=$([[ $VERBOSE -eq 1 ]] && echo "True" || echo "False")
)

if result:
    fat = CosmoExtFatBlob(x86_64_blob=result)
    with open('$OUTPUT', 'wb') as f:
        fat.write(f)
    print(f'SUCCESS: $OUTPUT ({Path(\"$OUTPUT\").stat().st_size} bytes)')
else:
    print('FAILED to build cosmoext', file=sys.stderr)
    sys.exit(1)
"

log_info "Done! Output: $OUTPUT"
