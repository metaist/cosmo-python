#!/usr/bin/env python3
"""Generate release notes components for GitHub Actions.

Usage:
    uv run -m ci.release_notes <dist_dir> [--release-tag TAG]

Outputs (for GITHUB_OUTPUT):
    version_table=| Python Version | Download |...
    default_version=3.13.1
    changelog=### Changed\n- item...
    deps_table=| Dependency | Version | License |...
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from . import cdx
from .common import CDX_FILE, setup_logging, version_key

log = logging.getLogger("ci.release_notes")

CHANGELOG_PATH = Path("CHANGELOG.md")


def extract_unreleased(changelog_path: Path = CHANGELOG_PATH) -> str:
    """Extract content from Unreleased section of changelog.

    Returns the content between ## [Unreleased] and the next ## heading,
    excluding the link definition and description paragraph.
    """
    if not changelog_path.exists():
        return ""

    content = changelog_path.read_text()
    # Find Unreleased section
    match = re.search(
        r"## \[Unreleased\].*?\n\[unreleased\]:.*?\n\n.*?\n\n(.*?)(?=\n---|\n## \[)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""

    section = match.group(1).strip()
    return section if section else ""


def generate_deps_table(bom: cdx.Bom) -> str:
    """Generate dependency versions table from upstream.cdx.json."""
    return bom.upstream_table()


def move_unreleased_to_release(release_tag: str, changelog_path: Path = CHANGELOG_PATH) -> None:
    """Move Unreleased content to a dated release section.

    Modifies the changelog in place:
    - Adds new section header: ## [TAG] - YYYY-MM-DD
    - Clears Unreleased section (keeps header and description)
    - Adds link definition for the new release
    """
    if not changelog_path.exists():
        return

    content = changelog_path.read_text()

    # Extract unreleased content
    unreleased_content = extract_unreleased(changelog_path)
    if not unreleased_content:
        return

    # Get today's date
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Find where to insert new release (after Unreleased section ends)
    # Pattern: find the --- after Unreleased
    insert_match = re.search(
        r"(## \[Unreleased\].*?\n\[unreleased\]:.*?\n\nThese are changes.*?\n)\n(.*?)(\n---)",
        content,
        re.DOTALL | re.IGNORECASE,
    )

    if not insert_match:  # pragma: no cover - unreleased_content check catches this
        return

    # Build new release section
    new_section = f"\n## [{release_tag}] - {today}\n\n{unreleased_content}\n"

    # Clear the unreleased content (keep the section structure)
    before_unreleased = content[: insert_match.start()]
    unreleased_header = insert_match.group(1)

    # Add link definition for new release
    # Find where link definitions start (after ---)
    links_match = re.search(r"\n---\n\n(\[.+?\]:.*)", content, re.DOTALL)
    if links_match:
        # Insert release link before issue links
        release_link = (
            f"[{release_tag}]: https://github.com/metaist/cosmo-python/releases/tag/{release_tag}\n"
        )

        # Find the right place to insert (after other release links, before issue links)
        links_section = links_match.group(1)
        if re.match(r"\[\d{8}-\d{6}\]:", links_section):
            # Already has release links, add after them
            new_content = (
                before_unreleased
                + unreleased_header
                + new_section
                + "\n---\n\n"
                + release_link
                + links_section
            )
        else:
            # No release links yet, add before issue links
            new_content = (
                before_unreleased
                + unreleased_header
                + new_section
                + "\n---\n\n"
                + release_link
                + "\n"
                + links_section
            )

        changelog_path.write_text(new_content)


def main() -> int:
    setup_logging()

    dist_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    release_tag = ""
    update_changelog = False

    # Parse args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--release-tag" and i + 1 < len(args):
            release_tag = args[i + 1]
            i += 2
        elif args[i] == "--update-changelog":
            update_changelog = True
            i += 1
        else:
            i += 1

    if not dist_dir.exists():
        log.error(f"{dist_dir} does not exist")
        return 1

    # Find all binaries
    binaries = sorted(dist_dir.glob("python-*-cosmo.com"))
    if not binaries:
        log.error(f"No binaries found in {dist_dir}")
        return 1

    # Build version table
    lines = [
        "| Python Version | Download |",
        "|----------------|----------|",
    ]
    for binary in sorted(binaries, key=lambda p: version_key(p.stem.split("-")[1])):
        filename = binary.name
        match = re.match(r"python-(\d+\.\d+\.\d+)-cosmo\.com", filename)
        if match:
            version = match.group(1)
            minor = ".".join(version.split(".")[:2])
            lines.append(f"| {minor}.x | `{filename}` |")

    version_table = "\n".join(lines)

    # Get default version and deps table
    bom = cdx.load(CDX_FILE)
    default_python = bom.get_default_component("python")
    default_version = default_python.version if default_python else "unknown"
    deps_table = generate_deps_table(bom)

    # Extract changelog content
    changelog = extract_unreleased(CHANGELOG_PATH)

    # Update changelog if requested
    if update_changelog and release_tag:
        move_unreleased_to_release(release_tag, CHANGELOG_PATH)
        log.info(f"Updated CHANGELOG.md for release {release_tag}")

    # Output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            # Multi-line output using heredoc syntax
            f.write(f"version_table<<EOF\n{version_table}\nEOF\n")
            f.write(f"default_version={default_version}\n")
            f.write(f"changelog<<EOF\n{changelog}\nEOF\n")
            f.write(f"deps_table<<EOF\n{deps_table}\nEOF\n")

    # Also print for debugging
    log.info("Version table:")
    print(version_table)
    print()
    log.info(f"Default version: {default_version}")
    print()
    log.info("Changelog:")
    print(changelog if changelog else "(empty)")
    print()
    log.info("Dependencies:")
    print(deps_table)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
