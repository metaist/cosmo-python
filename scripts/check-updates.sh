#!/usr/bin/env bash
# Check for dependency updates and update versions.json + README.md
#
# Usage: ./scripts/check-updates.sh [--dry-run]
#
# Checks all upstreams for newer versions, updates versions.json with new
# versions and SHA256 hashes, and regenerates README.md with cog.
#
# Uses endoflife.date API for Python status/eol information.
# OpenSSL is fetched but skipped for updates (known Cosmopolitan issues).

# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

DRY_RUN="${1:-}"

# Dependencies to skip updating (but still fetch for reporting)
SKIP_UPDATE=("openssl")

# Track changes
declare -A UPDATES=()
HAS_UPDATES=false

# Cache for endoflife.date API
ENDOFLIFE_CACHE=""

#------------------------------------------------------------------------------
# Version fetching functions
#------------------------------------------------------------------------------

# GitHub releases: get latest release tag
# Usage: fetch_github_latest owner repo [strip_prefix]
fetch_github_latest() {
    local owner="$1" repo="$2" strip="${3:-}"
    local tag
    tag=$(gh api "repos/$owner/$repo/releases/latest" --jq '.tag_name' 2>/dev/null) || return 1
    if [[ -n "$strip" ]]; then
        tag="${tag#"$strip"}"
    fi
    echo "$tag"
}

# GNU FTP: get latest version from directory listing
# Usage: fetch_gnu_latest project [pattern]
fetch_gnu_latest() {
    local project="$1" pattern="${2:-}"
    local url="https://ftp.gnu.org/gnu/$project/"

    # Default pattern: project-X.Y.tar.gz or project-X.Y.Z.tar.gz
    if [[ -z "$pattern" ]]; then
        pattern="${project}-([0-9]+\.[0-9]+(\.[0-9]+)?)"
    fi

    curl -sL "$url" | grep -oE "$pattern" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | sort -V | tail -1
}

# Python.org: get latest patch version for a minor version
# Usage: fetch_python_latest minor_version (e.g., "3.12")
fetch_python_latest() {
    local minor="$1"
    local url="https://www.python.org/ftp/python/"

    curl -sL "$url" | grep -oE "href=\"${minor}\.[0-9]+/\"" | grep -oE "${minor}\.[0-9]+" | sort -V | tail -1
}

# endoflife.date API: get Python version info
# Usage: fetch_endoflife_data
fetch_endoflife_data() {
    if [[ -z "$ENDOFLIFE_CACHE" ]]; then
        ENDOFLIFE_CACHE=$(curl -sL "https://endoflife.date/api/python.json")
    fi
    echo "$ENDOFLIFE_CACHE"
}

# Get status for a Python minor version from endoflife.date
# Usage: get_python_status minor_version
# Returns: prerelease, bugfix, security, or eol
get_python_status() {
    local minor="$1"
    local data today release_date support_date eol_date

    data=$(fetch_endoflife_data | jq -r ".[] | select(.cycle == \"$minor\")")
    if [[ -z "$data" ]]; then
        echo "unknown"
        return
    fi

    today=$(date +%Y-%m-%d)
    release_date=$(echo "$data" | jq -r '.releaseDate')
    support_date=$(echo "$data" | jq -r '.support')
    eol_date=$(echo "$data" | jq -r '.eol')

    # Check if not yet released
    if [[ "$release_date" > "$today" ]]; then
        echo "prerelease"
    # Check if still in bugfix support
    elif [[ "$support_date" > "$today" ]]; then
        echo "bugfix"
    # Check if in security-only support
    elif [[ "$eol_date" > "$today" ]]; then
        echo "security"
    else
        echo "eol"
    fi
}

# Get EOL date for a Python minor version
# Usage: get_python_eol minor_version
get_python_eol() {
    local minor="$1"
    local eol
    eol=$(fetch_endoflife_data | jq -r ".[] | select(.cycle == \"$minor\") | .eol")
    # Convert YYYY-MM-DD to YYYY-MM format
    echo "${eol:0:7}"
}

