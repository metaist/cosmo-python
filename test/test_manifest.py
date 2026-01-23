"""Tests for ci/manifest.py."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from ci import cdx
from ci.manifest import (
    is_prerelease,
    get_cosmocc_version,
    get_repo,
    fetch_previous_manifest,
    collect_new_binaries,
    generate_manifest,
)


def make_test_cdx(tmp_path: Path, disabled: list[str] | None = None) -> Path:
    """Create a test upstream.cdx.json file with Python and dependencies."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="cosmocc", version="4.0.0", url="http://x", sha256="a", license="ISC"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.12.8", url="http://py1", sha256="p1", license="PSF-2.0"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.13.1", url="http://py2", sha256="p2", license="PSF-2.0"
    ))
    bom.add_component(cdx.Component(
        name="openssl", version="3.5.4", url="http://ssl", sha256="ssl", license="Apache-2.0"
    ))
    bom.add_component(cdx.Component(
        name="readline", version="8.3", url="http://rl", sha256="rl", license="GPL-3.0"
    ))
    bom.add_component(cdx.Component(
        name="ncurses", version="6.6", url="http://nc", sha256="nc", license="X11"
    ))
    bom.set_default("cosmocc", "4.0.0")
    bom.set_default("python", "3.13.1")
    bom.set_latest("python", "3.12", "3.12.8")
    bom.set_latest("python", "3.13", "3.13.1")
    # Dependencies for python builds (what manifest.py looks up)
    bom.set_dependencies("python@3.12.8", ["openssl@3.5.4", "readline@8.3", "ncurses@6.6"])
    bom.set_dependencies("python@3.13.1", ["openssl@3.5.4", "readline@8.3", "ncurses@6.6"])
    # Library interdependency
    bom.set_dependencies("readline@8.3", ["ncurses@6.6"])
    if disabled:
        bom.set_disabled("python", disabled)

    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    return cdx_file


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
    """get_cosmocc_version reads from upstream.cdx.json."""
    monkeypatch.delenv("COSMOCC_VERSION", raising=False)
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    assert get_cosmocc_version() == "4.0.0"


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
def test_fetch_previous_manifest_url(mock_urlopen: MagicMock, tmp_path: Path) -> None:
    """fetch_previous_manifest fetches from URL."""
    # Create a minimal CycloneDX BOM to return (manifest has cosmo-python)
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="cosmo-python", version="3.12.8", url="http://old", sha256="old", license="PSF-2.0"
    ))
    cdx_data = cdx.dump(bom)

    mock_response = MagicMock()
    mock_response.read.return_value = bytes(str(cdx_data).replace("'", '"'), "utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    # This will fail since we're mocking with dict, let's use JSON
    import json
    mock_response.read.return_value = json.dumps(cdx_data).encode()

    result = fetch_previous_manifest("https://example.com/manifest.cdx.json")
    assert result is not None
    assert isinstance(result, cdx.Bom)


@patch("urllib.request.urlopen")
def test_fetch_previous_manifest_url_failure(mock_urlopen: MagicMock) -> None:
    """fetch_previous_manifest returns None on error."""
    mock_urlopen.side_effect = OSError("Network error")
    result = fetch_previous_manifest("https://example.com/manifest.cdx.json")
    assert result is None


def test_fetch_previous_manifest_local(tmp_path: Path) -> None:
    """fetch_previous_manifest reads local file."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="cosmo-python", version="3.12.8", url="http://old", sha256="old", license="PSF-2.0"
    ))
    manifest = tmp_path / "manifest.cdx.json"
    cdx.dump(bom, manifest)

    result = fetch_previous_manifest(str(manifest))
    assert result is not None
    assert result.get_component("cosmo-python", "3.12.8") is not None


def test_fetch_previous_manifest_local_missing(tmp_path: Path) -> None:
    """fetch_previous_manifest returns None if file missing."""
    result = fetch_previous_manifest(str(tmp_path / "nonexistent.json"))
    assert result is None


def test_collect_new_binaries(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_binaries finds binaries and checksums."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    # Create fake binary
    binary = tmp_path / "python-3.12.8-cosmo.com"
    binary.write_bytes(b"fake binary content")

    result = collect_new_binaries("20260115-134426")

    assert "3.12.8" in result
    assert result["3.12.8"]["filename"] == "python-3.12.8-cosmo.com"
    assert "sha256" in result["3.12.8"]
    # Check checksum file was created
    assert (tmp_path / "python-3.12.8-cosmo.com.sha256").exists()


def test_collect_new_binaries_uses_existing_checksum(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_binaries uses existing .sha256 file."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    binary = tmp_path / "python-3.12.8-cosmo.com"
    binary.write_bytes(b"fake")
    checksum = tmp_path / "python-3.12.8-cosmo.com.sha256"
    checksum.write_text("abc123  python-3.12.8-cosmo.com\n")

    result = collect_new_binaries("20260115-134426")
    assert result["3.12.8"]["sha256"] == "abc123"


def test_collect_new_binaries_prerelease(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_binaries handles prerelease versions."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    (tmp_path / "python-3.14.0a1-cosmo.com").write_bytes(b"fake")
    (tmp_path / "python-3.14.0rc1-cosmo.com").write_bytes(b"fake")

    result = collect_new_binaries("20260115-134426")
    assert "3.14.0a1" in result
    assert "3.14.0rc1" in result


def test_generate_manifest_basic(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest creates proper CycloneDX structure."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.12.8": {"url": "http://a", "sha256": "aaa", "filename": "a.com"},
        "3.13.1": {"url": "http://b", "sha256": "bbb", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)

    assert result._release == "20260115-134426"
    assert result.get_default_version("python") == "3.13.1"
    assert result.get_latest_version("python", "3.12") == "3.12.8"
    assert result.get_latest_version("python", "3.13") == "3.13.1"
    assert result.get_component("cosmo-python", "3.12.8") is not None
    assert result.get_component("cosmo-python", "3.13.1") is not None
    # Check cosmocc is included
    assert result.get_component("cosmocc", "4.0.0") is not None


def test_generate_manifest_includes_deps(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest includes dependencies."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.13.1": {"url": "http://b", "sha256": "bbb", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)

    # Check openssl dependency is included
    assert result.get_component("openssl", "3.5.4") is not None
    # Check dependency relationship
    deps = result.get_dependencies("cosmo-python@3.13.1")
    assert "openssl@3.5.4" in deps
    # Check library interdependency is copied
    readline_deps = result.get_dependencies("readline@8.3")
    assert "ncurses@6.6" in readline_deps


def test_generate_manifest_merges_previous(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest merges with previous manifest."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    # Create previous manifest (has cosmo-python components)
    prev_bom = cdx.Bom()
    prev_bom.add_component(cdx.Component(
        name="cosmo-python", version="3.11.9", url="http://old", sha256="old", license="PSF-2.0"
    ))
    prev_bom._component_releases["cosmo-python@3.11.9"] = "20260101-000000"

    new_binaries = {
        "3.12.8": {"url": "http://new", "sha256": "new", "filename": "new.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries, prev_bom)

    assert result.get_component("cosmo-python", "3.11.9") is not None  # from previous
    assert result.get_component("cosmo-python", "3.12.8") is not None  # from new


def test_generate_manifest_filters_disabled(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest excludes disabled versions."""
    cdx_file = make_test_cdx(tmp_path, disabled=["3.9"])
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.9.18": {"url": "http://a", "sha256": "a", "filename": "a.com"},
        "3.12.8": {"url": "http://b", "sha256": "b", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)

    assert result.get_component("cosmo-python", "3.9.18") is None
    assert result.get_component("cosmo-python", "3.12.8") is not None


def test_generate_manifest_prerelease_default(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest picks stable default over prerelease."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.13.1": {"url": "http://a", "sha256": "a", "filename": "a.com"},
        "3.14.0a1": {"url": "http://b", "sha256": "b", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)
    default_version = result.get_default_version("python")
    assert default_version == "3.13.1"  # stable, not prerelease


def test_generate_manifest_only_prereleases(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest uses highest prerelease when no stable versions."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.14.0a1": {"url": "http://a", "sha256": "a", "filename": "a.com"},
        "3.14.0b2": {"url": "http/b", "sha256": "b", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)
    default_version = result.get_default_version("python")
    assert default_version == "3.14.0b2"  # highest prerelease


def test_generate_manifest_no_binaries(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest handles no binaries."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    result = generate_manifest("20260115-134426", {})
    # No default set when no versions
    assert result.get_default_version("python") is None


def test_generate_manifest_attestation_repo(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest includes attestation repo."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    new_binaries = {
        "3.13.1": {"url": "http://a", "sha256": "a", "filename": "a.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)
    comp = result.get_component("cosmo-python", "3.13.1")
    assert comp is not None
    assert comp.attestation_repo == "test/repo"


def test_print_summary(tmp_path: Path, capsys: "pytest.CaptureFixture[str]") -> None:
    """print_summary outputs manifest info."""
    from ci.manifest import print_summary
    from ci.common import setup_logging
    setup_logging()

    bom = cdx.Bom()
    bom._release = "20260115-134426"
    bom.add_component(cdx.Component(
        name="python", version="3.13.1", url="http://a", sha256="a", license="PSF-2.0"
    ))
    bom.set_default("python", "3.13")
    bom.set_latest("python", "3.13", "3.13.1")
    bom._component_releases["cosmo-python@3.13.1"] = "20260115-134426"

    print_summary(bom)

    out, _ = capsys.readouterr()
    assert "20260115-134426" in out
    assert "3.13.1" in out


def test_collect_new_binaries_skips_non_matching(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """collect_new_binaries skips files that don't match pattern."""
    monkeypatch.setattr("ci.manifest.DIST_DIR", tmp_path)
    monkeypatch.setenv("REPO", "test/repo")

    # Create files that don't match pattern
    (tmp_path / "python-invalid-cosmo.com").write_bytes(b"fake")
    (tmp_path / "other-file.txt").write_bytes(b"fake")
    # And one that does
    (tmp_path / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    result = collect_new_binaries("20260115-134426")

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
    monkeypatch.setattr("sys.argv", ["manifest", "20260115-134426", "--unknown"])

    result = main()

    assert result == 1


def test_main_success(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() generates manifest successfully."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    cdx_file = make_test_cdx(tmp_path)

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "20260115-134426"])

    result = main()

    assert result == 0
    assert (dist / "manifest.cdx.json").exists()


def test_main_with_merge(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with --merge fetches previous manifest."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Previous manifest (has cosmo-python components)
    prev_bom = cdx.Bom()
    prev_bom.add_component(cdx.Component(
        name="cosmo-python", version="3.12.8", url="http://old", sha256="old", license="PSF-2.0"
    ))
    prev = tmp_path / "prev-manifest.cdx.json"
    cdx.dump(prev_bom, prev)

    cdx_file = make_test_cdx(tmp_path)

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "20260115-134426", "--merge", str(prev)])

    result = main()

    assert result == 0
    manifest = cdx.load(dist / "manifest.cdx.json")
    assert manifest.get_component("cosmo-python", "3.12.8") is not None  # from previous
    assert manifest.get_component("cosmo-python", "3.13.1") is not None  # from new


def test_main_empty_tag(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with empty tag generates one."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")

    cdx_file = make_test_cdx(tmp_path)

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", ""])

    result = main()

    assert result == 0


def test_main_uses_existing_manifest(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() uses existing manifest.cdx.json if present."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Create existing manifest (has cosmo-python components)
    existing_bom = cdx.Bom()
    existing_bom.add_component(cdx.Component(
        name="cosmo-python", version="3.12.8", url="http://old", sha256="old", license="PSF-2.0"
    ))
    cdx.dump(existing_bom, dist / "manifest.cdx.json")

    cdx_file = make_test_cdx(tmp_path)

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "20260115-134426"])

    result = main()

    assert result == 0
    manifest = cdx.load(dist / "manifest.cdx.json")
    assert manifest.get_component("cosmo-python", "3.12.8") is not None  # from existing


def test_main_warns_no_binaries(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]") -> None:
    """main() warns when no binaries found."""
    from ci.manifest import main

    dist = tmp_path / "dist"
    dist.mkdir()
    # Create existing manifest so we have versions to work with
    existing_bom = cdx.Bom()
    existing_bom.add_component(cdx.Component(
        name="cosmo-python", version="3.12.8", url="http://old", sha256="old", license="PSF-2.0"
    ))
    cdx.dump(existing_bom, dist / "manifest.cdx.json")

    cdx_file = make_test_cdx(tmp_path)

    monkeypatch.setattr("ci.manifest.DIST_DIR", dist)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")
    monkeypatch.setattr("sys.argv", ["manifest", "20260115-134426"])

    result = main()

    assert result == 0
    out, _ = capsys.readouterr()
    assert "No binaries found" in out


def test_generate_manifest_without_cosmocc(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest works when cosmocc version not in upstream."""
    # Create upstream without the requested cosmocc version
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.1", url="http://py", sha256="p", license="PSF-2.0"
    ))
    bom.set_default("python", "3.13.1")
    bom.set_latest("python", "3.13", "3.13.1")
    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)

    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "9.9.9")  # Not in upstream
    monkeypatch.setenv("REPO", "test/repo")

    from ci.manifest import generate_manifest

    new_binaries = {
        "3.13.1": {"url": "http://b", "sha256": "bbb", "filename": "b.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)

    # Should work, just no cosmocc component
    assert result.get_component("cosmocc", "9.9.9") is None
    assert result.get_component("cosmo-python", "3.13.1") is not None


def test_generate_manifest_version_not_newer(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """generate_manifest doesn't update latest when adding older version after newer."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.manifest.CDX_FILE", cdx_file)
    monkeypatch.setenv("COSMOCC_VERSION", "4.0.0")
    monkeypatch.setenv("REPO", "test/repo")

    from ci.manifest import generate_manifest

    # Build both 3.13.1 (newer) and 3.13.0 (older) - iteration order matters
    # Using dict that has newer version first
    new_binaries = {
        "3.13.1": {"url": "http://new", "sha256": "new", "filename": "new.com"},
        "3.13.0": {"url": "http://old", "sha256": "old", "filename": "old.com"},
    }

    result = generate_manifest("20260115-134426", new_binaries)

    # latest should be 3.13.1, not overwritten by 3.13.0
    assert result.get_latest_version("python", "3.13") == "3.13.1"
