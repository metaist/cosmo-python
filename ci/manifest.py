#!/usr/bin/env python3
"""Generate manifest.json for a release.

This creates a spanning manifest that includes:
- All Python versions from the current release
- All Python versions from previous releases (merged)
- Disabled versions (from versions.json) are excluded

The manifest serves as a registry of all available versions across releases.

Usage:
    uv run -m ci.manifest <release_tag> [--merge <url_or_path>]

Outputs: ${DIST_DIR}/manifest.json (default: ./dist/manifest.json)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import VERSIONS_FILE, setup_logging, version_key

# Directories
DIST_DIR = Path(os.environ.get("DIST_DIR", "dist"))

log = logging.getLogger("ci.manifest")


def is_prerelease(v: str) -> bool:
    """Check if version is a pre-release (alpha, beta, rc)."""
    return bool(re.search(r"[ab]|rc", v))


def get_cosmocc_version() -> str:
    """Get cosmocc version from versions.json or environment."""
    if "COSMOCC_VERSION" in os.environ:
        return os.environ["COSMOCC_VERSION"]
    data = json.loads(VERSIONS_FILE.read_text())
    return str(data.get("cosmocc", {}).get("default", "unknown"))


def get_repo() -> str:
    """Get repo from environment or default."""
    return os.environ.get("REPO", "metaist/cosmo-python")


def fetch_previous_manifest(url_or_path: str) -> dict[str, Any] | None:
    """Fetch previous manifest from URL or local path."""
    if url_or_path.startswith("http"):
        log.info(f"Fetching previous manifest from {url_or_path}...")
        try:
            with urllib.request.urlopen(url_or_path, timeout=30) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())
                log.info("Previous manifest fetched")
                return data
        except Exception as e:
            log.warning(f"Could not fetch previous manifest: {e}")
            return None
    else:
        path = Path(url_or_path)
        if path.exists():
            log.info(f"Using previous manifest from {path}")
            return dict(json.loads(path.read_text()))
        else:
            log.warning(f"Previous manifest not found at {path}")
            return None


def collect_new_versions(release_tag: str) -> dict[str, Any]:
    """Collect all built Python versions from dist/."""
    new_versions = {}
    repo = get_repo()

    for artifact in sorted(DIST_DIR.glob("python-*-cosmo.com")):
        filename = artifact.name
        # Extract version from filename: python-3.12.8-cosmo.com
        match = re.match(r"python-(\d+\.\d+\.\d+)-cosmo\.com", filename)
        if not match:
            continue
        version = match.group(1)

        # Get checksum
        checksum_file = artifact.with_suffix(".com.sha256")
        if checksum_file.exists():
            checksum = checksum_file.read_text().split()[0]
        else:
            checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
            checksum_file.write_text(f"{checksum}  {filename}\n")

        url = f"https://github.com/{repo}/releases/download/{release_tag}/{filename}"
        new_versions[version] = {
            "url": url,
            "sha256": checksum,
            "filename": filename,
            "release": release_tag,
        }
        log.info(f"New: {version} ({checksum[:16]}...)")

    return new_versions


def generate_manifest(
    release_tag: str,
    new_versions: dict[str, Any],
    prev_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate manifest with proper merging and ordering."""
    cosmocc_version = get_cosmocc_version()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Load disabled versions from versions.json
    versions_data = json.loads(VERSIONS_FILE.read_text())
    disabled = versions_data.get("python", {}).get("disabled", {})
    if disabled:
        log.warning(f"Disabled versions: {list(disabled.keys())}")

    # Get previous versions
    old_versions = {}
    if prev_manifest:
        old_versions = prev_manifest.get("versions", {})

    # Merge: new overrides old
    all_versions = {**old_versions, **new_versions}

    # Filter out disabled versions
    disabled_patterns = list(disabled.keys())
    all_versions = {
        ver: data
        for ver, data in all_versions.items()
        if not any(ver.startswith(pat) for pat in disabled_patterns)
    }

    # Compute latest for each minor version
    minors: dict[str, str] = {}
    for ver in all_versions:
        minor = ".".join(ver.split(".")[:2])
        if minor not in minors or version_key(ver) > version_key(minors[minor]):
            minors[minor] = ver
    latest = {k: minors[k] for k in sorted(minors.keys(), key=version_key)}

    # Find default (highest non-prerelease version)
    stable_versions = [v for v in all_versions if not is_prerelease(v)]
    if stable_versions:
        default = sorted(stable_versions, key=version_key)[-1]
    else:
        default = sorted(all_versions.keys(), key=version_key)[-1]

    # Build manifest with ordered keys
    return {
        "release": release_tag,
        "cosmocc": cosmocc_version,
        "generated": generated,
        "default": default,
        "latest": latest,
        "versions": {
            k: all_versions[k] for k in sorted(all_versions.keys(), key=version_key)
        },
    }


def print_summary(manifest: dict[str, Any]) -> None:
    """Print manifest summary."""
    print()
    log.info("Manifest summary:")
    print(f"  Release: {manifest['release']}")
    print(f"  Cosmocc: {manifest['cosmocc']}")
    print(f"  Versions: {len(manifest['versions'])}")
    print(f"  Default: {manifest['default']}")
    print()
    print("  Available versions:")
    for ver, data in manifest["versions"].items():
        print(f"    {ver} -> {data.get('release', 'unknown')}")


def main() -> int:
    setup_logging()

    # Parse arguments
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    release_tag = args[0]
    merge_url = None

    i = 1
    while i < len(args):
        if args[i] == "--merge" and i + 1 < len(args):
            merge_url = args[i + 1]
            i += 2
        else:
            log.error(f"Unknown argument: {args[i]}")
            return 1

    # Generate release tag if empty
    if not release_tag:
        release_tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log.info(f"Using generated release tag: {release_tag}")

    log.info(f"Generating manifest for release {release_tag}")

    # Create dist dir
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch previous manifest
    prev_manifest = None
    if merge_url:
        prev_manifest = fetch_previous_manifest(merge_url)
    else:
        # Check for existing manifest
        existing = DIST_DIR / "manifest.json"
        if existing.exists():
            log.info("Using existing manifest as base")
            prev_manifest = json.loads(existing.read_text())

    # Collect new versions
    new_versions = collect_new_versions(release_tag)
    if not new_versions:
        log.warning("No binaries found in dist/")

    # Generate manifest
    manifest = generate_manifest(release_tag, new_versions, prev_manifest)

    # Write manifest
    manifest_path = DIST_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    log.info(f"OK Manifest written to {manifest_path}")

    # Print summary
    print_summary(manifest)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
