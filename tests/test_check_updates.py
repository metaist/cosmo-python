"""Tests for ci/check_updates.py."""

from unittest.mock import patch, MagicMock

from ci import cdx
from ci.check_updates import (
    update_dependency,
    update_python_version,
    check_python_versions,
    check_dependencies,
)


def make_test_bom() -> cdx.Bom:
    """Create a test BOM with sample data."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.13.0", url="http://py/3.13.0.tgz",
        sha256="abc", license="PSF-2.0", license_url="http://psf",
        sigstore_identity="test@python.org", sigstore_issuer="https://accounts.google.com",
        eol="2029-10", status="bugfix", component_type="application"
    ))
    bom.add_component(cdx.Component(
        name="xz", version="5.6.0", url="http://xz/5.6.0.tar.gz",
        sha256="def", license="MIT", license_url="http://mit",
        gpg="ABC123", component_type="library"
    ))
    bom.set_default("python", "3.13")
    bom.set_latest("python", "3.13", "3.13.0")
    bom.set_default("xz", "5.6.0")
    bom.set_dependencies("python@3.13.0", ["xz@5.6.0"])
    return bom


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_dry_run(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency in dry-run mode doesn't modify bom."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)
    mock_sha256.return_value = "abc123"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    result = update_dependency(bom, "xz", "5.6.1")

    assert result is True
    assert bom.get_component("xz", "5.6.1") is None  # Not added


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_success(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency adds new version."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "def456"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://xz/5.6.1.tar.gz"
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    result = update_dependency(bom, "xz", "5.6.1")

    assert result is True
    assert bom.get_default_version("xz") == "5.6.1"
    comp = bom.get_component("xz", "5.6.1")
    assert comp is not None
    assert comp.sha256 == "def456"
    assert comp.license == "MIT"  # Copied from old default
    assert comp.gpg == "ABC123"  # Copied from old default


@patch("ci.check_updates.DEPS")
def test_update_dependency_unknown(mock_deps: MagicMock) -> None:
    """update_dependency returns False for unknown dep."""
    mock_deps.get.return_value = None
    bom = make_test_bom()
    result = update_dependency(bom, "unknown", "1.0.0")
    assert result is False


@patch("ci.check_updates.DEPS")
def test_update_dependency_no_url(mock_deps: MagicMock) -> None:
    """update_dependency returns False if build_url returns empty."""
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = ""
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    result = update_dependency(bom, "xz", "5.6.1")
    assert result is False


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_fetch_error(mock_deps: MagicMock, mock_sha256: MagicMock) -> None:
    """update_dependency returns False on fetch error."""
    mock_sha256.side_effect = Exception("Network error")
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    result = update_dependency(bom, "xz", "5.6.1")
    assert result is False


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_dry_run(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version in dry-run mode doesn't modify bom."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)
    mock_sha256.return_value = "abc123"

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test"
    mock_py.get_status.return_value = "bugfix"
    mock_py.get_eol.return_value = "2029-10"

    bom = make_test_bom()
    result = update_python_version(bom, "3.13", "3.13.1", mock_py)

    assert result is True
    assert bom.get_component("python", "3.13.1") is None  # Not added


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_success(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version adds new version."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "def456"

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://py/Python-3.13.1.tgz"
    mock_py.get_status.return_value = "bugfix"
    mock_py.get_eol.return_value = "2029-10"

    bom = make_test_bom()
    result = update_python_version(bom, "3.13", "3.13.1", mock_py)

    assert result is True
    assert bom.get_latest_version("python", "3.13") == "3.13.1"
    comp = bom.get_component("python", "3.13.1")
    assert comp is not None
    assert comp.sha256 == "def456"
    assert comp.license == "PSF-2.0"
    assert comp.sigstore_identity == "test@python.org"  # Copied
    assert comp.status == "bugfix"
    assert comp.eol == "2029-10"
    # Dependencies should be copied
    assert bom.get_dependencies("python@3.13.1") == ["xz@5.6.0"]


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_fetch_error(mock_sha256: MagicMock) -> None:
    """update_python_version returns False on fetch error."""
    mock_sha256.side_effect = Exception("Network error")

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test"

    bom = make_test_bom()
    result = update_python_version(bom, "3.13", "3.13.1", mock_py)
    assert result is False


def test_check_python_versions_finds_update() -> None:
    """check_python_versions finds updates."""
    mock_py = MagicMock()
    mock_py.fetch_latest.return_value = "3.13.1"
    mock_py.get_status.return_value = "bugfix"

    bom = make_test_bom()
    updates = check_python_versions(bom, mock_py)

    assert ("3.13", "3.13.1") in updates


def test_check_python_versions_current() -> None:
    """check_python_versions returns empty when current."""
    mock_py = MagicMock()
    mock_py.fetch_latest.return_value = "3.13.0"  # Same as current
    mock_py.get_status.return_value = "bugfix"

    bom = make_test_bom()
    updates = check_python_versions(bom, mock_py)

    assert len(updates) == 0


def test_check_python_versions_eol() -> None:
    """check_python_versions skips EOL versions."""
    mock_py = MagicMock()
    mock_py.fetch_latest.return_value = "3.13.1"
    mock_py.get_status.return_value = "eol"

    bom = make_test_bom()
    updates = check_python_versions(bom, mock_py)

    assert len(updates) == 0


def test_check_python_versions_no_current() -> None:
    """check_python_versions skips minors with no current version."""
    mock_py = MagicMock()

    # Create bom with latest set but no actual component
    bom = cdx.Bom()
    bom.set_latest("python", "3.13", "3.13.0")  # Set latest but no component

    updates = check_python_versions(bom, mock_py)

    assert len(updates) == 0
    mock_py.fetch_latest.assert_not_called()  # Should skip before fetching


@patch("ci.check_updates.DEPS")
def test_check_dependencies_finds_update(mock_deps: MagicMock) -> None:
    """check_dependencies finds updates."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = "5.6.1"
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    updates = check_dependencies(bom)

    assert ("xz", "5.6.1") in updates


