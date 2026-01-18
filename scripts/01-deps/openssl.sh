#!/bin/bash
# Build OpenSSL with cosmocc for use with Python
#
# Usage: ./openssl.sh [VERSION] [--clean]
#
# Supports both OpenSSL 1.1.x and 3.x series.
#
# Key decisions:
# - Static library only: Cosmopolitan requires static linking
# - no-asm: Maximum compatibility across platforms
# - getrandom: Modern entropy source that works on all Cosmopolitan targets
#
# OpenSSL 3.x requires additional configuration to work with Cosmopolitan:
# - no-quic: Avoids sendmmsg/recvmmsg syscalls not in Cosmopolitan
# - no-dso: Avoids dladdr not in Cosmopolitan
# - -U_FORTIFY_SOURCE: Avoids __memcpy_chk etc. not in Cosmopolitan
# - -DOPENSSL_NO_SECURE_MEMORY: Avoids shm* syscalls not in Cosmopolitan
#
# Security note on disabled features (OpenSSL 3.x):
# - FORTIFY_SOURCE: Defense-in-depth buffer overflow detection. OpenSSL is
#   heavily audited/fuzzed; same tradeoff made by python-build-standalone/musl.
# - Secure memory (mlock): Secrets could swap to disk. Mitigated by encrypted
#   swap or no swap (common in containers). Acceptable for dev/CI use cases.
# - QUIC/async/engine: No security impact; just features not needed.
# - no-legacy: Actually improves security by disabling old algorithms.
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libssl.a, ${DEPS_DIR}/lib/libcrypto.a, ${DEPS_DIR}/include/openssl/
#
source "$(dirname "$0")/../common.sh"

# Parse arguments
parse_dep_args "openssl" "$@"

OPENSSL_VERSION="$DEP_VERSION"
OPENSSL_SHA256="$(get_pkg_sha256 openssl "$OPENSSL_VERSION")"
OPENSSL_URL="$(get_pkg_url openssl "$OPENSSL_VERSION")"
OPENSSL_MAJOR="${OPENSSL_VERSION%%.*}"

# Directory name depends on tarball structure
if [ "$OPENSSL_MAJOR" = "1" ]; then
  OPENSSL_DIR="${WORK_DIR}/openssl-OpenSSL_${OPENSSL_VERSION//./_}"
else
  OPENSSL_DIR="${WORK_DIR}/openssl-${OPENSSL_VERSION}"
fi

# Validate version exists
if [ "$OPENSSL_SHA256" = "null" ] || [ -z "$OPENSSL_SHA256" ]; then
  log_error "openssl ${OPENSSL_VERSION} not found in upstream.cdx.json"
  exit 1
fi

ensure_dirs

# Handle --clean
if [ "$DEP_CLEAN" = true ]; then
  clean_dep "openssl-*" "" \
    "${DEPS_DIR}/lib/libssl.a" \
    "${DEPS_DIR}/lib/libcrypto.a" \
    "${DEPS_DIR}/lib/.aarch64/libssl.a" \
    "${DEPS_DIR}/lib/.aarch64/libcrypto.a" \
    "${DEPS_DIR}/include/openssl"
  rm -rf "${OPENSSL_DIR}"
fi

# Idempotency: skip if already built
skip_if_all_exist "openssl ${OPENSSL_VERSION}" \
  "${DEPS_DIR}/lib/libssl.a" \
  "${DEPS_DIR}/lib/libcrypto.a"

log_build "openssl ${OPENSSL_VERSION}"

