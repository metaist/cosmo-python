"""Documentation helpers for cog integration."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DOCS_URL = "https://docs.metaist.com/cosmo-python"


def include_doc(
    path: str,
    *,
    start_after: str | None = None,
    end_before: str | None = None,
    heading_level: int = 0,
) -> str:
    """Include content from a docs/ file for use in README.

    Args:
        path: Path relative to repo root (e.g., "docs/index.md")
        start_after: Include content after this marker line (exclusive)
        end_before: Include content before this marker line (exclusive)
        heading_level: Adjust heading levels (positive = deeper, negative = shallower)

    Returns:
        The processed markdown content.
    """
    file_path = REPO_ROOT / path
    content = file_path.read_text()

    # Extract section between markers
    if start_after:
        idx = content.find(start_after)
        if idx != -1:
            content = content[idx + len(start_after) :]

    if end_before:
        idx = content.find(end_before)
        if idx != -1:
            content = content[:idx]

    # Adjust heading levels
    if heading_level != 0:
        lines = content.split("\n")
        adjusted = []
        for line in lines:
            if line.startswith("#"):
                hashes = len(line) - len(line.lstrip("#"))
                new_level = max(1, hashes + heading_level)
                line = "#" * new_level + line[hashes:]
            adjusted.append(line)
        content = "\n".join(adjusted)

    return content.strip()
