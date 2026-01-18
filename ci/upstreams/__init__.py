"""Upstream dependency fetchers."""

from __future__ import annotations

from typing import Protocol

from .github import GITHUB_DEPS, GitHubDep
from .gnu import GNU_DEPS, GnuDep
from .misc import MISC_DEPS
from .python import PythonUpstream


class Upstream(Protocol):
    """Protocol for upstream dependencies."""

    def fetch_latest(self) -> str | None: ...  # pragma: no cover
    def build_url(self, version: str) -> str: ...  # pragma: no cover


# Registry of all non-Python dependencies
DEPS: dict[str, Upstream] = {
    **GITHUB_DEPS,
    **GNU_DEPS,
    **MISC_DEPS,
}

__all__ = [
    "DEPS",
    "Upstream",
    "PythonUpstream",
    "GitHubDep",
    "GnuDep",
]
