"""Tests for ci/release.py."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ci import release


@pytest.fixture
def tmp_dist(tmp_path: Path) -> Path:
    """Create temporary dist directory with mock binaries."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "python-3.12.1-cosmo.com").touch()
    (dist / "python-3.13.2-cosmo.com").touch()
    (dist / "python-3.14.0-cosmo.com").touch()
    return dist


@pytest.fixture
def tmp_changelog(tmp_path: Path) -> Path:
    """Create temporary CHANGELOG.md."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("""\
# Changelog

---

## [Unreleased]

[unreleased]: https://github.com/test/repo/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Fixed**

- [#1] bug fix one
- [#2] bug fix two

**Added**

- [#3] new feature

[#1]: https://github.com/test/repo/issues/1
[#2]: https://github.com/test/repo/issues/2
[#3]: https://github.com/test/repo/issues/3

---

## [20260101-120000] - 2026-01-01

Previous release.
""")
    return changelog


class TestMoveUnreleasedToRelease:
    """Tests for move_unreleased_to_release."""

    def test_moves_content_to_release_section(self, tmp_changelog: Path) -> None:
        """Should move Unreleased content to dated release section."""
        release.move_unreleased_to_release(
            "20260119-120000",
            tmp_changelog,
            "test/repo",
        )

        content = tmp_changelog.read_text()
        assert "## [20260119-120000] -" in content
        assert "[20260119-120000]: https://github.com/test/repo/releases/tag/20260119-120000" in content
        # Original content should be in new section
        assert "[#1] bug fix one" in content

    def test_missing_file(self, tmp_path: Path) -> None:
        """Should do nothing for missing file."""
        missing = tmp_path / "missing.md"
        release.move_unreleased_to_release("20260119-120000", missing)
        assert not missing.exists()

    def test_empty_unreleased(self, tmp_path: Path) -> None:
        """Should do nothing when Unreleased is empty."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n\nRelease.\n")
        original = changelog.read_text()
        release.move_unreleased_to_release("20260119-120000", changelog)
        assert changelog.read_text() == original




class TestExtractUnreleasedWithLinks:
    """Tests for extract_unreleased_with_links."""

    def test_extracts_content_and_links(self, tmp_changelog: Path) -> None:
        """Should extract content and link definitions."""
        result = release.extract_unreleased_with_links(tmp_changelog)
        assert "**Fixed**" in result
        assert "[#1] bug fix one" in result
        assert "[#1]: https://github.com/test/repo/issues/1" in result
        assert "[#3]: https://github.com/test/repo/issues/3" in result

    def test_excludes_header_and_description(self, tmp_changelog: Path) -> None:
        """Should exclude header and description paragraph."""
        result = release.extract_unreleased_with_links(tmp_changelog)
        assert "## [Unreleased]" not in result
        assert "[unreleased]:" not in result
        assert "These are changes" not in result

    def test_missing_file(self, tmp_path: Path) -> None:
        """Should return empty string for missing file."""
        result = release.extract_unreleased_with_links(tmp_path / "missing.md")
        assert result == ""

    def test_no_unreleased_section(self, tmp_path: Path) -> None:
        """Should return empty string if no Unreleased section."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n\nRelease.\n")
        result = release.extract_unreleased_with_links(changelog)
        assert result == ""


class TestGenerateVersionTable:
    """Tests for generate_version_table."""

    def test_generates_table_without_release_tag(self, tmp_dist: Path) -> None:
        """Should generate table with filenames only."""
        result = release.generate_version_table(tmp_dist)
        assert "| Python | Download |" in result
        assert "| 3.12 | `python-3.12.1-cosmo.com` |" in result
        assert "| 3.13 | `python-3.13.2-cosmo.com` |" in result
        assert "| 3.14 | `python-3.14.0-cosmo.com` |" in result

    def test_generates_table_with_release_tag(self, tmp_dist: Path) -> None:
        """Should generate table with download links."""
        result = release.generate_version_table(
            tmp_dist, release_tag="20260119-120000", repo="owner/repo"
        )
        assert "[python-3.12.1-cosmo.com]" in result
        assert "https://github.com/owner/repo/releases/download/20260119-120000/" in result

    def test_empty_dist(self, tmp_path: Path) -> None:
        """Should return empty string for empty dist."""
        empty_dist = tmp_path / "empty"
        empty_dist.mkdir()
        result = release.generate_version_table(empty_dist)
        assert result == ""

    def test_sorts_by_version(self, tmp_dist: Path) -> None:
        """Should sort versions correctly."""
        result = release.generate_version_table(tmp_dist)
        lines = result.split("\n")
        # Find version lines (skip header)
        versions = [l for l in lines if l.startswith("| 3.")]
        assert "3.12" in versions[0]
        assert "3.13" in versions[1]
        assert "3.14" in versions[2]

    def test_skips_non_matching_files(self, tmp_path: Path) -> None:
        """Should skip files that don't match the expected pattern."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "python-3.12.1-cosmo.com").touch()
        (dist / "not-a-python-binary.com").touch()  # doesn't match
        (dist / "python-invalid-cosmo.com").touch()  # doesn't match
        result = release.generate_version_table(dist)
        assert "3.12" in result
        assert "invalid" not in result
        assert "not-a-python" not in result


class TestGenerateSupplyChainTable:
    """Tests for generate_supply_chain_table."""

    def test_generates_table(self) -> None:
        """Should generate supply chain table from BOM."""
        from ci import cdx
        from ci.common import CDX_FILE

        bom = cdx.load(CDX_FILE)
        result = release.generate_supply_chain_table(bom)
        assert "| Dependency | Version |" in result
        assert "Python" in result
        assert "OpenSSL" in result


class TestGenerateReleaseNotes:
    """Tests for generate_release_notes."""

    def test_generates_complete_notes(
        self, tmp_dist: Path, tmp_changelog: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should generate complete release notes."""
        # Copy upstream.cdx.json to temp dir before changing cwd
        import shutil
        src = Path(__file__).parent.parent / "upstream.cdx.json"
        shutil.copy(src, tmp_dist.parent / "upstream.cdx.json")
        monkeypatch.chdir(tmp_dist.parent)

        result = release.generate_release_notes(
            tmp_dist,
            release_tag="20260119-120000",
            repo="owner/repo",
            changelog_path=tmp_changelog,
        )

        # Check structure
        assert "## Python Versions" in result
        assert "## Supply Chain" in result
        assert "## Changelog" in result

        # Check order (Python Versions before Supply Chain before Changelog)
        py_pos = result.find("## Python Versions")
        sc_pos = result.find("## Supply Chain")
        cl_pos = result.find("## Changelog")
        assert py_pos < sc_pos < cl_pos

        # Check content
        assert "Default Python version:" in result
        assert "[python-3.12.1-cosmo.com]" in result
        assert "[#1] bug fix one" in result

    def test_handles_empty_dist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle empty dist directory (no version table)."""
        import shutil
        src = Path(__file__).parent.parent / "upstream.cdx.json"
        shutil.copy(src, tmp_path / "upstream.cdx.json")
        monkeypatch.chdir(tmp_path)

        empty_dist = tmp_path / "empty_dist"
        empty_dist.mkdir()

        result = release.generate_release_notes(empty_dist)

        # No Python Versions section when no binaries
        assert "## Python Versions" not in result
        # But Supply Chain should still be there
        assert "## Supply Chain" in result

    def test_handles_empty_changelog(
        self, tmp_dist: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle empty/missing changelog."""
        import shutil
        src = Path(__file__).parent.parent / "upstream.cdx.json"
        shutil.copy(src, tmp_path / "upstream.cdx.json")
        monkeypatch.chdir(tmp_path)

        # Create empty changelog
        empty_changelog = tmp_path / "CHANGELOG.md"
        empty_changelog.write_text("# Changelog\n\nNo unreleased section.\n")

        result = release.generate_release_notes(
            tmp_dist,
            changelog_path=empty_changelog,
        )

        # No Changelog section when changelog is empty
        assert "## Changelog" not in result
        # But Python Versions should still be there
        assert "## Python Versions" in result


class TestMain:
    """Tests for main function."""

    def test_missing_dist_dir(self) -> None:
        """Should return 1 for missing dist dir."""
        with patch.object(sys, "argv", ["release", "/nonexistent"]):
            assert release.main() == 1

    def test_empty_dist_dir(self, tmp_path: Path) -> None:
        """Should return 1 for empty dist dir."""
        empty_dist = tmp_path / "empty"
        empty_dist.mkdir()
        with patch.object(sys, "argv", ["release", str(empty_dist)]):
            assert release.main() == 1

    def test_writes_output_file(self, tmp_dist: Path, tmp_changelog: Path) -> None:
        """Should write to output file when specified."""
        output = tmp_dist.parent / "notes.md"
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--output", str(output)],
        ):
            result = release.main()
        assert result == 0
        assert output.exists()
        content = output.read_text()
        assert "## Python Versions" in content

    def test_writes_github_output(
        self, tmp_dist: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should write to GITHUB_OUTPUT when set."""
        github_output = tmp_path / "github_output"
        github_output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))

        with patch.object(sys, "argv", ["release", str(tmp_dist)]):
            result = release.main()

        assert result == 0
        content = github_output.read_text()
        assert "version_table<<EOF" in content
        assert "default_version=" in content
        assert "release_notes<<EOF" in content

    def test_parses_release_tag_arg(self, tmp_dist: Path) -> None:
        """Should parse --release-tag argument."""
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--release-tag", "20260119-120000"],
        ):
            result = release.main()
        assert result == 0

    def test_parses_repo_arg(self, tmp_dist: Path) -> None:
        """Should parse --repo argument."""
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--repo", "other/repo"],
        ):
            result = release.main()
        assert result == 0

    def test_ignores_unknown_args(self, tmp_dist: Path) -> None:
        """Should ignore unknown arguments."""
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--unknown", "value"],
        ):
            result = release.main()
        assert result == 0

    def test_handles_args_at_end_without_values(self, tmp_dist: Path) -> None:
        """Should handle args at end of argv without values."""
        # --release-tag at end without value
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--release-tag"],
        ):
            result = release.main()
        assert result == 0

        # --repo at end without value
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--repo"],
        ):
            result = release.main()
        assert result == 0

        # --output at end without value
        with patch.object(
            sys,
            "argv",
            ["release", str(tmp_dist), "--output"],
        ):
            result = release.main()
        assert result == 0

    def test_update_changelog_flag(
        self, tmp_dist: Path, tmp_changelog: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should update changelog when --update-changelog is specified."""
        monkeypatch.setattr(release, "CHANGELOG_PATH", tmp_changelog)

        with patch.object(
            sys,
            "argv",
            [
                "release",
                str(tmp_dist),
                "--release-tag",
                "20260119-120000",
                "--update-changelog",
            ],
        ):
            result = release.main()

        assert result == 0
        content = tmp_changelog.read_text()
        assert "## [20260119-120000]" in content
