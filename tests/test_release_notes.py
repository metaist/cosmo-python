"""Tests for ci/release_notes.py."""

import json
from pathlib import Path


def test_main_generates_table(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() generates version table from binaries."""
    # Create fake dist dir with binaries
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Create versions.json
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {
            "default": "3.13",
            "latest": {"3.12": "3.12.8", "3.13": "3.13.1"},
        }
    }))
    monkeypatch.setattr("ci.common.VERSIONS_FILE", versions_file)

    # Mock GITHUB_OUTPUT
    output_file = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr("sys.argv", ["release_notes", str(dist)])

    from ci.release_notes import main
    result = main()

    assert result == 0
    output = output_file.read_text()
    assert "version_table<<EOF" in output
    assert "3.12.x" in output
    assert "3.13.x" in output
    assert "default_version=3.13.1" in output


def test_main_no_binaries(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() returns error if no binaries found."""
    dist = tmp_path / "dist"
    dist.mkdir()

    monkeypatch.setattr("sys.argv", ["release_notes", str(dist)])

    from ci.release_notes import main
    result = main()

    assert result == 1


def test_main_no_dist(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() returns error if dist doesn't exist."""
    monkeypatch.setattr("sys.argv", ["release_notes", str(tmp_path / "nonexistent")])

    from ci.release_notes import main
    result = main()

    assert result == 1