# SQLite: get latest version from download page
fetch_sqlite_latest() {
    local url="https://www.sqlite.org/download.html"
    # Look for sqlite-autoconf-XXXXXXX.tar.gz pattern, extract version
    local autoconf_ver
    autoconf_ver=$(curl -sL "$url" | grep -oE 'sqlite-autoconf-[0-9]+\.tar\.gz' | head -1 | grep -oE '[0-9]+')

    if [[ -z "$autoconf_ver" ]]; then
        return 1
    fi

    # Convert autoconf version (3510200) to semver (3.51.2)
    # Format: XYYYZZZZ where X=major, YYY=minor, ZZZZ=patch (last two digits usually 00)
    local major minor patch
    major="${autoconf_ver:0:1}"
    minor="${autoconf_ver:1:2}"
    patch="${autoconf_ver:3:2}"

    # Remove leading zeros
    minor=$((10#$minor))
    patch=$((10#$patch))

    echo "$major.$minor.$patch"
}

# Get SQLite autoconf version for a semver
sqlite_to_autoconf() {
    local version="$1"
    local major minor patch
    IFS='.' read -r major minor patch <<< "$version"
    printf "%d%02d%02d00" "$major" "$minor" "$patch"
}

# curl.se CA certs: get latest date
fetch_cacert_latest() {
    local url="https://curl.se/docs/caextract.html"
    curl -sL "$url" | grep -oE 'cacert-[0-9]{4}-[0-9]{2}-[0-9]{2}\.pem' | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}'
}

# sourceware.org bzip2: get latest version
fetch_bz2_latest() {
    local url="https://sourceware.org/pub/bzip2/"
    curl -sL "$url" | grep -oE 'bzip2-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1
}

# OpenSSL 1.1.1 series: EOL, no longer in releases
# Last version was 1.1.1w - we're stuck on 1.1.1u for Cosmo compatibility
fetch_openssl_1_latest() {
    # Return current version since 1.1.1 is EOL and not in releases API
    echo "1.1.1u"
}

#------------------------------------------------------------------------------
# SHA256 fetching
#------------------------------------------------------------------------------

# Download file and compute SHA256
# Usage: fetch_sha256 url
fetch_sha256() {
    local url="$1"
    curl -sL "$url" | sha256sum | cut -d' ' -f1
}

#------------------------------------------------------------------------------
# Update functions
#------------------------------------------------------------------------------

# Update versions.json with a new version
# Usage: update_versions_json dep version sha256 [extra_fields_json]
update_versions_json() {
    local dep="$1" version="$2" sha256="$3" extra="${4:-}"
    local tmp_file
    tmp_file=$(mktemp)

    # Build the version object
    local version_obj="{\"sha256\": \"$sha256\"}"
    if [[ -n "$extra" ]]; then
        version_obj=$(echo "$version_obj" | jq ". + $extra")
    fi

    # Copy GPG fingerprint from previous default version if it exists
    local current_default gpg_fp
    current_default=$(jq -r ".${dep}.default" "$VERSIONS_FILE")
    gpg_fp=$(jq -r ".${dep}.versions.\"${current_default}\".gpg // empty" "$VERSIONS_FILE")
    if [[ -n "$gpg_fp" ]]; then
        version_obj=$(echo "$version_obj" | jq --arg gpg "$gpg_fp" '. + {gpg: $gpg}')
        log_info "  GPG fingerprint: $gpg_fp (copied from $current_default)"
    fi

    # Update versions.json
    jq --arg dep "$dep" \
       --arg ver "$version" \
       --argjson obj "$version_obj" \
       '.[$dep].versions[$ver] = $obj | .[$dep].default = $ver' \
       "$VERSIONS_FILE" > "$tmp_file"

    mv "$tmp_file" "$VERSIONS_FILE"
}

# Regenerate README.md using cog
regenerate_readme() {
    log_info "Regenerating README.md..."
    if command -v uvx &>/dev/null; then
        uvx --from ds-run ds cog
    else
        log_warn "uvx not found, skipping README regeneration"
    fi
}

#------------------------------------------------------------------------------
# Main checking logic
#------------------------------------------------------------------------------

check_dependency() {
    local dep="$1"
    local current_version latest_version

    current_version=$(get_dep_version "$dep")

    case "$dep" in
        cosmocc)
            latest_version=$(fetch_github_latest jart cosmopolitan) || return 1
            ;;
        libffi)
            latest_version=$(fetch_github_latest libffi libffi "v") || return 1
            ;;
        xz)
            latest_version=$(fetch_github_latest tukaani-project xz "v") || return 1
            ;;
        ncurses)
            latest_version=$(fetch_gnu_latest ncurses) || return 1
            ;;
        readline)
            latest_version=$(fetch_gnu_latest readline) || return 1
            ;;
        gdbm)
            latest_version=$(fetch_gnu_latest gdbm) || return 1
            ;;
        bz2)
            latest_version=$(fetch_bz2_latest) || return 1
            ;;
        sqlite)
            latest_version=$(fetch_sqlite_latest) || return 1
            ;;
        cacert)
            latest_version=$(fetch_cacert_latest) || return 1
            ;;
        openssl)
            # Fetch but note we're on 1.1.1 series
            latest_version=$(fetch_openssl_1_latest) || return 1
            ;;
        *)
            log_warn "Unknown dependency: $dep"
            return 1
            ;;
    esac

    echo "$current_version $latest_version"
}

