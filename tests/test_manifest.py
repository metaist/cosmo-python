"""Tests for ci/manifest.py."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from ci.manifest import (
    is_prerelease,
    get_cosmocc_version,
    get_repo,
    fetch_previous_manifest,
    collect_new_versions,
    generate_manifest,
)


def test_is_prerelease() -> None:
    """is_prerelease detects alpha/beta/rc."""
    assert is_prerelease("3.14.0a1") is True
    assert is_prerelease("3.14.0b1") is True
    assert is_prerelease("3.14.0rc1") is True
    assert is_prerelease("3.14.0") is False
    assert is_prerelease("3.13.1") is False


def test_get_cosmocc_version_from_env(monkeypatch: "pytest.MonkeyPatch") -> None:
    """get_cosmocc_version uses env var if set."""
    monkeypatch.setenv("COSMOCC_VERSION", "9.9.9")
    assert get_cosmocc_version() == "9.9.9"


def test_get_cosmocc_version_from_file(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """get_cosmocc_version reads from versions.json."""
    monkeypatch.delenv("COSMOCC_VERSION", raising=False)
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({"cosmocc": {"default": "4.0.2"}}))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    assert get_cosmocc_version() == "4.0.2"


def test_get_repo_default() -> None:
    """get_repo returns default."""
    import os
    os.environ.pop("REPO", None)
    assert get_repo() == "metaist/cosmo-python"


def test_get_repo_from_env(monkeypatch: "pytest.MonkeyPatch") -> None:
    """get_repo uses env var."""
    monkeypatch.setenv("REPO", "other/repo")
    assert get_repo() == "other/repo"


@patch("urllib.request.urlopen")
def test_fetch_previous_manifest_url(mock_urlopen: MagicMock) -> None:
    """fetch_previous_manifest fetches from URL."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"versions": {}}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = fetch_previous_manifest("https://example.com/manifest.json")
    assert result == {"versions": {}}


@patch("urllib.request.urlopen")
def test_fetch_previous_manifest_url_failure(mock_urlopen: MagicMock) -> None:
    """fetch_previous_manifest returns None on error."""
    mock_urlopen.side_effect = Exception("Network error")
    result = fetch_previous_manifest("https://example.com/manifest.json")
    assert result is None


def test_fetch_previous_manifest_local(tmp_path: Path) -> None:
    """fetch_previous_manifest reads local file."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"versions": {"3.12.8": {}}}')
    result = fetch_previous_manifest(str(manifest))
    assert result == {"versions": {"3.12.8": {}}}


def test_fetch_previous_manifest_local_missing(tmp_path: Path) -> None:
    """fetch_previous_manifest returns None if file missing."""
    result = fetch_previous_manifest(str(tmp_path / "nonexistent.json"))
    assert result is None


def test_collect_new_versions(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_versions finds binaries and checksums."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    # Create fake binary
    binary = tmp_path / "python-3.12.8-cosmo.com"
    binary.write_bytes(b"fake binary content")

    result = collect_new_versions("v1.0.0")

    assert "3.12.8" in result
    assert result["3.12.8"]["filename"] == "python-3.12.8-cosmo.com"
    assert result["3.12.8"]["release"] == "v1.0.0"
    assert "sha256" in result["3.12.8"]
    # Check checksum file was created
    assert (tmp_path / "python-3.12.8-cosmo.com.sha256").exists()


def test_collect_new_versions_uses_existing_checksum(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_versions uses existing .sha256 file."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    binary = tmp_path / "python-3.12.8-cosmo.com"
    binary.write_bytes(b"fake")
    checksum = tmp_path / "python-3.12.8-cosmo.com.sha256"
    checksum.write_text("abc123  python-3.12.8-cosmo.com\n")

    result = collect_new_versions("v1.0.0")
    assert result["3.12.8"]["sha256"] == "abc123"


def test_generate_manifest_basic(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest creates proper structure."""
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")

    new_versions = {
        "3.12.8": {"url": "http://a", "sha256": "aaa", "filename": "a.com", "release": "v1"},
        "3.13.1": {"url": "http://b", "sha256": "bbb", "filename": "b.com", "release": "v1"},
    }

    result = generate_manifest("v1.0.0", new_versions)

    assert result["release"] == "v1.0.0"
    assert result["cosmocc"] == "4.0.0"
    assert result["default"] == "3.13.1"
    assert "3.12" in result["latest"]
    assert "3.13" in result["latest"]
    assert "3.12.8" in result["versions"]
    assert "3.13.1" in result["versions"]


