"""Tests for ci/common.py."""

import logging

from ci.common import version_key, setup_logging, CDX_FILE


def test_version_key_two_digit_minor() -> None:
    """Two-digit minor versions sort numerically, not lexically."""
    versions = ["3.9.0", "3.10.0", "3.11.0"]
    result = sorted(versions, key=version_key)
    assert result == ["3.9.0", "3.10.0", "3.11.0"]


def test_version_key_patch_double_digits() -> None:
    """Double-digit patch versions sort correctly."""
    versions = ["3.12.1", "3.12.10", "3.12.2"]
    result = sorted(versions, key=version_key)
    assert result == ["3.12.1", "3.12.2", "3.12.10"]


def test_cdx_file_exists() -> None:
    """CDX_FILE points to versions.cdx.json."""
    assert CDX_FILE.name == "versions.cdx.json"
    assert CDX_FILE.exists()


def test_setup_logging(capfd: "pytest.CaptureFixture[str]") -> None:
    """setup_logging configures colored output."""
    setup_logging()
    log = logging.getLogger("ci.test_module")
    log.info("test message")
    log.info("OK success")
    log.warning("warn message")

    out, _ = capfd.readouterr()
    assert "[test-module]" in out
    assert "test message" in out
    assert "OK" in out  # green color code will be present
    assert "WARN" in out