# Setup cosmocc
setup_cosmocc
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${COSMO_DIR}/bin/cosmocc" ]; then
  log_error "cosmocc not found at ${COSMO_DIR}/bin/cosmocc"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${OPENSSL_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="openssl-${OPENSSL_VERSION}.tar.gz"
  download_verify_gpg "openssl" "${OPENSSL_VERSION}" "${OPENSSL_URL}" "${TARBALL}" "openssl ${OPENSSL_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${OPENSSL_DIR}"

# Apply getrandom patch for OpenSSL 1.x (3.x handles this differently)
if [ "$OPENSSL_MAJOR" = "1" ]; then
  RAND_FILE="crypto/rand/rand_unix.c"
  if ! grep -q "Force getrandom for Cosmopolitan" "${RAND_FILE}" 2>/dev/null; then
    log_info "applying getrandom patch..."
    if grep -q "defined(__linux)" "${RAND_FILE}"; then
      sed -i 's/#  if defined(__linux) && defined(__NR_getrandom)/#  if 1 \/\* Force getrandom for Cosmopolitan \*\/ || (defined(__linux) \&\& defined(__NR_getrandom))/' "${RAND_FILE}"
      sed -i 's/syscall(__NR_getrandom, buf, buflen, 0)/getrandom(buf, buflen, 0)/' "${RAND_FILE}"
    else
      log_warn "expected pattern not found in ${RAND_FILE}"
    fi
  fi
fi

# Clean any previous build
make clean 2>/dev/null || true

# Configure OpenSSL - different flags for 1.x vs 3.x
log_info "configuring..."

if [ "$OPENSSL_MAJOR" = "1" ]; then
  # OpenSSL 1.x configuration (original, proven approach)
  ./Configure \
    no-shared \
    no-asm \
    no-dso \
    no-dynamic-engine \
    no-engine \
    no-pic \
    no-autoalginit \
    no-autoerrinit \
    --with-rand-seed=getrandom \
    --openssldir="/zip/share/ssl" \
    --prefix="${DEPS_DIR}" \
    CC="${CC}" \
    AR="${AR}" \
    RANLIB="${RANLIB}" \
    CFLAGS="-Os" \
    linux-x86_64
else
  # OpenSSL 3.x configuration
  # Requires additional flags to work with Cosmopolitan's limited libc
  # See security analysis in issue #13
  ./Configure \
    --prefix="${DEPS_DIR}" \
    --libdir=lib \
    --openssldir="/zip/share/ssl" \
    linux-x86_64 \
    no-shared \
    no-tests \
    no-legacy \
    no-async \
    no-engine \
    no-quic \
    no-dso \
    no-asm \
    CC="${CC}" \
    AR="${AR}" \
    RANLIB="${RANLIB}" \
    CFLAGS="-Os -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -DOPENSSL_NO_ASYNC -D__STDC_NO_ATOMICS__=1 -DOPENSSL_NO_SECURE_MEMORY"
fi

# Patch Makefile for static module building
sed -i 's/^\*shared\*/*static*/' Makefile 2>/dev/null || true

log_info "compiling (this may take a few minutes)..."
timed run_dep_make -j"$(nproc)" build_libs

# Manual install - avoid make install_sw because cosmoar conflicts with
# OpenSSL's install script when handling fat binary directories
log_info "installing..."
cp libcrypto.a libssl.a "${DEPS_DIR}/lib/"
cp -r include/openssl "${DEPS_DIR}/include/"

# Handle aarch64 objects if they exist (fat binary support)
if find . -name ".aarch64" -type d | head -1 | grep -q .; then
  log_info "creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"

  # For OpenSSL 3.x, we need to match the exact objects in the x86_64 archives
  # because there are multiple object files with different prefixes (libssl-lib-, libcrypto-lib-, etc.)
  # Simply finding all .o files would include duplicates
  
  # Create aarch64 archives by finding the aarch64 counterpart of each x86_64 object
  for lib in libssl libcrypto; do
    OBJS=""
    for obj in $(ar -t "${lib}.a"); do
      # Find the aarch64 version of this object
      aarch64_obj=$(find . -path "*/.aarch64/${obj}" -type f 2>/dev/null | head -1)
      if [ -n "$aarch64_obj" ]; then
        OBJS="$OBJS $aarch64_obj"
      fi
    done
    if [ -n "$OBJS" ]; then
      # shellcheck disable=SC2086
      ar rcs "${DEPS_DIR}/lib/.aarch64/${lib}.a" $OBJS
    fi
  done
fi

# Download Mozilla CA certificate bundle for SSL verification
# This will be bundled into the final Python binary at /zip/share/ssl/certs/
# We store locally at ${DEPS_DIR}/share/ssl/ to match the /zip/ structure
CACERT_VERSION="${CACERT_VERSION:-$(get_dep_version cacert)}"
CACERT_SHA256="$(get_pkg_sha256 cacert "$CACERT_VERSION")"
CA_BUNDLE_URL="https://curl.se/ca/cacert-${CACERT_VERSION}.pem"
CA_BUNDLE_DIR="${DEPS_DIR}/share/ssl/certs"
CA_BUNDLE_FILE="${DEPS_DIR}/share/ssl/cert.pem"

if [ ! -f "${CA_BUNDLE_FILE}" ]; then
  log_info "downloading Mozilla CA certificate bundle ${CACERT_VERSION}..."
  mkdir -p "${CA_BUNDLE_DIR}"
  
  # Download and verify
  curl -fsSL "${CA_BUNDLE_URL}" -o "${CA_BUNDLE_FILE}.tmp"
  echo "${CACERT_SHA256}  ${CA_BUNDLE_FILE}.tmp" | sha256sum -c - > /dev/null 2>&1 || {
    log_error "CA bundle checksum verification failed!"
    rm -f "${CA_BUNDLE_FILE}.tmp"
    exit 1
  }
  mv "${CA_BUNDLE_FILE}.tmp" "${CA_BUNDLE_FILE}"
  log_info "CA bundle checksum verified"
  
  # Also create individual cert files for compatibility
  # Some tools expect a directory of individual certs
  log_info "extracting individual certificates..."
  cd "${CA_BUNDLE_DIR}"
  awk '
    /-----BEGIN CERTIFICATE-----/ { cert = "" }
    { cert = cert $0 "\n" }
    /-----END CERTIFICATE-----/ {
      # Extract subject CN for filename
      cmd = "echo \"" cert "\" | openssl x509 -noout -subject 2>/dev/null | sed \"s/.*CN = //\" | sed \"s/[^a-zA-Z0-9_.-]/_/g\""
      cmd | getline name
      close(cmd)
      if (name == "") name = "cert_" NR
      print cert > name ".pem"
    }
  ' "${CA_BUNDLE_FILE}" 2>/dev/null || true
  
  # Create hash symlinks (c_rehash equivalent)
  for cert in *.pem; do
    if [ -f "$cert" ]; then
      hash=$(openssl x509 -hash -noout -in "$cert" 2>/dev/null) || continue
      ln -sf "$cert" "${hash}.0" 2>/dev/null || true
    fi
  done
  
  log_ok "CA certificates installed"
fi

log_ok "openssl ${OPENSSL_VERSION} installed"
log_info "  libraries: ${DEPS_DIR}/lib/libssl.a, ${DEPS_DIR}/lib/libcrypto.a"
log_info "  headers:   ${DEPS_DIR}/include/openssl/"
log_info "  ca-certs:  ${CA_BUNDLE_DIR}/"
