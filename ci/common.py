"""Common utilities for CI scripts."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Paths - relative to repo root (this file is at ci/common.py)
REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.json"

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    """Custom formatter with colors and short module names."""

    def format(self, record: logging.LogRecord) -> str:
        # Extract short name from logger name (ci.check_updates -> check-updates)
        name = record.name.replace("ci.", "").replace("_", "-")
        msg = record.getMessage()

        if record.levelno >= logging.ERROR:
            return f"[{name}] {RED}ERROR{RESET} {msg}"
        elif record.levelno >= logging.WARNING:
            return f"[{name}] {YELLOW}WARN{RESET} {msg}"
        elif msg.startswith("OK "):
            return f"[{name}] {GREEN}OK{RESET} {msg[3:]}"
        else:
            return f"[{name}] {msg}"


def setup_logging() -> None:
    """Configure logging with colored output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)


def version_key(v: str) -> list[tuple[int, int | str]]:
    """Sort versions by semver, handling pre-release tags.

    >>> sorted(["3.10.2", "3.10.1", "3.9.0"], key=version_key)
    ['3.9.0', '3.10.1', '3.10.2']
    >>> sorted(["3.14.0a2", "3.14.0a1", "3.14.0b1"], key=version_key)
    ['3.14.0a1', '3.14.0a2', '3.14.0b1']
    """
    parts = v.replace("a", ".a.").replace("b", ".b.").replace("rc", ".rc.").split(".")
    result: list[tuple[int, int | str]] = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p)))
        else:
            result.append((1, p))
    return result


def load_versions() -> dict[str, Any]:
    """Load versions.json."""
    return dict(json.loads(VERSIONS_FILE.read_text()))


def save_versions(data: dict[str, Any]) -> None:
    """Save versions.json (without normalization)."""
    VERSIONS_FILE.write_text(json.dumps(data, indent=2) + "\n")
