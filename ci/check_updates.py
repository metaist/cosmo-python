#!/usr/bin/env python3
"""Check for dependency updates and update versions.json + README.md.

Usage: uv run -m ci.check_updates [--dry-run]

Checks all upstreams (see ci/upstreams/) for newer versions, updates
versions.json with new versions and SHA256 hashes, and regenerates
README.md with cog.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any

from .common import VERSIONS_FILE, load_versions, setup_logging, version_key
from .upstreams import DEPS, PythonUpstream
from .upstreams.http import fetch_sha256


DRY_RUN = "--dry-run" in sys.argv

log = logging.getLogger("ci.check_updates")


def save_versions(data: dict[str, Any]) -> None:
    """Save versions.json with normalized key ordering."""
    from .normalize import normalize

    VERSIONS_FILE.write_text(json.dumps(data, indent=2) + "\n")
    normalize(VERSIONS_FILE)


def get_dep_license(data: dict[str, Any], dep: str) -> tuple[str, str] | None:
    """Get license info from default version."""
    default = data.get(dep, {}).get("default")
    if not default:
        return None
    ver_info = data.get(dep, {}).get("versions", {}).get(default, {})
    lic = ver_info.get("license")
    url = ver_info.get("license_url", "")
    if lic:
        return (str(lic), str(url))
    return None


def update_dependency(data: dict[str, Any], dep: str, new_version: str) -> bool:
    """Update a dependency to a new version."""
    log.info(f"Updating {dep} to {new_version}...")

    upstream = DEPS.get(dep)
    if not upstream:
        log.error(f"  Unknown dependency: {dep}")
        return False

    url = upstream.build_url(new_version)
    if not url:
        log.error(f"  Don't know how to build URL for {dep}")
        return False

    try:
        sha256 = fetch_sha256(url)
    except Exception as e:
        log.error(f"  Failed to fetch {url}: {e}")
        return False

    if DRY_RUN:
        log.info("  (dry-run) Would update versions.json")
        return True

    # Build version entry
    ver_entry: dict[str, Any] = {
        "url": url,
        "sha256": sha256,
    }

    # Copy GPG fingerprint from previous default
    current_default = data.get(dep, {}).get("default")
    if current_default:
        gpg = data[dep]["versions"].get(current_default, {}).get("gpg")
        if gpg:
            ver_entry["gpg"] = gpg
            log.info(f"  GPG fingerprint: {gpg} (copied from {current_default})")

    # Copy license from current default
    license_info = get_dep_license(data, dep)
    if license_info:
        ver_entry["license"], ver_entry["license_url"] = license_info
        log.info(f"  License: {license_info[0]}")

    # Update data
    if dep not in data:
        data[dep] = {"versions": {}}
    data[dep]["versions"][new_version] = ver_entry
    data[dep]["default"] = new_version

    log.info(f"OK Updated {dep} to {new_version}")
    return True


def update_python_version(
    data: dict[str, Any], minor: str, new_version: str, python: PythonUpstream
) -> bool:
    """Update a Python version."""
    log.info(f"Updating Python {minor} to {new_version}...")

    url = python.build_url(new_version)

    try:
        sha256 = fetch_sha256(url)
    except Exception as e:
        log.error(f"  Failed to fetch {url}: {e}")
        return False

    if DRY_RUN:
        log.info("  (dry-run) Would update versions.json")
        return True

    # Build version entry
    ver_entry: dict[str, Any] = {
        "url": url,
        "sha256": sha256,
    }

    # Get status and eol
    status = python.get_status(minor)
    eol = python.get_eol(minor)
    if eol:
        ver_entry["eol"] = eol
    if status:
        ver_entry["status"] = status

    # Copy sigstore info from previous version
    current = data["python"]["latest"].get(minor)
    if current:
        sigstore = data["python"]["versions"].get(current, {}).get("sigstore")
        if sigstore:
            ver_entry["sigstore"] = sigstore
            log.info(f"  Sigstore: {sigstore['identity']} (copied from {current})")

    # Copy license
    license_info = get_dep_license(data, "python")
    if license_info:
        ver_entry["license"], ver_entry["license_url"] = license_info

    # Update data
    data["python"]["versions"][new_version] = ver_entry
    data["python"]["latest"][minor] = new_version

    log.info(f"OK Updated Python {minor} to {new_version}")
    return True


def check_python_versions(
    data: dict[str, Any], python: PythonUpstream
) -> list[tuple[str, str]]:
    """Check for Python updates, return list of (minor, new_version) tuples."""
    updates = []
    for minor in sorted(data["python"]["latest"].keys(), key=version_key):
        current = data["python"]["latest"][minor]
        latest = python.fetch_latest(minor)
        status = python.get_status(minor)

        if status == "eol":
            log.warning(f"Python {minor}: {current} (EOL - consider removing)")
            continue

        if latest and latest != current:
            log.info(f"Python {minor}: {current} -> {latest} ({status})")
            updates.append((minor, latest))
        else:
            log.info(f"Python {minor}: {current} ({status})")

    return updates


def check_dependencies(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Check for dependency updates, return list of (dep, new_version) tuples."""
    updates = []
    dep_order = [
        "cosmocc",
        "bz2",
        "cacert",
        "gdbm",
        "libffi",
        "ncurses",
        "openssl",
        "readline",
        "sqlite",
        "xz",
    ]

    for dep in dep_order:
        current = data.get(dep, {}).get("default", "unknown")
        upstream = DEPS.get(dep)
        if not upstream:
            log.warning(f"{dep}: unknown upstream")
            continue

        try:
            latest = upstream.fetch_latest()
        except Exception as e:
            log.warning(f"{dep}: {current} (failed to check: {e})")
            continue

        if not latest:
            log.warning(f"{dep}: {current} (failed to check)")
            continue

        if latest != current:
            log.info(f"{dep}: {current} -> {latest}")
            updates.append((dep, latest))
        else:
            log.info(f"{dep}: {current} (current)")

    return updates


