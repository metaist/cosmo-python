"""Tests for ci/release_notes.py."""

from pathlib import Path

import pytest

from ci import cdx
from ci.release_notes import extract_unreleased, generate_deps_table, move_unreleased_to_release


def make_test_cdx(tmp_path: Path) -> Path:
    """Create a test upstream.cdx.json file."""
    bom = cdx.Bom()
    bom.add_component(cdx.Component(
        name="python", version="3.12.8", url="http://x", sha256="a", license="PSF-2.0"
    ))
    bom.add_component(cdx.Component(
        name="python", version="3.13.1", url="http://y", sha256="b", license="PSF-2.0"
    ))
    bom.add_component(cdx.Component(
        name="openssl", version="3.5.4", url="http://z", sha256="c", license="Apache-2.0"
    ))
    bom.set_default("python", "3.13.1")
    bom.set_default("openssl", "3.5.4")
    bom.set_latest("python", "3.12", "3.12.8")
    bom.set_latest("python", "3.13", "3.13.1")

    cdx_file = tmp_path / "upstream.cdx.json"
    cdx.dump(bom, cdx_file)
    return cdx_file


SAMPLE_CHANGELOG = """\
# Changelog

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Changed**

- Updated foo to bar
- Fixed baz

**Added**

- New feature X

---

[#1]: https://github.com/test/repo/issues/1
"""


def test_extract_unreleased(tmp_path: Path) -> None:
    """extract_unreleased returns content from Unreleased section."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG)

    result = extract_unreleased(changelog)

    assert "**Changed**" in result
    assert "Updated foo to bar" in result
    assert "**Added**" in result
    assert "New feature X" in result


def test_extract_unreleased_empty(tmp_path: Path) -> None:
    """extract_unreleased returns empty string when section is empty."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("""\
# Changelog

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

---

[#1]: https://github.com/test/repo/issues/1
""")

    result = extract_unreleased(changelog)
    assert result == ""


def test_extract_unreleased_no_file(tmp_path: Path) -> None:
    """extract_unreleased returns empty string when file doesn't exist."""
    result = extract_unreleased(tmp_path / "nonexistent.md")
    assert result == ""


def test_generate_deps_table(tmp_path: Path) -> None:
    """generate_deps_table creates markdown table from bom."""
    cdx_file = make_test_cdx(tmp_path)
    bom = cdx.load(cdx_file)

    result = generate_deps_table(bom)

    assert "| Dependency | Version | Integrity | Signature | License |" in result
    assert "Python" in result
    assert "3.12–3.13" in result
    assert "OpenSSL" in result
    assert "3.5.4" in result


def test_move_unreleased_to_release(tmp_path: Path) -> None:
    """move_unreleased_to_release updates changelog with release section."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG)

    move_unreleased_to_release("20260116-120000", changelog)

    content = changelog.read_text()
    assert "## [20260116-120000]" in content
    assert "Updated foo to bar" in content
    # Link should be added
    assert "[20260116-120000]: https://github.com/metaist/cosmo-python/releases/tag/20260116-120000" in content


def test_move_unreleased_no_file(tmp_path: Path) -> None:
    """move_unreleased_to_release does nothing if file doesn't exist."""
    changelog = tmp_path / "nonexistent.md"
    move_unreleased_to_release("20260116-120000", changelog)
    assert not changelog.exists()


def test_move_unreleased_empty_content(tmp_path: Path) -> None:
    """move_unreleased_to_release does nothing if unreleased is empty."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("""\
# Changelog

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

---

[#1]: https://github.com/test/repo/issues/1
""")
    original = changelog.read_text()

    move_unreleased_to_release("20260116-120000", changelog)

    # File unchanged
    assert changelog.read_text() == original


def test_move_unreleased_with_existing_release(tmp_path: Path) -> None:
    """move_unreleased_to_release handles existing release links."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("""\
# Changelog

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Added**

- New thing

---

[20260115-100000]: https://github.com/metaist/cosmo-python/releases/tag/20260115-100000

[#1]: https://github.com/test/repo/issues/1
""")

    move_unreleased_to_release("20260116-120000", changelog)

    content = changelog.read_text()
    assert "## [20260116-120000]" in content
    # Both release links should exist
    assert "[20260116-120000]:" in content
    assert "[20260115-100000]:" in content


def test_move_unreleased_bad_format(tmp_path: Path) -> None:
    """move_unreleased_to_release handles non-standard changelog format."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Just a title\n\nSome content\n")
    original = changelog.read_text()

    move_unreleased_to_release("20260116-120000", changelog)

    # File unchanged - pattern didn't match
    assert changelog.read_text() == original


def test_main_generates_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() generates version table from binaries."""
    # Create fake dist dir with binaries
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.8-cosmo.com").write_bytes(b"fake")
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Create upstream.cdx.json
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)
    monkeypatch.setattr("ci.release_notes.CDX_FILE", cdx_file)

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
    assert "deps_table<<EOF" in output
    assert "changelog<<EOF" in output


def test_main_no_binaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns error if no binaries found."""
    dist = tmp_path / "dist"
    dist.mkdir()

    monkeypatch.setattr("sys.argv", ["release_notes", str(dist)])

    from ci.release_notes import main
    result = main()

    assert result == 1


def test_main_no_dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns error if dist doesn't exist."""
    monkeypatch.setattr("sys.argv", ["release_notes", str(tmp_path / "nonexistent")])

    from ci.release_notes import main
    result = main()

    assert result == 1


def test_main_update_changelog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() with --update-changelog modifies the changelog."""
    # Create fake dist dir with binaries
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    # Create upstream.cdx.json
    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)

    # Create changelog
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG)
    monkeypatch.setattr("ci.release_notes.CHANGELOG_PATH", changelog)

    monkeypatch.setattr("sys.argv", [
        "release_notes", str(dist),
        "--release-tag", "20260116-150000",
        "--update-changelog"
    ])

    from ci.release_notes import main
    result = main()

    assert result == 0
    content = changelog.read_text()
    assert "## [20260116-150000]" in content


def test_main_ignores_unknown_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() ignores unknown arguments."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")

    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)

    monkeypatch.setattr("sys.argv", [
        "release_notes", str(dist), "--unknown", "arg"
    ])

    from ci.release_notes import main
    result = main()

    assert result == 0


def test_main_ignores_non_matching_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() ignores files that don't match python version pattern."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.13.1-cosmo.com").write_bytes(b"fake")
    (dist / "python-invalid-cosmo.com").write_bytes(b"fake")  # Matches glob but not regex

    cdx_file = make_test_cdx(tmp_path)
    monkeypatch.setattr("ci.common.CDX_FILE", cdx_file)

    output_file = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr("sys.argv", ["release_notes", str(dist)])

    from ci.release_notes import main
    result = main()

    assert result == 0
    output = output_file.read_text()
    # Only 3.13.x should be in table
    assert "3.13.x" in output
    assert "invalid" not in output


def test_move_unreleased_no_links_section(tmp_path: Path) -> None:
    """move_unreleased_to_release handles changelog without link definitions."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("""\
# Changelog

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Added**

- New thing

---
""")  # No link definitions after ---

    move_unreleased_to_release("20260116-120000", changelog)

    # Should not crash, content may be unchanged or partially updated
    assert changelog.exists()
