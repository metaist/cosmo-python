"""Common utilities for CI scripts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Paths - relative to repo root (this file is at ci/common.py)
REPO_ROOT = Path(__file__).parent.parent
CDX_FILE = REPO_ROOT / "upstream.cdx.json"

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


# GitHub Actions metadata for README table
GITHUB_ACTIONS: dict[str, str] = {
    "actions/attest-build-provenance": "Generate SLSA build provenance attestations",
    "actions/cache": "Cache dependencies between workflow runs",
    "actions/checkout": "Clone repository",
    "actions/download-artifact": "Download workflow artifacts",
    "actions/upload-artifact": "Upload workflow artifacts",
    "astral-sh/setup-uv": "Install uv package manager",
}


def github_actions_table() -> str:
    """Generate a markdown table of GitHub Actions used in workflows.

    Parses all workflow files in .github/workflows/ to extract action references,
    then generates a table with Action (linked), Version, and Purpose columns.
    """
    import re

    workflows_dir = REPO_ROOT / ".github" / "workflows"
    uses_pattern = re.compile(r"uses:\s*([^@\s]+)@([a-f0-9]+)\s*#\s*v(\d+)")

    # Collect unique action@sha pairs
    # Note: regex requires @sha # vN format, so local refs like ./.github/workflows/x.yaml
    # are naturally excluded (they don't have @sha)
    actions: dict[str, tuple[str, str]] = {}  # repo -> (sha, version)
    for workflow in sorted(workflows_dir.glob("*.yaml")):
        content = workflow.read_text()
        for match in uses_pattern.finditer(content):
            repo, sha, version = match.groups()
            actions[repo] = (sha, f"v{version}")

    # Generate table
    lines = [
        "| Action | Version | Purpose |",
        "|--------|---------|---------|",
    ]

    for repo in sorted(actions.keys()):
        sha, version = actions[repo]
        purpose = GITHUB_ACTIONS.get(repo, "—")
        url = f"https://github.com/{repo}"
        lines.append(f"| [{repo}]({url}) | {version} | {purpose} |")

    return "\n".join(lines)