def test_generate_manifest_merges_previous(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest merges with previous manifest."""
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")

    prev_manifest = {
        "versions": {
            "3.11.9": {"url": "http://old", "sha256": "old", "release": "v0.9"},
        }
    }
    new_versions = {
        "3.12.8": {"url": "http://new", "sha256": "new", "filename": "new.com", "release": "v1"},
    }

    result = generate_manifest("v1.0.0", new_versions, prev_manifest)

    assert "3.11.9" in result["versions"]  # from previous
    assert "3.12.8" in result["versions"]  # from new


def test_generate_manifest_filters_disabled(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest excludes disabled versions."""
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {"3.9": "EOL"}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")

    new_versions = {
        "3.9.18": {"url": "http://a", "sha256": "a", "filename": "a.com", "release": "v1"},
        "3.12.8": {"url": "http://b", "sha256": "b", "filename": "b.com", "release": "v1"},
    }

    result = generate_manifest("v1.0.0", new_versions)

    assert "3.9.18" not in result["versions"]
    assert "3.12.8" in result["versions"]


def test_generate_manifest_prerelease_default(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest picks stable default over prerelease."""
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")

    new_versions = {
        "3.13.1": {"url": "http://a", "sha256": "a", "filename": "a.com", "release": "v1"},
        "3.14.0a1": {"url": "http://b", "sha256": "b", "filename": "b.com", "release": "v1"},
    }

    result = generate_manifest("v1.0.0", new_versions)
    assert result["default"] == "3.13.1"  # stable, not prerelease


def test_generate_manifest_only_prerelease(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest uses prerelease if no stable versions."""
    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")

    new_versions = {
        "3.14.0a1": {"url": "http://a", "sha256": "a", "filename": "a.com", "release": "v1"},
        "3.14.0a2": {"url": "http://b", "sha256": "b", "filename": "b.com", "release": "v1"},
    }

    result = generate_manifest("v1.0.0", new_versions)
    assert result["default"] == "3.14.0a2"  # highest prerelease


def test_print_summary(capsys: "pytest.CaptureFixture[str]") -> None:
    """print_summary outputs manifest info."""
    from ci.manifest import print_summary
    from ci.common import setup_logging
    setup_logging()

    manifest = {
        "release": "v1.0.0",
        "cosmocc": "4.0.0",
        "default": "3.13.1",
        "versions": {"3.13.1": {"release": "v1.0.0"}}
    }
    print_summary(manifest)

    out, _ = capsys.readouterr()
    assert "v1.0.0" in out
    assert "4.0.0" in out
    assert "3.13.1" in out


def test_collect_new_versions_skips_non_matching(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_versions skips files that don't match pattern."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    # Create files that don't match pattern
    (tmp_path / "python-invalid-cosmo.com").write_bytes(b"fake")
    (tmp_path / "other-file.txt").write_bytes(b"fake")
    # And one that does
    (tmp_path / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    result = collect_new_versions("v1.0.0")

    assert len(result) == 1
    assert "3.12.8" in result


def test_main_help(monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]") -> None:
    """main() with --help prints usage."""
    from ci.manifest import main
    monkeypatch.setattr("sys.argv", ["manifest", "--help"])

    result = main()

    assert result == 0
    out, _ = capsys.readouterr()
    assert "Usage:" in out


def test_main_no_args(monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]") -> None:
    """main() with no args prints help."""
    from ci.manifest import main
    monkeypatch.setattr("sys.argv", ["manifest"])

    result = main()

    assert result == 0


def test_main_unknown_arg(monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with unknown arg returns error."""
    from ci.manifest import main
    monkeypatch.setattr("sys.argv", ["manifest", "v1.0.0", "--unknown"])

    result = main()

    assert result == 1


def test_main_success(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() generates manifest successfully."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "v1.0.0"])

    result = main()

    assert result == 0
    assert (dist / "manifest.json").exists()


def test_main_with_merge(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with --merge fetches previous manifest."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Previous manifest
    prev = tmp_path / "prev-manifest.json"
    prev.write_text(json.dumps({"versions": {"3.12.8": {"url": "old", "release": "v0.9"}}}))

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "v1.0.0", "--merge", str(prev)])

    result = main()

    assert result == 0
    manifest = json.loads((dist / "manifest.json").read_text())
    assert "3.12.8" in manifest["versions"]  # from previous
    assert "3.13.1" in manifest["versions"]  # from new


def test_main_empty_tag(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with empty tag generates one."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", ""])

    result = main()

    assert result == 0


def test_main_uses_existing_manifest(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() uses existing manifest.json if present."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")
    (dist / "manifest.json").write_text(json.dumps({
        "versions": {"3.12.8": {"url": "old", "release": "v0.9"}}
    }))

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "v1.0.0"])

    result = main()

    assert result == 0
    manifest = json.loads((dist / "manifest.json").read_text())
    assert "3.12.8" in manifest["versions"]  # from existing


def test_main_warns_no_binaries(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]") -> None:
    """main() warns when no binaries found."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    # Create existing manifest so we have versions to work with
    (dist / "manifest.json").write_text(json.dumps({
        "versions": {"3.12.8": {"url": "old", "release": "v0.9"}}
    }))

    versions_file = tmp_path / "versions.json"
    versions_file.write_text(json.dumps({
        "python": {"disabled": {}},
        "cosmocc": {"default": "4.0.0"},
    }))

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.VERSIONS_FILE", versions_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "v1.0.0"])

    result = main()

    assert result == 0
    out, _ = capsys.readouterr()
    assert "No binaries found" in out
