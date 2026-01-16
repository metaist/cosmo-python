"""Tests for ci/common.py."""

import json
import logging
from pathlib import Path

from ci.common import version_key, load_versions, save_versions, setup_logging, VERSIONS_FILE


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


def test_load_versions(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """load_versions reads versions.json."""
    test_file = tmp_path / "versions.json"
    test_file.write_text(json.dumps({
        "python": {"versions": {"3.13.1": {}}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.common.VERSIONS_FILE", test_file)

    data = load_versions()
    assert "python" in data
    assert "cosmocc" in data
    assert "versions" in data["python"]


def test_save_versions(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """save_versions writes JSON."""
    test_file = tmp_path / "versions.json"
    monkeypatch.setattr("ci.common.VERSIONS_FILE", test_file)

    data = {"test": {"default": "1.0", "versions": {}}}
    save_versions(data)

    result = json.loads(test_file.read_text())
    assert result == data


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
