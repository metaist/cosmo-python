#!/usr/bin/env python3
"""Generate release notes for GitHub releases.

Usage:
    uv run -m ci.release <dist_dir> [--release-tag TAG] [--repo REPO] [--output FILE]

Examples:
    # Preview release notes locally
    uv run -m ci.release dist --release-tag 20260119-120000

    # Output to file
    uv run -m ci.release dist --release-tag 20260119-120000 --output dist/release_notes.md

    # For GitHub Actions (writes to GITHUB_OUTPUT)
    uv run -m ci.release dist --release-tag ${{ github.ref_name }}
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from . import cdx
from .common import CDX_FILE, setup_logging, version_key

log = logging.getLogger("ci.release")

CHANGELOG_PATH = Path("CHANGELOG.md")
DEFAULT_REPO = "metaist/cosmo-python"


def extract_unreleased_with_links(changelog_path: Path = CHANGELOG_PATH) -> str:
    """Extract Unreleased section content including issue link definitions.

    Returns the content between ## [Unreleased] header and the --- separator,
    excluding the header line and description paragraph, but including link defs.
    """
    if not changelog_path.exists():
        return ""

    content = changelog_path.read_text()

    # Find Unreleased section - everything between header and ---
    match = re.search(
        r"## \[Unreleased\]\s*\n"
        r"\[unreleased\]:.*?\n\n"  # link def
        r".*?\n\n"  # description paragraph
        r"(.*?)"  # content we want
        r"\n---",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""

    return match.group(1).strip()


def generate_version_table(
    dist_dir: Path,
    release_tag: str | None = None,
    repo: str = DEFAULT_REPO,
) -> str:
    """Generate Python versions table with download links.

    Args:
        dist_dir: Directory containing python-*-cosmo.com binaries
        release_tag: GitHub release tag for download URLs (None for filenames only)
        repo: GitHub repo in owner/repo format
    """
    binaries = sorted(dist_dir.glob("python-*-cosmo.com"))
    if not binaries:
        return ""

    lines = [
        "| Python | Download |",
        "|--------|----------|",
    ]

    for binary in sorted(binaries, key=lambda p: version_key(p.stem.split("-")[1])):
        filename = binary.name
        match = re.match(r"python-(\d+\.\d+\.\d+)-cosmo\.com", filename)
        if match:
            version = match.group(1)
            minor = ".".join(version.split(".")[:2])
            if release_tag:
                url = f"https://github.com/{repo}/releases/download/{release_tag}/{filename}"
                lines.append(f"| {minor} | [{filename}]({url}) |")
            else:
                lines.append(f"| {minor} | `{filename}` |")

    return "\n".join(lines)


def generate_supply_chain_table(bom: cdx.Bom) -> str:
    """Generate supply chain (dependencies) table."""
    return bom.upstream_table()


def generate_release_notes(
    dist_dir: Path,
    release_tag: str | None = None,
    repo: str = DEFAULT_REPO,
    changelog_path: Path = CHANGELOG_PATH,
) -> str:
    """Generate complete release notes markdown.

    Args:
        dist_dir: Directory containing python-*-cosmo.com binaries
        release_tag: GitHub release tag (None for preview mode)
        repo: GitHub repo in owner/repo format
        changelog_path: Path to CHANGELOG.md

    Returns:
        Complete release notes as markdown string
    """
    bom = cdx.load(CDX_FILE)
    default_python = bom.get_default_component("python")
    default_version = default_python.version if default_python else "unknown"

    sections = []

    # Header with default version
    sections.append(f"**Default Python version: {default_version}**\n")

    # Python Versions table
    version_table = generate_version_table(dist_dir, release_tag, repo)
    if version_table:
        sections.append("## Python Versions\n")
        sections.append(version_table + "\n")

    # Supply Chain (dependencies)
    sections.append("## Supply Chain\n")
    sections.append(generate_supply_chain_table(bom) + "\n")

    # Changelog (the long part, at the end)
    changelog = extract_unreleased_with_links(changelog_path)
    if changelog:
        sections.append("## Changelog\n")
        sections.append(changelog)

    return "\n".join(sections)


def main() -> int:
    setup_logging()

    dist_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    release_tag: str | None = None
    repo = DEFAULT_REPO
    output_path: Path | None = None

    # Parse args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--release-tag" and i + 1 < len(args):
            release_tag = args[i + 1]
            i += 2
        elif args[i] == "--repo" and i + 1 < len(args):
            repo = args[i + 1]
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = Path(args[i + 1])
            i += 2
        else:
            i += 1

    if not dist_dir.exists():
        log.error(f"{dist_dir} does not exist")
        return 1

    # Check for binaries
    binaries = sorted(dist_dir.glob("python-*-cosmo.com"))
    if not binaries:
        log.error(f"No binaries found in {dist_dir}")
        return 1

    # Generate release notes
    release_notes = generate_release_notes(dist_dir, release_tag, repo)

    # Get components for GitHub Actions output
    bom = cdx.load(CDX_FILE)
    default_python = bom.get_default_component("python")
    default_version = default_python.version if default_python else "unknown"
    version_table = generate_version_table(dist_dir, release_tag, repo)
    deps_table = generate_supply_chain_table(bom)
    changelog = extract_unreleased_with_links()

    # Output to file if requested
    if output_path:
        output_path.write_text(release_notes)
        log.info(f"Wrote release notes to {output_path}")

    # Output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version_table<<EOF\n{version_table}\nEOF\n")
            f.write(f"default_version={default_version}\n")
            f.write(f"changelog<<EOF\n{changelog}\nEOF\n")
            f.write(f"deps_table<<EOF\n{deps_table}\nEOF\n")
            f.write(f"release_notes<<EOF\n{release_notes}\nEOF\n")

    # Print to stdout (for preview or piping)
    print(release_notes)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
