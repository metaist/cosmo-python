"""HTTP utilities for upstream fetching."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import urllib.request
from typing import Any

log = logging.getLogger("ci.upstreams.http")


def fetch_json(url: str) -> Any:
    """Fetch JSON from URL."""
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_sha256(url: str) -> str:
    """Download URL and compute SHA256."""
    log.info(f"  Fetching SHA256 from {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    sha = hashlib.sha256(data).hexdigest()
    log.info(f"  SHA256: {sha}")
    return sha


def gh_api(endpoint: str) -> Any:
    """Call GitHub API via gh CLI."""
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
