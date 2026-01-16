#!/usr/bin/env python3
"""Normalize key ordering in versions.json.

Package order: python, cosmocc, then alphabetical
Version order: semver sorted (not alphabetical)
Key order within versions: notes, eol, status, url, sha256, gpg/sigstore, license, license_url

Usage:
    uv run -m ci.normalize
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from .common import VERSIONS_FILE, setup_logging, version_key

log = logging.getLogger("ci.normalize")


def sort_version_keys(ver_data: dict[str, object]) -> dict[str, object]:
    """Sort keys within a version entry."""
    key_order = [
        "notes",
        "eol",
        "status",
        "url",
        "sha256",
        "gpg",
        "sigstore",
        "license",
        "license_url",
    ]
    sorted_data = {}
    # First add keys in preferred order
    for k in key_order:
        if k in ver_data:
            sorted_data[k] = ver_data[k]
    # Then any remaining keys alphabetically
    for k in sorted(ver_data.keys()):
        if k not in sorted_data:
            sorted_data[k] = ver_data[k]
    return sorted_data


def sort_package_keys(pkg_data: dict[str, object]) -> dict[str, object]:
    """Sort keys within a package entry."""
    key_order = ["default", "disabled", "latest", "versions"]
    sorted_data = {}
    for k in key_order:
        if k in pkg_data:
            sorted_data[k] = pkg_data[k]
    for k in sorted(pkg_data.keys()):
        if k not in sorted_data:
            sorted_data[k] = pkg_data[k]
    return sorted_data


def normalize(path: Path) -> None:
    """Normalize versions.json key ordering."""
    data = json.loads(path.read_text())

    # Sort packages: python, cosmocc first, then alphabetical
    pkg_order = ["python", "cosmocc"] + sorted(
        k for k in data.keys() if k not in ["python", "cosmocc"]
    )

    sorted_data = {}
    for pkg in pkg_order:
        if pkg not in data:
            continue
        pkg_data = data[pkg]

        # Sort versions by semver
        if "versions" in pkg_data:
            versions = pkg_data["versions"]
            sorted_versions = {}
            for ver in sorted(versions.keys(), key=version_key):
                sorted_versions[ver] = sort_version_keys(versions[ver])
            pkg_data["versions"] = sorted_versions

        # Sort package-level keys
        sorted_data[pkg] = sort_package_keys(pkg_data)

    path.write_text(json.dumps(sorted_data, indent=2) + "\n")


def main() -> int:
    setup_logging()
    normalize(VERSIONS_FILE)
    log.info("OK versions.json normalized")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
