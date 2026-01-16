"""Tests for ci/check_updates.py."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from ci.check_updates import (
    get_dep_license,
    update_dependency,
    update_python_version,
    check_python_versions,
    check_dependencies,
    ensure_license_info,
)


def test_get_dep_license_found() -> None:
    """get_dep_license extracts license from default version."""
    data = {
        "openssl": {
            "default": "3.5.4",
            "versions": {
                "3.5.4": {"license": "Apache-2.0", "license_url": "http://lic"}
            }
        }
    }
    result = get_dep_license(data, "openssl")
    assert result == ("Apache-2.0", "http://lic")


def test_get_dep_license_not_found() -> None:
    """get_dep_license returns None if no license."""
    data = {"openssl": {"default": "3.5.4", "versions": {"3.5.4": {}}}}
    result = get_dep_license(data, "openssl")
    assert result is None


def test_get_dep_license_no_default() -> None:
    """get_dep_license returns None if no default."""
    data = {"openssl": {"versions": {}}}
    result = get_dep_license(data, "openssl")
    assert result is None


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_dry_run(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency in dry-run mode doesn't modify data."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)
    mock_sha256.return_value = "abc123"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    data = {"xz": {"default": "5.6.0", "versions": {"5.6.0": {}}}}
    result = update_dependency(data, "xz", "5.6.1")

    assert result is True
    assert "5.6.1" not in data["xz"]["versions"]


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_success(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency adds new version."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test/5.6.1.tar.gz"
    mock_deps.get.return_value = mock_upstream

    data = {
        "xz": {
            "default": "5.6.0",
            "versions": {"5.6.0": {"license": "MIT", "license_url": "http://lic"}}
        }
    }
    result = update_dependency(data, "xz", "5.6.1")

    assert result is True
    assert data["xz"]["default"] == "5.6.1"
    assert data["xz"]["versions"]["5.6.1"]["sha256"] == "abc123"
    assert data["xz"]["versions"]["5.6.1"]["license"] == "MIT"


@patch("ci.check_updates.DEPS")
def test_update_dependency_unknown(mock_deps: MagicMock) -> None:
    """update_dependency returns False for unknown dep."""
    mock_deps.get.return_value = None
    data = {}
    result = update_dependency(data, "unknown", "1.0.0")
    assert result is False


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_fetch_error(mock_deps: MagicMock, mock_sha256: MagicMock) -> None:
    """update_dependency returns False on fetch error."""
    mock_sha256.side_effect = Exception("Network error")
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    data = {}
    result = update_dependency(data, "xz", "5.6.1")
    assert result is False


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.PythonUpstream")
def test_update_python_version_dry_run(mock_py: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version in dry-run mode doesn't modify data."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)
    mock_sha256.return_value = "abc123"
    mock_instance = MagicMock()
    mock_instance.build_url.return_value = "http://test"
    mock_instance.get_status.return_value = "bugfix"
    mock_instance.get_eol.return_value = "2029-10"

    data = {"python": {"latest": {"3.13": "3.13.0"}, "versions": {"3.13.0": {}}}}
    result = update_python_version(data, "3.13", "3.13.1", mock_instance)

    assert result is True
    assert "3.13.1" not in data["python"]["versions"]


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_success(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version adds new version."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test/Python-3.13.1.tgz"
    mock_py.get_status.return_value = "bugfix"
    mock_py.get_eol.return_value = "2029-10"

    data = {
        "python": {
            "latest": {"3.13": "3.13.0"},
            "versions": {"3.13.0": {"license": "PSF", "license_url": "http://psf"}}
        }
    }
    result = update_python_version(data, "3.13", "3.13.1", mock_py)

    assert result is True
    assert data["python"]["latest"]["3.13"] == "3.13.1"
    assert data["python"]["versions"]["3.13.1"]["sha256"] == "abc123"
    assert data["python"]["versions"]["3.13.1"]["status"] == "bugfix"


@patch("ci.check_updates.PythonUpstream")
def test_check_python_versions(mock_py_class: MagicMock) -> None:
    """check_python_versions finds updates."""
    mock_py = MagicMock()
    mock_py.fetch_latest.side_effect = lambda m: {"3.12": "3.12.9", "3.13": "3.13.1"}.get(m)
    mock_py.get_status.return_value = "bugfix"

    data = {
        "python": {
            "latest": {"3.12": "3.12.8", "3.13": "3.13.1"},
            "versions": {}
        }
    }
    updates = check_python_versions(data, mock_py)

    assert ("3.12", "3.12.9") in updates
    assert len(updates) == 1  # 3.13 is current


@patch("ci.check_updates.DEPS")
def test_check_dependencies(mock_deps: MagicMock) -> None:
    """check_dependencies finds updates."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = "5.6.1"
    mock_deps.get.return_value = mock_upstream
    mock_deps.__iter__ = lambda _: iter(["xz"])

    data = {"xz": {"default": "5.6.0"}}
    updates = check_dependencies(data)

    assert ("xz", "5.6.1") in updates