@patch("ci.check_updates.DEPS")
def test_check_dependencies_current(mock_deps: MagicMock) -> None:
    """check_dependencies returns empty when current."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = "5.6.0"  # Same
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    updates = check_dependencies(bom)

    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_fetch_error(mock_deps: MagicMock) -> None:
    """check_dependencies handles fetch errors."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.side_effect = Exception("Network")
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    updates = check_dependencies(bom)

    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_unknown_upstream(mock_deps: MagicMock) -> None:
    """check_dependencies handles unknown upstream."""
    mock_deps.get.return_value = None

    bom = make_test_bom()
    updates = check_dependencies(bom)

    # xz has no upstream now
    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_no_default(mock_deps: MagicMock) -> None:
    """check_dependencies skips deps with no default version."""
    # Create bom with component but no default set
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="xz", version="5.6.0", url="http://x", sha256="a", license="MIT"
    ))
    # Don't set default for xz

    updates = check_dependencies(bom)

    assert len(updates) == 0
    mock_deps.get.assert_not_called()  # Should skip before looking up upstream


@patch("ci.check_updates.DEPS")
def test_check_dependencies_fetch_returns_none(mock_deps: MagicMock) -> None:
    """check_dependencies handles None from fetch."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = None
    mock_deps.get.return_value = mock_upstream

    bom = make_test_bom()
    updates = check_dependencies(bom)

    assert len(updates) == 0


@patch("subprocess.run")
def test_regenerate_readme_success(mock_run: MagicMock) -> None:
    """regenerate_readme calls uvx."""
    from ci.check_updates import regenerate_readme
    regenerate_readme()
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_regenerate_readme_not_found(mock_run: MagicMock) -> None:
    """regenerate_readme handles missing uvx."""
    from ci.check_updates import regenerate_readme
    mock_run.side_effect = FileNotFoundError()
    regenerate_readme()  # Should not raise


@patch("subprocess.run")
def test_regenerate_readme_failure(mock_run: MagicMock) -> None:
    """regenerate_readme handles subprocess error."""
    from ci.check_updates import regenerate_readme
    import subprocess
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    regenerate_readme()  # Should not raise


@patch("ci.check_updates.regenerate_readme")
@patch("ci.check_updates.cdx.dump")
@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.cdx.load")
def test_main_no_updates(
    mock_load: MagicMock,
    mock_check_py: MagicMock,
    mock_check_deps: MagicMock,
    mock_dump: MagicMock,
    mock_regen: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() with no updates."""
    from ci.check_updates import main

    mock_load.return_value = make_test_bom()
    mock_check_py.return_value = []
    mock_check_deps.return_value = []
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)

    result = main()

    assert result == 0
    mock_dump.assert_not_called()
    mock_regen.assert_not_called()


@patch("ci.check_updates.regenerate_readme")
@patch("ci.check_updates.cdx.dump")
@patch("ci.check_updates.update_dependency")
@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.update_python_version")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.cdx.load")
def test_main_with_updates(
    mock_load: MagicMock,
    mock_check_py: MagicMock,
    mock_update_py: MagicMock,
    mock_check_deps: MagicMock,
    mock_update_dep: MagicMock,
    mock_dump: MagicMock,
    mock_regen: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() with updates saves and regenerates."""
    from ci.check_updates import main

    mock_load.return_value = make_test_bom()
    mock_check_py.return_value = [("3.13", "3.13.2")]
    mock_update_py.return_value = True
    mock_check_deps.return_value = [("xz", "5.6.1")]
    mock_update_dep.return_value = True
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)

    result = main()

    assert result == 0
    mock_dump.assert_called_once()
    mock_regen.assert_called_once()


@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.cdx.load")
def test_main_dry_run(
    mock_load: MagicMock,
    mock_check_py: MagicMock,
    mock_check_deps: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() in dry-run doesn't save."""
    from ci.check_updates import main

    mock_load.return_value = make_test_bom()
    mock_check_py.return_value = [("3.13", "3.13.1")]  # Has updates
    mock_check_deps.return_value = []
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)

    result = main()

    assert result == 0
