"""Tests for ci/normalize.py."""

import json
from pathlib import Path

from ci.normalize import sort_version_keys, sort_package_keys, normalize


def test_sort_version_keys_preferred_order() -> None:
    """Keys are sorted in preferred order."""
    data = {
        "sha256": "abc123",
        "url": "https://example.com",
        "license": "MIT",
        "eol": "2030-01",
        "status": "bugfix",
    }
    result = sort_version_keys(data)
    keys = list(result.keys())
    assert keys == ["eol", "status", "url", "sha256", "license"]


def test_sort_version_keys_unknown_at_end() -> None:
    """Unknown keys are sorted alphabetically at end."""
    data = {
        "url": "https://example.com",
        "sha256": "abc123",
        "zebra": "unknown",
        "apple": "unknown",
    }
    result = sort_version_keys(data)
    keys = list(result.keys())
    assert keys == ["url", "sha256", "apple", "zebra"]


def test_sort_version_keys_gpg_sigstore() -> None:
    """GPG and sigstore keys are in correct position."""
    data = {
        "sha256": "abc123",
        "url": "https://example.com",
        "gpg": "FINGERPRINT",
        "sigstore": {"identity": "test"},
        "license": "MIT",
    }
    result = sort_version_keys(data)
    keys = list(result.keys())
    assert keys == ["url", "sha256", "gpg", "sigstore", "license"]


def test_sort_package_keys_preferred_order() -> None:
    """Package keys are sorted in preferred order."""
    data = {
        "versions": {},
        "latest": {"3.13": "3.13.1"},
        "default": "3.13",
        "disabled": {},
    }
    result = sort_package_keys(data)
    keys = list(result.keys())
    assert keys == ["default", "disabled", "latest", "versions"]


def test_sort_package_keys_unknown_at_end() -> None:
    """Unknown keys are sorted alphabetically at end."""
    data = {
        "versions": {},
        "default": "1.0",
        "custom_field": "value",
    }
    result = sort_package_keys(data)
    keys = list(result.keys())
    assert keys == ["default", "versions", "custom_field"]


def test_normalize_main(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    """main() normalizes versions.json."""
    from ci.normalize import main

    test_file = tmp_path / "versions.json"
    test_file.write_text(json.dumps({"python": {"default": "3.13", "versions": {}}}))
    monkeypatch.setattr("ci.common.VERSIONS_FILE", test_file)

    result = main()
    assert result == 0


def test_normalize_full(tmp_path: Path) -> None:
    """Full normalize function orders everything."""
    data = {
        "xz": {
            "versions": {
                "5.6.1": {"sha256": "aaa", "url": "http://a"},
                "5.4.0": {"sha256": "bbb", "url": "http://b"},
            },
            "default": "5.6.1",
        },
        "python": {
            "versions": {
                "3.13.1": {"sha256": "ccc", "url": "http://c"},
                "3.12.8": {"sha256": "ddd", "url": "http://d"},
            },
            "default": "3.13",
            "latest": {"3.12": "3.12.8", "3.13": "3.13.1"},
        },
        "cosmocc": {"default": "4.0.2", "versions": {}},
    }
    path = tmp_path / "versions.json"
    path.write_text(json.dumps(data))

    normalize(path)

    result = json.loads(path.read_text())
    # Package order: python, cosmocc, then alpha
    assert list(result.keys()) == ["python", "cosmocc", "xz"]
    # Version order: semver sorted
    assert list(result["python"]["versions"].keys()) == ["3.12.8", "3.13.1"]
    assert list(result["xz"]["versions"].keys()) == ["5.4.0", "5.6.1"]


def test_normalize_skips_missing_packages(tmp_path: Path) -> None:
    """normalize skips packages in order that don't exist."""
    data = {
        "xz": {"default": "5.6.1", "versions": {}},
        # python and cosmocc not present
    }
    path = tmp_path / "versions.json"
    path.write_text(json.dumps(data))

    normalize(path)

    result = json.loads(path.read_text())
    assert list(result.keys()) == ["xz"]
