"""
Stub _scproxy module for Cosmopolitan Python.

The real _scproxy uses macOS SystemConfiguration framework to get proxy
settings. Since Cosmopolitan doesn't support macOS frameworks, we provide
a stub that returns empty/no proxy settings.

This allows urllib.request to import on macOS without errors.
"""

from typing import Any


def _get_proxy_settings() -> dict[str, Any]:
    """Return empty proxy settings."""
    return {
        "exclude_simple": False,
        "exceptions": [],
    }


def _get_proxies() -> dict[str, str]:
    """Return empty proxy dict."""
    return {}
