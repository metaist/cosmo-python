#!/usr/bin/env python3
"""Generate build matrix for GitHub Actions.

Usage:
    uv run -m ci.build_matrix <input>

Where <input> is:
    - "all": all versions from versions.cdx.json
    - "3.12.8": single version
    - "3.12.8, 3.13.1": comma-separated versions

Outputs (for GITHUB_OUTPUT):
    matrix={"version":["3.12.8","3.13.1",...]}
    cosmocc_version=X.Y.Z
"""

from __future__ import annotations

import json
import logging
import os
import sys

from . import cdx
from .common import CDX_FILE, setup_logging

log = logging.getLogger("ci.build_matrix")


def main() -> int:
    setup_logging()

    if len(sys.argv) < 2:
        log.error("Usage: uv run -m ci.build_matrix <input>")
        return 1

    input_arg = sys.argv[1]
    bom = cdx.load(CDX_FILE)

    # Determine versions
    if input_arg == "all":
        versions = bom.python_versions()
    else:
        # Split by comma or space
        versions = [v.strip() for v in input_arg.replace(",", " ").split() if v.strip()]

    # Build matrix JSON
    matrix = {"version": versions}
    cosmocc = bom.get_default_version("cosmocc")

    # Output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"matrix={json.dumps(matrix)}\n")
            f.write(f"cosmocc_version={cosmocc}\n")

    # Also print for debugging
    log.info(f"Building versions: {versions}")
    log.info(f"Cosmocc version: {cosmocc}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