def test_ensure_license_info() -> None:
    """ensure_license_info backfills license."""
    data = {
        "xz": {
            "default": "5.6.1",
            "versions": {
                "5.6.0": {},
                "5.6.1": {"license": "MIT", "license_url": "http://lic"}
            }
        }
    }
    updated = ensure_license_info(data)

    assert updated is True
    assert data["xz"]["versions"]["5.6.0"]["license"] == "MIT"


def test_ensure_license_info_no_changes() -> None:
    """ensure_license_info returns False if nothing to do."""
    data = {
        "xz": {
            "default": "5.6.1",
            "versions": {
                "5.6.0": {"license": "MIT", "license_url": "http://lic"},
                "5.6.1": {"license": "MIT", "license_url": "http://lic"}
            }
        }
    }
    updated = ensure_license_info(data)
    assert updated is False


def test_save_versions(tmp_path: "Path", monkeypatch: "pytest.MonkeyPatch") -> None:
    """save_versions writes and normalizes."""
    from ci.check_updates import save_versions
    import json
    from pathlib import Path

    test_file = tmp_path / "versions.json"
    # Also need to patch where normalize reads from
    monkeypatch.setattr("ci.common.VERSIONS_FILE", test_file)
    monkeypatch.setattr("ci.check_updates.VERSIONS_FILE", test_file)
    monkeypatch.setattr("ci.normalize.VERSIONS_FILE", test_file)

    data = {"xz": {"default": "1.0", "versions": {}}, "python": {"default": "3.13", "versions": {}}}
    save_versions(data)

    result = json.loads(test_file.read_text())
    # Should be normalized: python first
    assert list(result.keys())[0] == "python"


@patch("ci.check_updates.DEPS")
def test_update_dependency_no_url(mock_deps: MagicMock) -> None:
    """update_dependency returns False if build_url returns empty."""
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = ""
    mock_deps.get.return_value = mock_upstream

    data = {}
    result = update_dependency(data, "xz", "5.6.1")
    assert result is False


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_fetch_error(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version returns False on fetch error."""
    mock_sha256.side_effect = Exception("Network error")

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test"

    data = {"python": {"latest": {}, "versions": {}}}
    result = update_python_version(data, "3.13", "3.13.1", mock_py)
    assert result is False


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_copies_sigstore(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version copies sigstore info from previous."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test"
    mock_py.get_status.return_value = "bugfix"
    mock_py.get_eol.return_value = "2029-10"

    data = {
        "python": {
            "latest": {"3.13": "3.13.0"},
            "versions": {
                "3.13.0": {
                    "sigstore": {"identity": "test@python.org"},
                    "license": "PSF",
                    "license_url": "http://psf"
                }
            }
        }
    }
    result = update_python_version(data, "3.13", "3.13.1", mock_py)

    assert result is True
    assert data["python"]["versions"]["3.13.1"]["sigstore"]["identity"] == "test@python.org"


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_copies_gpg(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency copies GPG fingerprint from previous."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    data = {
        "xz": {
            "default": "5.6.0",
            "versions": {"5.6.0": {"gpg": "ABC123FINGERPRINT"}}
        }
    }
    result = update_dependency(data, "xz", "5.6.1")

    assert result is True
    assert data["xz"]["versions"]["5.6.1"]["gpg"] == "ABC123FINGERPRINT"


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


@patch("ci.check_updates.PythonUpstream")
def test_check_python_versions_eol(mock_py_class: MagicMock) -> None:
    """check_python_versions warns about EOL versions."""
    mock_py = MagicMock()
    mock_py.fetch_latest.return_value = "3.8.20"
    mock_py.get_status.return_value = "eol"

    data = {
        "python": {
            "latest": {"3.8": "3.8.19"},
            "versions": {}
        }
    }
    updates = check_python_versions(data, mock_py)

    # EOL versions should not be in updates
    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_fetch_error(mock_deps: MagicMock) -> None:
    """check_dependencies handles fetch errors."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.side_effect = Exception("Network")
    mock_deps.get.return_value = mock_upstream

    data = {"xz": {"default": "5.6.0"}}
    updates = check_dependencies(data)

    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_unknown_upstream(mock_deps: MagicMock) -> None:
    """check_dependencies handles unknown upstream."""
    mock_deps.get.return_value = None

    data = {"unknown": {"default": "1.0"}}
    updates = check_dependencies(data)

    assert len(updates) == 0


@patch("ci.check_updates.DEPS")
def test_check_dependencies_fetch_returns_none(mock_deps: MagicMock) -> None:
    """check_dependencies handles None from fetch."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = None
    mock_deps.get.return_value = mock_upstream

    data = {"xz": {"default": "5.6.0"}}
    updates = check_dependencies(data)

    assert len(updates) == 0


@patch("ci.check_updates.regenerate_readme")
@patch("ci.check_updates.save_versions")
@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.ensure_license_info")
@patch("ci.check_updates.load_versions")
def test_main_no_updates(
    mock_load: MagicMock,
    mock_ensure: MagicMock,
    mock_check_py: MagicMock,
    mock_check_deps: MagicMock,
    mock_save: MagicMock,
    mock_regen: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() with no updates."""
    from ci.check_updates import main

    mock_load.return_value = {"python": {"latest": {}, "versions": {}}}
    mock_ensure.return_value = False
    mock_check_py.return_value = []
    mock_check_deps.return_value = []
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)

    result = main()

    assert result == 0
    mock_save.assert_not_called()
    mock_regen.assert_not_called()