def ensure_license_info(data: dict[str, Any]) -> bool:
    """Ensure all versions have license info (backfill from default)."""
    updated = False
    for dep in data:
        license_info = get_dep_license(data, dep)
        if not license_info:
            continue

        lic, url = license_info
        for ver in data[dep].get("versions", {}):
            ver_data = data[dep]["versions"][ver]
            if "license" not in ver_data:
                log.info(f"Adding license info to {dep} {ver}")
                ver_data["license"] = lic
                ver_data["license_url"] = url
                updated = True

    return updated


def regenerate_readme() -> None:
    """Regenerate README.md using cog."""
    log.info("Regenerating README.md...")
    try:
        subprocess.run(["uvx", "--from", "ds-run", "ds", "cog"], check=True)
    except FileNotFoundError:
        log.warning("uvx not found, skipping README regeneration")
    except subprocess.CalledProcessError:
        log.warning("README regeneration failed")


def main() -> int:
    setup_logging()

    log.info("Checking for dependency updates...")
    print()

    data = load_versions()
    python = PythonUpstream()
    has_updates = False

    # Ensure license info on all versions
    if ensure_license_info(data):
        has_updates = True
        if DRY_RUN:
            log.info("(dry-run) Would add missing license info")
        else:
            log.info("OK Added missing license info")
    print()

    # Check Python versions
    log.info("=== Python ===")
    python_updates = check_python_versions(data, python)
    for minor, version in python_updates:
        if update_python_version(data, minor, version, python):
            has_updates = True
    print()

    # Check dependencies
    log.info("=== Dependencies ===")
    dep_updates = check_dependencies(data)
    for dep, version in dep_updates:
        if update_dependency(data, dep, version):
            has_updates = True
    print()

    # Save and regenerate
    if has_updates and not DRY_RUN:
        save_versions(data)
        regenerate_readme()

    # Summary
    log.info("=== Summary ===")
    if has_updates:
        log.info("OK Updates applied:" if not DRY_RUN else "OK Updates found:")
        for minor, version in python_updates:
            print(f"  - python-{minor}: {version}")
        for dep, version in dep_updates:
            print(f"  - {dep}: {version}")
        if not DRY_RUN:
            print()
            log.info("Files modified:")
            print("  - versions.json")
            print("  - README.md")
    else:
        log.info("All dependencies are up to date.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
