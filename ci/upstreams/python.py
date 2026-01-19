"""Python upstream with endoflife.date integration."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..common import version_key
from .http import fetch_json

_ENDOFLIFE_CACHE: list[dict[str, Any]] = []
_RELEASES_CACHE: list[dict[str, Any]] = []


def _fetch_endoflife_data() -> list[dict[str, Any]]:  # pragma: no cover
    """Fetch Python lifecycle data from endoflife.date API."""
    global _ENDOFLIFE_CACHE
    if not _ENDOFLIFE_CACHE:
        _ENDOFLIFE_CACHE = fetch_json("https://endoflife.date/api/python.json")
    return _ENDOFLIFE_CACHE


def _fetch_releases() -> list[dict[str, Any]]:  # pragma: no cover
    """Fetch all Python releases from python.org API (cached)."""
    global _RELEASES_CACHE
    if not _RELEASES_CACHE:
        _RELEASES_CACHE = fetch_json("https://www.python.org/api/v2/downloads/release/")
    return _RELEASES_CACHE


class PythonUpstream:
    """Python upstream with status and EOL tracking."""

    def fetch_latest(self, minor: str) -> str | None:
        """Fetch latest Python version for a minor release."""
        try:
            data = _fetch_releases()
            # Filter by name pattern: "Python 3.14.X" (X = digits only, no alpha/beta/rc)
            pattern = re.compile(rf"^Python {re.escape(minor)}\.\d+$")
            releases = [
                r
                for r in data
                if r["is_published"] and not r["pre_release"] and pattern.match(r["name"])
            ]
            if not releases:
                return None
            versions = [str(r["name"]).replace("Python ", "") for r in releases]
            return str(sorted(versions, key=version_key)[-1])
        except (OSError, ValueError, KeyError):  # pragma: no cover - network/parse errors
            return None

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        return f"https://www.python.org/ftp/python/{version}/Python-{version}.tgz"

    def get_status(self, minor: str) -> str:
        """Get Python status: prerelease, bugfix, security, or eol."""
        data = _fetch_endoflife_data()
        for entry in data:
            if entry["cycle"] == minor:
                today = date.today().isoformat()
                release_date = entry.get("releaseDate", "")
                support_date = entry.get("support", "")
                eol_date = entry.get("eol", "")

                if release_date > today:
                    return "prerelease"
                elif support_date and support_date > today:
                    return "bugfix"
                elif eol_date and eol_date > today:
                    return "security"
                else:
                    return "eol"
        return "unknown"

    def get_eol(self, minor: str) -> str:
        """Get EOL date for a Python minor version (YYYY-MM format)."""
        data = _fetch_endoflife_data()
        for entry in data:
            if entry["cycle"] == minor:
                eol = entry.get("eol", "")
                return str(eol)[:7] if eol else ""
        return ""  # pragma: no cover - defensive: minor not in endoflife data