@patch("ci.check_updates.regenerate_readme")
@patch("ci.check_updates.save_versions")
@patch("ci.check_updates.update_dependency")
@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.update_python_version")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.ensure_license_info")
@patch("ci.check_updates.load_versions")
def test_main_with_updates(
    mock_load: MagicMock,
    mock_ensure: MagicMock,
    mock_check_py: MagicMock,
    mock_update_py: MagicMock,
    mock_check_deps: MagicMock,
    mock_update_dep: MagicMock,
    mock_save: MagicMock,
    mock_regen: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() with updates saves and regenerates."""
    from ci.check_updates import main

    mock_load.return_value = {"python": {"latest": {}, "versions": {}}}
    mock_ensure.return_value = True
    mock_check_py.return_value = [("3.13", "3.13.2")]
    mock_update_py.return_value = True
    mock_check_deps.return_value = [("xz", "5.6.1")]
    mock_update_dep.return_value = True
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)

    result = main()

    assert result == 0
    mock_save.assert_called_once()
    mock_regen.assert_called_once()


@patch("ci.check_updates.check_dependencies")
@patch("ci.check_updates.check_python_versions")
@patch("ci.check_updates.ensure_license_info")
@patch("ci.check_updates.load_versions")
def test_main_dry_run(
    mock_load: MagicMock,
    mock_ensure: MagicMock,
    mock_check_py: MagicMock,
    mock_check_deps: MagicMock,
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """main() in dry-run doesn't save."""
    from ci.check_updates import main

    mock_load.return_value = {"python": {"latest": {}, "versions": {}}}
    mock_ensure.return_value = True
    mock_check_py.return_value = []
    mock_check_deps.return_value = []
    monkeypatch.setattr("ci.check_updates.DRY_RUN", True)

    result = main()

    assert result == 0


@patch("ci.check_updates.fetch_sha256")
@patch("ci.check_updates.DEPS")
def test_update_dependency_creates_new_dep(mock_deps: MagicMock, mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_dependency creates new dep entry if not present."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"
    mock_upstream = MagicMock()
    mock_upstream.build_url.return_value = "http://test"
    mock_deps.get.return_value = mock_upstream

    data = {}  # No xz entry
    result = update_dependency(data, "xz", "5.6.1")

    assert result is True
    assert "xz" in data
    assert data["xz"]["default"] == "5.6.1"


@patch("ci.check_updates.fetch_sha256")
def test_update_python_version_copies_license(mock_sha256: MagicMock, monkeypatch: "pytest.MonkeyPatch") -> None:
    """update_python_version copies license from default."""
    monkeypatch.setattr("ci.check_updates.DRY_RUN", False)
    mock_sha256.return_value = "abc123"

    mock_py = MagicMock()
    mock_py.build_url.return_value = "http://test"
    mock_py.get_status.return_value = "bugfix"
    mock_py.get_eol.return_value = "2029-10"

    # get_dep_license uses "default" to find license info
    data = {
        "python": {
            "default": "3.13.0",  # Points to version with license
            "latest": {"3.13": "3.13.0"},
            "versions": {
                "3.13.0": {"license": "PSF-2.0", "license_url": "http://psf"}
            }
        }
    }
    result = update_python_version(data, "3.13", "3.13.1", mock_py)

    assert result is True
    assert data["python"]["versions"]["3.13.1"]["license"] == "PSF-2.0"


def test_ensure_license_info_skips_no_license() -> None:
    """ensure_license_info skips deps without license info."""
    data = {
        "xz": {
            "default": "5.6.1",
            "versions": {
                "5.6.0": {},  # No license
                "5.6.1": {}   # No license on default either
            }
        }
    }
    updated = ensure_license_info(data)
    assert updated is False


@patch("ci.check_updates.DEPS")
def test_check_dependencies_logs_current(mock_deps: MagicMock) -> None:
    """check_dependencies logs when dep is current."""
    mock_upstream = MagicMock()
    mock_upstream.fetch_latest.return_value = "5.6.0"  # Same as current
    mock_deps.get.return_value = mock_upstream

    # Only include one dep to test the "current" branch
    data = {
        "cosmocc": {"default": "5.6.0"},
        "bz2": {"default": "5.6.0"},
        "cacert": {"default": "5.6.0"},
        "gdbm": {"default": "5.6.0"},
        "libffi": {"default": "5.6.0"},
        "ncurses": {"default": "5.6.0"},
        "openssl": {"default": "5.6.0"},
        "readline": {"default": "5.6.0"},
        "sqlite": {"default": "5.6.0"},
        "xz": {"default": "5.6.0"},
    }
    updates = check_dependencies(data)

    # All are current, no updates
    assert len(updates) == 0
