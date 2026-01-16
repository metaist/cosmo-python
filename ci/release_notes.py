#!/usr/bin/env python3
"""Generate release notes components for GitHub Actions.

Usage:
    uv run -m ci.release_notes <dist_dir>

Outputs (for GITHUB_OUTPUT):
    version_table=| Python Version | Download |...
    default_version=3.13.1
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from .common import load_versions, setup_logging, version_key

log = logging.getLogger("ci.release_notes")


def main() -> int:
    setup_logging()

    dist_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")

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

    # Get default version
    data = load_versions()
    default_minor = data["python"]["default"]
    default_version = data["python"]["latest"][default_minor]

    # Output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            # Multi-line output using heredoc syntax
            f.write(f"version_table<<EOF\n{version_table}\nEOF\n")
            f.write(f"default_version={default_version}\n")

    # Also print for debugging
    log.info("Version table:")
    print(version_table)
    print()
    log.info(f"Default version: {default_version}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
