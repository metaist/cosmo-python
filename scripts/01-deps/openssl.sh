#!/bin/bash
# Build OpenSSL with cosmocc for use with Python
#
# Based on ahgamut/superconfigure's proven approach.
#
# Key decisions:
# - OpenSSL 1.1.1u: Stable, well-tested with Cosmopolitan
# - Static library only: Cosmopolitan requires static linking
# - no-asm: Maximum compatibility across platforms
# - getrandom: Modern entropy source that works on all Cosmopolitan targets
#
# Dependencies: none
# Outputs: ${DEPS_DIR}/lib/libssl.a, ${DEPS_DIR}/lib/libcrypto.a, ${DEPS_DIR}/include/openssl/
#
source "$(dirname "$0")/../common.sh"

# Get version and checksum from versions.json
OPENSSL_VERSION="${OPENSSL_VERSION:-$(get_dep_version openssl)}"
OPENSSL_SHA256="$(get_dep_sha256 openssl)"
# OpenSSL uses underscore format for tags: OpenSSL_1_1_1u
OPENSSL_TAG="OpenSSL_${OPENSSL_VERSION//./_}"
OPENSSL_URL="https://github.com/openssl/openssl/archive/refs/tags/${OPENSSL_TAG}.tar.gz"
OPENSSL_DIR="${WORK_DIR}/openssl-${OPENSSL_TAG}"

ensure_dirs

# Idempotency: skip if already built
skip_if_all_exist "openssl ${OPENSSL_VERSION}" \
  "${DEPS_DIR}/lib/libssl.a" \
  "${DEPS_DIR}/lib/libcrypto.a"

log_build "openssl ${OPENSSL_VERSION}"

# Setup cosmocc
export CC="${COSMO_DIR}/bin/cosmocc"
export AR="${COSMO_DIR}/bin/cosmoar"
export RANLIB="${COSMO_DIR}/bin/cosmoar s"

if [ ! -x "${CC}" ]; then
  log_error "cosmocc not found at ${CC}"
  log_error "run 00-setup/cosmocc.sh first"
  exit 1
fi

# Download if needed
if [ ! -d "${OPENSSL_DIR}" ]; then
  cd "${WORK_DIR}"
  TARBALL="openssl-${OPENSSL_TAG}.tar.gz"
  download_and_verify "${OPENSSL_URL}" "${TARBALL}" "${OPENSSL_SHA256}" "openssl ${OPENSSL_VERSION}"
  tar xzf "${TARBALL}"
  rm "${TARBALL}"
fi

cd "${OPENSSL_DIR}"

# Apply getrandom patch if not already applied
# This ensures reliable entropy on all Cosmopolitan platforms
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

# Clean any previous build
make clean 2>/dev/null || true

# Configure OpenSSL
# Flag explanations:
#   no-shared         - Static libraries only (required for Cosmopolitan)
#   no-asm            - Disable assembly for maximum compatibility
#   no-dso            - Disable dynamic shared object loading
#   no-dynamic-engine - Disable runtime engine loading
#   no-engine         - Disable engine support entirely
#   no-pic            - Disable position-independent code (static linking)
#   --with-rand-seed=getrandom - Use getrandom() for entropy
#
log_info "configuring..."
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

# Patch Setup.stdlib for static module building
sed -i 's/^\*shared\*/*static*/' Makefile 2>/dev/null || true

log_info "compiling (this may take a few minutes)..."
timed make -j"$(nproc)" build_libs

# Manual install - avoid make install_sw because cosmoar conflicts with
# OpenSSL's install script when handling fat binary directories
log_info "installing..."
cp libcrypto.a libssl.a "${DEPS_DIR}/lib/"
cp -r include/openssl "${DEPS_DIR}/include/"

# Handle aarch64 objects if they exist
if find . -name ".aarch64" -type d | head -1 | grep -q .; then
  log_info "creating aarch64 libraries..."
  mkdir -p "${DEPS_DIR}/lib/.aarch64"

  CRYPTO_OBJS=$(find crypto -path "*/.aarch64/*.o" 2>/dev/null || true)
  SSL_OBJS=$(find ssl -path "*/.aarch64/*.o" 2>/dev/null || true)

  if [ -n "${CRYPTO_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libcrypto.a" ${CRYPTO_OBJS}
  fi
  if [ -n "${SSL_OBJS}" ]; then
    ar rcs "${DEPS_DIR}/lib/.aarch64/libssl.a" ${SSL_OBJS}
  fi
fi

# Download Mozilla CA certificate bundle for SSL verification
# This will be bundled into the final Python binary at /zip/share/ssl/certs/
# We store locally at ${DEPS_DIR}/share/ssl/ to match the /zip/ structure
CACERT_VERSION="${CACERT_VERSION:-$(get_dep_version cacert)}"
CACERT_SHA256="$(get_dep_sha256 cacert)"
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
