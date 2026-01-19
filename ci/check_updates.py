#!/usr/bin/env python3
"""Check for dependency updates and update upstream.cdx.json + README.md.

Usage: uv run -m ci.check_updates [--dry-run]

Checks all upstreams (see ci/upstreams/) for newer versions, updates
upstream.cdx.json with new versions and SHA256 hashes, and regenerates
README.md with cog.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from . import cdx
from .common import CDX_FILE, setup_logging, version_key
from .upstreams import DEPS, PythonUpstream
from .upstreams import openssl as openssl_upstream
from .upstreams.http import fetch_sha256

DRY_RUN = "--dry-run" in sys.argv

log = logging.getLogger("ci.check_updates")


def update_dependency(bom: cdx.Bom, dep: str, new_version: str) -> bool:
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
    except (OSError, ValueError) as e:
        log.error(f"  Failed to fetch {url}: {e}")
        return False

    if DRY_RUN:
        log.info("  (dry-run) Would update upstream.cdx.json")
        return True

    # Get current default to copy metadata
    current = bom.get_default_component(dep)

    # Get EOL/status for OpenSSL
    eol = openssl_upstream.get_eol(new_version) if dep == "openssl" else None
    status = openssl_upstream.get_status(new_version) if dep == "openssl" else None

    # Build new component with regenerated PURL
    purl = upstream.build_purl(new_version)

    comp = cdx.Component(
        name=dep,
        version=new_version,
        url=url,
        sha256=sha256,
        license=current.license if current else "",
        license_url=current.license_url if current else None,
        gpg=current.gpg if current else None,
        purl=purl,
        component_type=current.component_type if current else "library",
        eol=eol,
        status=status,
    )

    if comp.gpg:
        log.info(f"  GPG fingerprint: {comp.gpg} (copied)")
    if comp.license:
        log.info(f"  License: {comp.license}")

    bom.add_component(comp)
    bom.set_default(dep, new_version)

    log.info(f"OK Updated {dep} to {new_version}")
    return True


def update_python_version(
    bom: cdx.Bom, minor: str, new_version: str, python: PythonUpstream
) -> bool:
    """Update a Python version."""
    log.info(f"Updating Python {minor} to {new_version}...")

    url = python.build_url(new_version)

    try:
        sha256 = fetch_sha256(url)
    except (OSError, ValueError) as e:
        log.error(f"  Failed to fetch {url}: {e}")
        return False

    if DRY_RUN:
        log.info("  (dry-run) Would update upstream.cdx.json")
        return True

    # Get current version to copy metadata
    current_version = bom.get_latest_version("python", minor)
    current = bom.get_component("python", current_version) if current_version else None

    # Get status and eol from upstream
    status = python.get_status(minor)
    eol = python.get_eol(minor)

    # Build new component
    comp = cdx.Component(
        name="python",
        version=new_version,
        url=url,
        sha256=sha256,
        license=current.license if current else "PSF-2.0",
        license_url=current.license_url if current else "https://docs.python.org/3/license.html",
        sigstore_identity=current.sigstore_identity if current else None,
        sigstore_issuer=current.sigstore_issuer if current else None,
        eol=eol,
        status=status,
        component_type="application",
    )

    if comp.sigstore_identity:
        log.info(f"  Sigstore: {comp.sigstore_identity} (copied)")

    bom.add_component(comp)
    bom.set_latest("python", minor, new_version)

    # Copy dependencies from current version
    if current_version:
        deps = bom.get_dependencies(f"python@{current_version}")
        if deps:
            bom.set_dependencies(f"python@{new_version}", deps)

    log.info(f"OK Updated Python {minor} to {new_version}")
    return True


def check_python_versions(bom: cdx.Bom, python: PythonUpstream) -> list[tuple[str, str]]:
    """Check for Python updates, return list of (minor, new_version) tuples."""
    updates = []
    for minor in sorted(bom.python_minors(), key=version_key):
        # python_minors() derives from components, so latest is always set
        current = bom.get_latest_version("python", minor)
        if not current:  # pragma: no cover
            continue

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


def check_dependencies(bom: cdx.Bom) -> list[tuple[str, str]]:
    """Check for dependency updates, return list of (dep, new_version) tuples."""
    updates = []

    # Check all non-python components
    for name in bom.component_names():
        if name == "python":
            continue

        current = bom.get_default_version(name)
        if not current:
            continue

        upstream = DEPS.get(name)
        if not upstream:
            log.warning(f"{name}: unknown upstream")
            continue

        try:
            latest = upstream.fetch_latest()
        except Exception as e:
            log.warning(f"{name}: {current} (failed to check: {e})")
            continue

        if not latest:
            log.warning(f"{name}: {current} (failed to check)")
            continue

        # Get status for OpenSSL
        status_str = ""
        if name == "openssl":
            status = openssl_upstream.get_status(latest)
            if status == "eol":
                log.warning(f"{name}: {latest} is EOL - consider upgrading")
            status_str = f" ({status})" if status != "unknown" else ""

        if latest != current:
            log.info(f"{name}: {current} -> {latest}{status_str}")
            updates.append((name, latest))
        else:
            log.info(f"{name}: {current}{status_str} (current)")

    return updates


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

    bom = cdx.load(CDX_FILE)
    python = PythonUpstream()
    has_updates = False

    # Check Python versions
    log.info("=== Python ===")
    python_updates = check_python_versions(bom, python)
    for minor, version in python_updates:
        if update_python_version(bom, minor, version, python):
            has_updates = True
    print()

    # Check dependencies
    log.info("=== Dependencies ===")
    dep_updates = check_dependencies(bom)
    for dep, version in dep_updates:
        if update_dependency(bom, dep, version):
            has_updates = True
    print()

    # Save and regenerate
    if has_updates and not DRY_RUN:
        bom._version += 1  # Increment BOM revision
        cdx.dump(bom, CDX_FILE)
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
            print("  - upstream.cdx.json")
            print("  - README.md")
    else:
        log.info("All dependencies are up to date.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
