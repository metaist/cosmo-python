#!/usr/bin/env python3
"""Generate manifest.cdx.json for a release.

This creates a CycloneDX SBOM manifest that includes:
- All Python versions from the current release
- All Python versions from previous releases (merged)
- All dependencies used to build each Python version
- Build attestation information for verification

The manifest serves as a registry of all available versions across releases.

Usage:
    uv run -m ci.manifest <release_tag> [--merge <url_or_path>]

Outputs: ${DIST_DIR}/manifest.cdx.json (default: ./dist/manifest.cdx.json)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import cdx
from .common import CDX_FILE, setup_logging, version_key

# Directories
DIST_DIR = Path(os.environ.get("DIST_DIR", "dist"))

# GitHub repo for attestation verification
DEFAULT_REPO = "metaist/cosmo-python"

log = logging.getLogger("ci.manifest")


def is_prerelease(v: str) -> bool:
    """Check if version is a pre-release (alpha, beta, rc)."""
    return bool(re.search(r"[ab]|rc", v))


def get_cosmocc_version() -> str:
    """Get cosmocc version from upstream.cdx.json or environment."""
    if "COSMOCC_VERSION" in os.environ:
        return os.environ["COSMOCC_VERSION"]
    bom = cdx.load(CDX_FILE)
    return bom.get_default_version("cosmocc") or "unknown"


def get_repo() -> str:
    """Get repo from environment or default."""
    return os.environ.get("REPO", DEFAULT_REPO)


def fetch_previous_manifest(url_or_path: str) -> cdx.Bom | None:
    """Fetch previous manifest from URL or local path."""
    if url_or_path.startswith("http"):
        log.info(f"Fetching previous manifest from {url_or_path}...")
        try:
            with urllib.request.urlopen(url_or_path, timeout=30) as resp:
                # Write to temp file and load
                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
                    tmp.write(resp.read().decode())
                    tmp_path = tmp.name
                bom = cdx.load(tmp_path)
                Path(tmp_path).unlink()
                log.info("Previous manifest fetched")
                return bom
        except (OSError, ValueError) as e:
            log.warning(f"Could not fetch previous manifest: {e}")
            return None
    else:
        path = Path(url_or_path)
        if path.exists():
            log.info(f"Using previous manifest from {path}")
            return cdx.load(path)
        else:
            log.warning(f"Previous manifest not found at {path}")
            return None


def collect_new_binaries(release_tag: str) -> dict[str, dict[str, str]]:
    """Collect all built Python binaries from dist/.

    Returns dict mapping version -> {url, sha256, filename}.
    """
    binaries: dict[str, dict[str, str]] = {}
    repo = get_repo()

    for artifact in sorted(DIST_DIR.glob("python-*-cosmo.com")):
        filename = artifact.name
        # Extract version from filename: python-3.12.8-cosmo.com
        match = re.match(r"python-(\d+\.\d+\.\d+[ab]?\d*(?:rc\d+)?)-cosmo\.com", filename)
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
        binaries[version] = {
            "url": url,
            "sha256": checksum,
            "filename": filename,
        }
        log.info(f"New: {version} ({checksum[:16]}...)")

    return binaries


def generate_manifest(
    release_tag: str,
    new_binaries: dict[str, dict[str, str]],
    prev_manifest: cdx.Bom | None = None,
) -> cdx.Bom:
    """Generate CycloneDX manifest with proper merging."""
    repo = get_repo()
    cosmocc_version = get_cosmocc_version()

    # Load build config to get dependencies
    build_bom = cdx.load(CDX_FILE)
    disabled_prefixes = build_bom.get_disabled("python")
    if disabled_prefixes:
        log.warning(f"Disabled version prefixes: {disabled_prefixes}")

    # Start with empty manifest or previous
    if prev_manifest:
        manifest = prev_manifest
    else:
        manifest = cdx.Bom()

    # Update manifest metadata
    manifest._release = release_tag

    # Add cosmocc as a component (toolchain used for builds)
    cosmocc_comp = build_bom.get_component("cosmocc", cosmocc_version)
    if cosmocc_comp:
        # Create a copy without download URL (it's a build tool, not distributed)
        manifest.add_component(
            cdx.Component(
                name="cosmocc",
                version=cosmocc_version,
                url="",  # Not distributed
                sha256="",
                license=cosmocc_comp.license,
                license_url=cosmocc_comp.license_url,
                description="Cosmopolitan C Compiler toolchain used for builds",
                component_type="application",
            )
        )

    # Collect all dependency versions needed
    dep_versions_needed: set[str] = set()  # "openssl@3.5.4" format

    # Add new Python binaries
    for version, binary_info in new_binaries.items():
        # Check if disabled
        if disabled_prefixes and any(version.startswith(p) for p in disabled_prefixes):
            log.warning(f"Skipping disabled version: {version}")
            continue

        # Get source component for license info
        source_comp = build_bom.get_component("python", version)

        # Create binary component (cosmo-python, not python)
        comp = cdx.Component(
            name="cosmo-python",
            version=version,
            url=binary_info["url"],
            sha256=binary_info["sha256"],
            license=source_comp.license if source_comp else "PSF-2.0",
            license_url=source_comp.license_url if source_comp else None,
            component_type="application",
            # Attestation info for verification
            attestation_repo=repo,
        )
        manifest.add_component(comp)

        # Track release tag per component
        manifest._component_releases[f"cosmo-python@{version}"] = release_tag

        # Update latest for this minor
        minor = ".".join(version.split(".")[:2])
        # Update latest for this minor (use "python" key for properties)
        current_latest = manifest.get_latest_version("python", minor)
        if not current_latest or version_key(version) > version_key(current_latest):
            manifest.set_latest("python", minor, version)

        # Collect dependencies from build config (includes python source + libs)
        deps = build_bom.get_dependencies(f"python@{version}")
        # Add upstream python source as dependency
        all_deps = [f"python@{version}"] + list(deps)
        for dep_ref in all_deps:
            dep_versions_needed.add(dep_ref)

        # Set dependencies in manifest
        manifest.set_dependencies(f"cosmo-python@{version}", all_deps)

    # Add all needed dependency components and their interdependencies
    for dep_ref in sorted(dep_versions_needed):
        name, version = dep_ref.split("@")
        dep_comp = build_bom.get_component(name, version)
        if dep_comp and not manifest.get_component(name, version):
            manifest.add_component(dep_comp)
        # Copy runtime library interdependencies (e.g., readline -> ncurses)
        # Skip python - it's just source, cosmo-python has the real deps
        # Filter out build-time deps (cosmocc) - only keep runtime deps
        if name != "python":
            lib_deps = build_bom.get_dependencies(dep_ref)
            runtime_deps = [d for d in lib_deps if not d.startswith("cosmocc@")]
            if runtime_deps:
                manifest.set_dependencies(dep_ref, runtime_deps)

    # Compute default (highest non-prerelease stable version of cosmo-python)
    all_versions = sorted(c.version for c in manifest.get_components("cosmo-python"))
    stable_versions = [v for v in all_versions if not is_prerelease(v)]
    if stable_versions:
        default_version = sorted(stable_versions, key=version_key)[-1]
    elif all_versions:
        default_version = sorted(all_versions, key=version_key)[-1]
    else:
        default_version = ""

    if default_version:
        manifest.set_default("python", default_version)

    return manifest


def print_summary(manifest: cdx.Bom) -> None:
    """Print manifest summary."""
    print()
    log.info("Manifest summary:")
    print(f"  Release: {manifest._release}")
    cosmo_versions = sorted(c.version for c in manifest.get_components("cosmo-python"))
    print(f"  Python versions: {len(cosmo_versions)}")

    default_version = manifest.get_default_version("python")
    print(f"  Default: {default_version}")

    print()
    print("  Available versions:")
    for version in cosmo_versions:
        release = manifest._component_releases.get(f"cosmo-python@{version}", "unknown")
        print(f"    {version} -> {release}")

    # Show dependencies (everything except cosmo-python)
    dep_names = [n for n in manifest.component_names() if n != "cosmo-python"]
    if dep_names:  # pragma: no branch - manifest always includes python and deps
        print()
        print("  Dependencies included:")
        for name in sorted(dep_names):
            comps = manifest.get_components(name)
            versions = [c.version for c in comps]
            print(f"    {name}: {', '.join(versions)}")


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
        existing = DIST_DIR / "manifest.cdx.json"
        if existing.exists():
            log.info("Using existing manifest as base")
            prev_manifest = cdx.load(existing)

    # Collect new binaries
    new_binaries = collect_new_binaries(release_tag)
    if not new_binaries:
        log.warning("No binaries found in dist/")

    # Generate manifest
    manifest = generate_manifest(release_tag, new_binaries, prev_manifest)

    # Write manifest
    manifest_path = DIST_DIR / "manifest.cdx.json"
    cdx.dump(manifest, manifest_path)
    log.info(f"OK Manifest written to {manifest_path}")

    # Print summary
    print_summary(manifest)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
