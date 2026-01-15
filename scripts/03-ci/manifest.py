#!/usr/bin/env python3
"""Generate manifest.json for a release.

Handles merging with previous manifest, filtering disabled versions,
computing latest per minor, and proper key ordering.

Usage:
    uv run scripts/03-ci/manifest.py <release_tag> <cosmocc_version> <generated> \
        <manifest_path> <versions_file> <new_versions_json> [prev_manifest_path]
"""

import json
import re
import sys
from pathlib import Path


def version_key(v: str) -> list:
    """Sort versions by semver, handling pre-release tags."""
    parts = v.replace("a", ".a.").replace("b", ".b.").replace("rc", ".rc.").split(".")
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p)))
        else:
            result.append((1, p))
    return result


def is_prerelease(v: str) -> bool:
    """Check if version is a pre-release (alpha, beta, rc)."""
    return bool(re.search(r"[ab]|rc", v))


def generate_manifest(
    release_tag: str,
    cosmocc_version: str,
    generated: str,
    manifest_path: Path,
    versions_file: Path,
    new_versions: dict,
    prev_manifest_path: Path | None = None,
) -> None:
    """Generate manifest.json with proper merging and ordering."""
    # Load disabled versions from versions.json
    disabled = json.loads(versions_file.read_text()).get("python", {}).get("disabled", {})
    if disabled:
        print(f"  disabled versions: {list(disabled.keys())}")

    # Load previous manifest if available
    old_versions = {}
    if prev_manifest_path and prev_manifest_path.exists():
        prev = json.loads(prev_manifest_path.read_text())
        old_versions = prev.get("versions", {})

    # Merge: new overrides old
    all_versions = {**old_versions, **new_versions}

    # Filter out disabled versions
    # Disabled can be "3.10" (whole minor) or "3.10.5" (specific patch)
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
    manifest = {
        "release": release_tag,
        "cosmocc": cosmocc_version,
        "generated": generated,
        "default": default,
        "latest": latest,
        "versions": {k: all_versions[k] for k in sorted(all_versions.keys(), key=version_key)},
    }

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 7:
        print(__doc__)
        sys.exit(1)

    release_tag = sys.argv[1]
    cosmocc_version = sys.argv[2]
    generated = sys.argv[3]
    manifest_path = Path(sys.argv[4])
    versions_file = Path(sys.argv[5])
    new_versions = json.loads(sys.argv[6])
    prev_manifest_path = Path(sys.argv[7]) if len(sys.argv) > 7 else None

    generate_manifest(
        release_tag,
        cosmocc_version,
        generated,
        manifest_path,
        versions_file,
        new_versions,
        prev_manifest_path,
    )
