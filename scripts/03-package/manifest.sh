#!/bin/bash
# Generate manifest.json for a release
#
# This creates a manifest file listing all built Python versions with
# their download URLs and checksums.
#
# Outputs: ${DIST_DIR}/manifest.json
#
source "$(dirname "$0")/../common.sh"

RELEASE_TAG="${1:-}"
REPO="${REPO:-metaist/cosmo-python}"
COSMOCC_VERSION="${COSMOCC_VERSION:-4.0.2}"

if [ -z "$RELEASE_TAG" ]; then
  # Default to current date-time
  RELEASE_TAG=$(date -u +"%Y%m%d-%H%M%S")
  log_info "using generated release tag: ${RELEASE_TAG}"
fi

MANIFEST_PATH="${DIST_DIR}/manifest.json"

log_build "manifest for release ${RELEASE_TAG}"

mkdir -p "${DIST_DIR}"

# Collect all built Python versions
declare -A VERSIONS
declare -A CHECKSUMS

for artifact in "${DIST_DIR}"/python-*-cosmo-*.com; do
  if [ -f "$artifact" ]; then
    filename=$(basename "$artifact")
    # Extract version from filename: python-3.12.8-cosmo-x86_64.com
    version=$(echo "$filename" | sed -E 's/python-([0-9]+\.[0-9]+\.[0-9]+)-cosmo-.*/\1/')
    
    # Get checksum
    checksum_file="${artifact}.sha256"
    if [ -f "$checksum_file" ]; then
      checksum=$(cut -d' ' -f1 < "$checksum_file")
    else
      checksum=$(sha256sum "$artifact" | cut -d' ' -f1)
    fi
    
    VERSIONS["$version"]="$filename"
    CHECKSUMS["$version"]="$checksum"
    log_info "found: ${version} (${checksum:0:16}...)"
  fi
done

if [ ${#VERSIONS[@]} -eq 0 ]; then
  log_error "no artifacts found in ${DIST_DIR}"
  exit 1
fi

# Build the JSON manifest
log_info "generating manifest..."

# Start JSON
cat > "${MANIFEST_PATH}" << EOF
{
  "release": "${RELEASE_TAG}",
  "cosmocc": "${COSMOCC_VERSION}",
  "generated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "versions": {
EOF

# Add each version
first=true
for version in $(echo "${!VERSIONS[@]}" | tr ' ' '\n' | sort -V); do
  filename="${VERSIONS[$version]}"
  checksum="${CHECKSUMS[$version]}"
  url="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${filename}"
  
  if [ "$first" = true ]; then
    first=false
  else
    echo "," >> "${MANIFEST_PATH}"
  fi
  
  cat >> "${MANIFEST_PATH}" << EOF
    "${version}": {
      "url": "${url}",
      "sha256": "${checksum}",
      "filename": "${filename}"
    }
EOF
done

# Close versions object
echo "" >> "${MANIFEST_PATH}"
echo "  }," >> "${MANIFEST_PATH}"

# Add latest mapping (minor version -> latest patch)
echo '  "latest": {' >> "${MANIFEST_PATH}"

declare -A LATEST
for version in "${!VERSIONS[@]}"; do
  minor="${version%.*}"
  if [ -z "${LATEST[$minor]}" ] || [ "$(printf '%s\n' "$version" "${LATEST[$minor]}" | sort -V | tail -1)" = "$version" ]; then
    LATEST["$minor"]="$version"
  fi
done

first=true
for minor in $(echo "${!LATEST[@]}" | tr ' ' '\n' | sort -V); do
  if [ "$first" = true ]; then
    first=false
  else
    echo "," >> "${MANIFEST_PATH}"
  fi
  printf '    "%s": "%s"' "$minor" "${LATEST[$minor]}" >> "${MANIFEST_PATH}"
done

echo "" >> "${MANIFEST_PATH}"
echo "  }," >> "${MANIFEST_PATH}"

# Add default (latest stable)
default_version=$(echo "${!VERSIONS[@]}" | tr ' ' '\n' | grep -v 'a\|b\|rc' | sort -V | tail -1)
if [ -z "$default_version" ]; then
  default_version=$(echo "${!VERSIONS[@]}" | tr ' ' '\n' | sort -V | tail -1)
fi

cat >> "${MANIFEST_PATH}" << EOF
  "default": "${default_version}"
}
EOF

log_ok "manifest written to ${MANIFEST_PATH}"
cat "${MANIFEST_PATH}"
