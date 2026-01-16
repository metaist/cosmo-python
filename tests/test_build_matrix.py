"""Tests for ci/build_matrix.py."""

import json
from unittest.mock import patch, MagicMock


def test_main_all_versions(tmp_path: "Path", monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with 'all' gets versions from versions.json."""
    from pathlib import Path

    # Create test versions.json
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"versions": {"3.12.1": {}, "3.13.0": {}}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.common.VERSIONS_FILE", versions_file)

    # Mock GITHUB_OUTPUT
    output_file = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr("sys.argv", ["build_matrix", "all"])

    from ci.build_matrix import main
    result = main()

    assert result == 0
    output = output_file.read_text()
    assert "matrix=" in output
    assert "3.12.1" in output
    assert "3.13.0" in output
    assert "cosmocc_version=4.0.0" in output


def test_main_specific_versions(tmp_path: "Path", monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with specific versions."""
    from pathlib import Path

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"versions": {}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.common.VERSIONS_FILE", versions_file)

    output_file = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr("sys.argv", ["build_matrix", "3.12.8, 3.13.1"])

    from ci.build_matrix import main
    result = main()

    assert result == 0
    output = output_file.read_text()
    assert "3.12.8" in output
    assert "3.13.1" in output


def test_main_no_args(monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]") -> None:
    """main() with no args returns error."""
    monkeypatch.setattr("sys.argv", ["build_matrix"])

    from ci.build_matrix import main
    result = main()

    assert result == 1
