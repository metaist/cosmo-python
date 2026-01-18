"""OpenSSL upstream with EOL tracking."""

from __future__ import annotations

import re
import urllib.request
from datetime import date

_RELEASE_STRATEGY_URL = "https://www.openssl.org/policies/releasestrat.html"
_EOL_CACHE: dict[str, tuple[str, str]] = {}  # minor -> (eol_date, status)


def _fetch_eol_data() -> dict[str, tuple[str, str]]:
    """Fetch OpenSSL EOL data from release strategy page.

    Returns dict mapping minor version (e.g., "3.5") to (eol_date, status).
    Status is "lts", "supported", or "eol".
    """
    global _EOL_CACHE
    if _EOL_CACHE:
        return _EOL_CACHE

    try:
        with urllib.request.urlopen(_RELEASE_STRATEGY_URL, timeout=30) as resp:
            html = resp.read().decode()

        # Pattern: Version 3.5 will be supported until 2030-04-08 (LTS)
        pattern = r"Version (\d+\.\d+) will be supported until (\d{4}-\d{2}-\d{2})(?:\s*\(LTS\))?"
        today = date.today().isoformat()

        for match in re.finditer(pattern, html, re.IGNORECASE):
            minor = match.group(1)
            eol_date = match.group(2)
            is_lts = "(LTS)" in match.group(0)

            if eol_date < today:
                status = "eol"
            elif is_lts:
                status = "lts"
            else:
                status = "supported"

            _EOL_CACHE[minor] = (eol_date, status)

    except OSError:  # pragma: no cover - network errors
        pass

    return _EOL_CACHE


def get_eol(version: str) -> str:
    """Get EOL date for an OpenSSL version (YYYY-MM format).

    Args:
        version: Full version like "3.5.4" or minor like "3.5"

    Returns:
        EOL date in YYYY-MM format, or empty string if unknown.
    """
    # Extract minor version (3.5.4 -> 3.5)
    parts = version.split(".")
    if len(parts) >= 2:
        minor = f"{parts[0]}.{parts[1]}"
    else:
        minor = version

    data = _fetch_eol_data()
    if minor in data:
        eol_date = data[minor][0]
        return eol_date[:7]  # YYYY-MM
    return ""


def get_status(version: str) -> str:
    """Get support status for an OpenSSL version.

    Args:
        version: Full version like "3.5.4" or minor like "3.5"

    Returns:
        One of: "lts", "supported", "eol", or "unknown"
    """
    # Extract minor version (3.5.4 -> 3.5)
    parts = version.split(".")
    if len(parts) >= 2:
        minor = f"{parts[0]}.{parts[1]}"
    else:
        minor = version

    data = _fetch_eol_data()
    if minor in data:
        return data[minor][1]
    return "unknown"
