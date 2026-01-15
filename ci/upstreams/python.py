"""Python upstream with endoflife.date integration."""

from __future__ import annotations

from datetime import date
from typing import Any

from ..common import version_key
from .http import fetch_json

_ENDOFLIFE_CACHE: list[dict[str, Any]] = []


def _fetch_endoflife_data() -> list[dict[str, Any]]:
    """Fetch Python lifecycle data from endoflife.date API."""
    global _ENDOFLIFE_CACHE
    if not _ENDOFLIFE_CACHE:
        _ENDOFLIFE_CACHE = fetch_json("https://endoflife.date/api/python.json")
    return _ENDOFLIFE_CACHE


class PythonUpstream:
    """Python upstream with status and EOL tracking."""

    def fetch_latest(self, minor: str) -> str | None:
        """Fetch latest Python version for a minor release."""
        try:
            data = fetch_json(
                f"https://www.python.org/api/v2/downloads/release/?version={minor}"
            )
            releases = [r for r in data["results"] if r["is_published"]]
            if not releases:
                return None
            versions = [str(r["name"]).replace("Python ", "") for r in releases]
            return str(sorted(versions, key=version_key)[-1])
        except Exception:
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
        return ""
