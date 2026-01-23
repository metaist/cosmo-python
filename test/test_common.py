"""Tests for ci/common.py."""

import logging

from ci.common import version_key, setup_logging, CDX_FILE, github_actions_table, GITHUB_ACTIONS


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
    """CDX_FILE points to upstream.cdx.json."""
    assert CDX_FILE.name == "upstream.cdx.json"
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


def test_github_actions_table() -> None:
    """github_actions_table generates markdown table from workflow files."""
    table = github_actions_table()

    # Check table structure
    lines = table.split("\n")
    assert lines[0] == "| Action | Version | Purpose |"
    assert lines[1] == "|--------|---------|---------|"

    # Check that known actions are present
    assert "actions/checkout" in table
    assert "astral-sh/setup-uv" in table

    # Check that versions are extracted
    assert "| v" in table  # versions like "v6", "v7"

    # Check that all actions in GITHUB_ACTIONS dict have purposes filled in
    for repo in GITHUB_ACTIONS:
        if repo in table:
            # Should have the purpose, not "—"
            assert GITHUB_ACTIONS[repo] in table

    # Local workflow refs (like ./.github/workflows/build.yaml) are naturally
    # excluded since they don't match the @sha # vN pattern
    assert "./.github/workflows" not in table