update_dependency() {
    local dep="$1" new_version="$2"
    local url sha256 extra=""

    log_info "Updating $dep to $new_version..."

    # Build download URL based on template
    case "$dep" in
        cosmocc)
            url="https://github.com/jart/cosmopolitan/releases/download/${new_version}/cosmocc-${new_version}.zip"
            ;;
        libffi)
            url="https://github.com/libffi/libffi/releases/download/v${new_version}/libffi-${new_version}.tar.gz"
            ;;
        xz)
            url="https://github.com/tukaani-project/xz/releases/download/v${new_version}/xz-${new_version}.tar.gz"
            ;;
        ncurses)
            url="https://ftp.gnu.org/gnu/ncurses/ncurses-${new_version}.tar.gz"
            ;;
        readline)
            url="https://ftp.gnu.org/gnu/readline/readline-${new_version}.tar.gz"
            ;;
        gdbm)
            url="https://ftp.gnu.org/gnu/gdbm/gdbm-${new_version}.tar.gz"
            ;;
        bz2)
            url="https://sourceware.org/pub/bzip2/bzip2-${new_version}.tar.gz"
            ;;
        sqlite)
            local autoconf_ver
            autoconf_ver=$(sqlite_to_autoconf "$new_version")
            # SQLite URLs include year - we need to figure it out
            # Try current year first, then next year
            local year
            for year in $(date +%Y) $(($(date +%Y) + 1)); do
                url="https://www.sqlite.org/${year}/sqlite-autoconf-${autoconf_ver}.tar.gz"
                if curl -sI "$url" | grep -q "200 OK"; then
                    break
                fi
            done
            extra="{\"autoconf_version\": \"$autoconf_ver\"}"
            ;;
        cacert)
            url="https://curl.se/ca/cacert-${new_version}.pem"
            ;;
        openssl)
            local ver_underscores="${new_version//./_}"
            url="https://github.com/openssl/openssl/archive/refs/tags/OpenSSL_${ver_underscores}.tar.gz"
            ;;
        *)
            log_error "Don't know how to update $dep"
            return 1
            ;;
    esac

    # Fetch SHA256
    log_info "  Fetching SHA256 from $url"
    sha256=$(fetch_sha256 "$url") || {
        log_error "  Failed to fetch $url"
        return 1
    }
    log_info "  SHA256: $sha256"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log_info "  (dry-run) Would update versions.json"
        return 0
    fi

    # Update versions.json
    update_versions_json "$dep" "$new_version" "$sha256" "$extra"

    log_ok "  Updated $dep to $new_version"
}

check_python_versions() {
    local updates=()

    # Read minor versions from versions.json instead of hardcoding
    local minors
    minors=$(jq -r '.python.latest | keys[]' "$VERSIONS_FILE" | sort -V)

    for minor in $minors; do
        local current latest status
        current=$(get_python_latest "$minor")
        latest=$(fetch_python_latest "$minor") || continue
        status=$(get_python_status "$minor")

        if [[ "$status" == "eol" ]]; then
            log_warn "Python $minor: $current (EOL - consider removing)" >&2
            continue
        fi

        if [[ "$current" != "$latest" ]]; then
            log_info "Python $minor: $current -> $latest ($status)" >&2
            updates+=("$minor:$latest")
        else
            log_info "Python $minor: $current ($status)" >&2
        fi
    done

    echo "${updates[*]:-}"
}

update_python_version() {
    local minor="$1" new_version="$2"
    local url sha256 status eol sigstore_identity sigstore_issuer

    log_info "Updating Python $new_version..."

    url="https://www.python.org/ftp/python/${new_version}/Python-${new_version}.tgz"

    log_info "  Fetching SHA256 from $url"
    sha256=$(fetch_sha256 "$url") || {
        log_error "  Failed to fetch $url"
        return 1
    }
    log_info "  SHA256: $sha256"

    # Get status and EOL from endoflife.date API
    status=$(get_python_status "$minor")
    eol=$(get_python_eol "$minor")
    log_info "  Status: $status, EOL: $eol"

    # Copy sigstore info from previous version in this minor series
    local current_version
    current_version=$(get_python_latest "$minor")
    sigstore_identity=$(jq -r ".python.versions.\"$current_version\".sigstore.identity // empty" "$VERSIONS_FILE")
    sigstore_issuer=$(jq -r ".python.versions.\"$current_version\".sigstore.issuer // empty" "$VERSIONS_FILE")
    if [[ -n "$sigstore_identity" ]]; then
        log_info "  Sigstore: $sigstore_identity (copied from $current_version)"
    fi

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log_info "  (dry-run) Would update versions.json"
        return 0
    fi

    # Build version object
    local tmp_file
    tmp_file=$(mktemp)

    if [[ -n "$sigstore_identity" ]] && [[ -n "$sigstore_issuer" ]]; then
        jq --arg ver "$new_version" \
           --arg minor "$minor" \
           --arg sha "$sha256" \
           --arg status "$status" \
           --arg eol "$eol" \
           --arg sig_id "$sigstore_identity" \
           --arg sig_iss "$sigstore_issuer" \
           '.python.versions[$ver] = {eol: $eol, status: $status, sha256: $sha, sigstore: {identity: $sig_id, issuer: $sig_iss}} | .python.latest[$minor] = $ver' \
           "$VERSIONS_FILE" > "$tmp_file"
    else
        jq --arg ver "$new_version" \
           --arg minor "$minor" \
           --arg sha "$sha256" \
           --arg status "$status" \
           --arg eol "$eol" \
           '.python.versions[$ver] = {eol: $eol, status: $status, sha256: $sha} | .python.latest[$minor] = $ver' \
           "$VERSIONS_FILE" > "$tmp_file"
    fi

    mv "$tmp_file" "$VERSIONS_FILE"

    log_ok "  Updated Python $new_version"
}

