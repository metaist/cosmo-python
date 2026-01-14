#!/bin/bash
# Generate manifest.json for a release
#
# This creates a spanning manifest that includes:
# - All Python versions from the current release
# - All Python versions from previous releases (merged)
#
# The manifest serves as a registry of all available versions across releases.
#
# Usage:
#   ./manifest.sh <release_tag>
#   ./manifest.sh <release_tag> --merge <previous_manifest_url>
#
# Outputs: ${DIST_DIR}/manifest.json
#
source "$(dirname "$0")/../common.sh"

RELEASE_TAG="${1:-}"
REPO="${REPO:-metaist/cosmo-python}"
COSMOCC_VERSION="${COSMOCC_VERSION:-$(get_dep_version cosmocc)}"

# Parse additional arguments
MERGE_URL=""
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --merge)
      MERGE_URL="$2"
      shift 2
      ;;
    *)
      log_error "unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ -z "$RELEASE_TAG" ]; then
  # Default to current date-time
  RELEASE_TAG=$(date -u +"%Y%m%d-%H%M%S")
  log_info "using generated release tag: ${RELEASE_TAG}"
fi

MANIFEST_PATH="${DIST_DIR}/manifest.json"
TEMP_MANIFEST="${DIST_DIR}/.manifest-new.json"
PREV_MANIFEST="${DIST_DIR}/.manifest-prev.json"

log_build "manifest for release ${RELEASE_TAG}"

mkdir -p "${DIST_DIR}"

# Fetch previous manifest if available
if [ -n "$MERGE_URL" ]; then
  log_info "fetching previous manifest from ${MERGE_URL}..."
  # Handle both URLs and local files
  if [[ "$MERGE_URL" == http* ]]; then
    if curl -fsSL "$MERGE_URL" -o "$PREV_MANIFEST" 2>/dev/null; then
      log_info "previous manifest fetched"
    else
      log_warn "could not fetch previous manifest, starting fresh"
      rm -f "$PREV_MANIFEST"
    fi
  elif [ -f "$MERGE_URL" ]; then
    cp "$MERGE_URL" "$PREV_MANIFEST"
    log_info "previous manifest copied from local file"
  else
    log_warn "previous manifest not found at ${MERGE_URL}, starting fresh"
  fi
elif [ -f "$MANIFEST_PATH" ]; then
  log_info "using existing manifest as base"
  cp "$MANIFEST_PATH" "$PREV_MANIFEST"
fi

# Collect all built Python versions from this release
declare -A NEW_VERSIONS
declare -A NEW_CHECKSUMS

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
      # Save checksum for future use
      echo "$checksum  $filename" > "$checksum_file"
    fi
    
    NEW_VERSIONS["$version"]="$filename"
    NEW_CHECKSUMS["$version"]="$checksum"
    log_info "new: ${version} (${checksum:0:16}...)"
  fi
done

# Build merged manifest using jq
log_info "generating manifest..."

# Create base structure for new versions
NEW_VERSIONS_JSON="{"
first=true
for version in $(echo "${!NEW_VERSIONS[@]}" | tr ' ' '\n' | sort -V); do
  filename="${NEW_VERSIONS[$version]}"
  checksum="${NEW_CHECKSUMS[$version]}"
  url="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${filename}"
  
  if [ "$first" = true ]; then
    first=false
  else
    NEW_VERSIONS_JSON+=","
  fi
  
  NEW_VERSIONS_JSON+="\"${version}\": {\"url\": \"${url}\", \"sha256\": \"${checksum}\", \"filename\": \"${filename}\", \"release\": \"${RELEASE_TAG}\"}"
done
NEW_VERSIONS_JSON+="}"

# Merge with previous manifest or create new
if [ -f "$PREV_MANIFEST" ]; then
  log_info "merging with previous manifest..."
  
  # Merge: new versions override old ones with same key
  jq -n \
    --arg release "$RELEASE_TAG" \
    --arg cosmocc "$COSMOCC_VERSION" \
    --arg generated "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    --argjson new_versions "$NEW_VERSIONS_JSON" \
    --slurpfile prev "$PREV_MANIFEST" '
    # Get previous versions, default to empty object
    ($prev[0].versions // {}) as $old_versions |
    
    # Merge: new overrides old
    ($old_versions + $new_versions) as $all_versions |
    
    # Compute latest for each minor version
    ([$all_versions | to_entries[] | {
      minor: (.key | split(".") | .[0:2] | join(".")),
      version: .key
    }] | group_by(.minor) | map({
      key: .[0].minor,
      value: ([.[].version] | sort | last)
    }) | from_entries) as $latest |
    
    # Find default (highest non-prerelease version)
    ([$all_versions | keys[] | select(test("[ab]|rc") | not)] | sort | last // ($all_versions | keys | sort | last)) as $default |
    
    {
      release: $release,
      cosmocc: $cosmocc,
      generated: $generated,
      versions: $all_versions,
      latest: $latest,
      default: $default
    }
  ' > "$TEMP_MANIFEST"
else
  log_info "creating new manifest..."
  
  jq -n \
    --arg release "$RELEASE_TAG" \
    --arg cosmocc "$COSMOCC_VERSION" \
    --arg generated "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    --argjson versions "$NEW_VERSIONS_JSON" '
    # Compute latest for each minor version
    ([$versions | to_entries[] | {
      minor: (.key | split(".") | .[0:2] | join(".")),
      version: .key
    }] | group_by(.minor) | map({
      key: .[0].minor,
      value: ([.[].version] | sort | last)
    }) | from_entries) as $latest |
    
    # Find default (highest non-prerelease version)
    ([$versions | keys[] | select(test("[ab]|rc") | not)] | sort | last // ($versions | keys | sort | last)) as $default |
    
    {
      release: $release,
      cosmocc: $cosmocc,
      generated: $generated,
      versions: $versions,
      latest: $latest,
      default: $default
    }
  ' > "$TEMP_MANIFEST"
fi

# Move temp to final
mv "$TEMP_MANIFEST" "$MANIFEST_PATH"
rm -f "$PREV_MANIFEST"

log_ok "manifest written to ${MANIFEST_PATH}"

# Pretty print summary
echo ""
log_info "Manifest summary:"
jq -r '
  "  Release: \(.release)",
  "  Cosmocc: \(.cosmocc)",
  "  Versions: \(.versions | keys | length)",
  "  Default: \(.default)",
  "",
  "  Available versions:",
  (.versions | to_entries | sort_by(.key) | .[] | "    \(.key) -> \(.value.release)")
' "$MANIFEST_PATH"
