"""Tests for ci/build_matrix.py."""

from ci import cdx


def make_test_cdx(tmp_path: "Path") -> "Path":
    """Create a test upstream.cdx.json file."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.12.1", url="http://x", sha256="a", license="PSF"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://y", sha256="b", license="PSF"
    ))
    bom.add_component(cdx.Component(
        name="cosmocc", version="4.0.0", url="http://z", sha256="c", license="ISC"
    ))
    bom.set_default("python", "3.13")
    bom.set_latest("python", "3.12", "3.12.1")
    bom.set_latest("python", "3.13", "3.13.0")
    bom.set_default("cosmocc", "4.0.0")

    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    return cdx_file


def test_main_all_versions(tmp_path: "Path", monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() with 'all' gets versions from upstream.cdx.json."""
    cdx_file = make_test_cdx(tmp_path)
    # Patch both locations where CDX_FILE might be imported
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("ci.build_matrix.CDX_FILE", cdx_file)

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
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("ci.build_matrix.CDX_FILE", cdx_file)

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


def test_main_no_github_output(tmp_path: "Path", monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() works without GITHUB_OUTPUT set."""
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("ci.build_matrix.CDX_FILE", cdx_file)

    # Don't set GITHUB_OUTPUT
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr("sys.argv", ["build_matrix", "3.13.0"])

    from ci.build_matrix import main
    result = main()

    assert result == 0