# Update status/eol for existing Python versions without changing patch version
update_python_metadata() {
    log_info "Checking Python status/eol metadata..."

    local minors
    minors=$(jq -r '.python.latest | keys[]' "$VERSIONS_FILE" | sort -V)

    for minor in $minors; do
        local version current_status current_eol new_status new_eol

        version=$(get_python_latest "$minor")
        current_status=$(jq -r ".python.versions[\"$version\"].status // \"unknown\"" "$VERSIONS_FILE")
        current_eol=$(jq -r ".python.versions[\"$version\"].eol // \"unknown\"" "$VERSIONS_FILE")

        new_status=$(get_python_status "$minor")
        new_eol=$(get_python_eol "$minor")

        if [[ "$current_status" != "$new_status" ]] || [[ "$current_eol" != "$new_eol" ]]; then
            log_info "Python $minor ($version): status $current_status -> $new_status, eol $current_eol -> $new_eol"
            UPDATES["python-$minor-metadata"]="$new_status (eol: $new_eol)"
            HAS_UPDATES=true

            if [[ "$DRY_RUN" != "--dry-run" ]]; then
                local tmp_file
                tmp_file=$(mktemp)

                jq --arg ver "$version" \
                   --arg status "$new_status" \
                   --arg eol "$new_eol" \
                   '.python.versions[$ver].status = $status | .python.versions[$ver].eol = $eol' \
                   "$VERSIONS_FILE" > "$tmp_file"

                mv "$tmp_file" "$VERSIONS_FILE"
            fi
        fi
    done
}

#------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------

main() {
    log_info "Checking for dependency updates..."
    echo

    # Check Python versions
    log_info "=== Python ==="
    local python_updates
    python_updates=$(check_python_versions)

    if [[ -n "$python_updates" ]]; then
        HAS_UPDATES=true
        for update in $python_updates; do
            local minor="${update%:*}"
            local version="${update#*:}"
            update_python_version "$minor" "$version"
            UPDATES["python-$minor"]="$version"
        done
    fi

    # Also check/update metadata for existing versions
    update_python_metadata
    echo

    # Check other dependencies
    log_info "=== Dependencies ==="
    for dep in cosmocc bz2 cacert gdbm libffi ncurses openssl readline sqlite xz; do
        local result current latest
        result=$(check_dependency "$dep") || {
            log_warn "$dep: failed to check"
            continue
        }

        current=$(echo "$result" | cut -d' ' -f1)
        latest=$(echo "$result" | cut -d' ' -f2)

        # Check if this dep is in the skip list
        local skip=false
        for skip_dep in "${SKIP_UPDATE[@]}"; do
            if [[ "$dep" == "$skip_dep" ]]; then
                skip=true
                break
            fi
        done

        if [[ "$skip" == "true" ]]; then
            log_warn "$dep: $current (pinned - skipping updates)"
        elif [[ "$current" != "$latest" ]]; then
            log_info "$dep: $current -> $latest"
            HAS_UPDATES=true
            update_dependency "$dep" "$latest"
            UPDATES["$dep"]="$latest"
        else
            log_info "$dep: $current (current)"
        fi
    done
    echo

    # Regenerate README if there were updates
    if [[ "$HAS_UPDATES" == "true" ]] && [[ "$DRY_RUN" != "--dry-run" ]]; then
        regenerate_readme
    fi

    # Summary
    log_info "=== Summary ==="
    if [[ "$HAS_UPDATES" == "true" ]]; then
        log_ok "Updates applied:"
        for key in "${!UPDATES[@]}"; do
            echo "  - $key: ${UPDATES[$key]}"
        done

        if [[ "$DRY_RUN" != "--dry-run" ]]; then
            echo
            log_info "Files modified:"
            echo "  - versions.json"
            echo "  - README.md"
        fi
    else
        log_info "All dependencies are up to date."
    fi
}

main "$@"
