"""
Stub _scproxy module for Cosmopolitan Python.

The real _scproxy uses macOS SystemConfiguration framework to get proxy
settings. Since Cosmopolitan doesn't support macOS frameworks, we provide
a stub that returns empty/no proxy settings.

This allows urllib.request to import on macOS without errors.
"""

def _get_proxy_settings():
    """Return empty proxy settings."""
    return {
        'exclude_simple': False,
        'exceptions': [],
    }

def _get_proxies():
    """Return empty proxy dict."""
    return {}
