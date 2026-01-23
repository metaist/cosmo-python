"""Tests for ci/docs.py."""

from ci.docs import include_doc, DOCS_DIR


def test_include_doc_full_file() -> None:
    """include_doc reads entire file when no markers specified."""
    content = include_doc("docs/index.md")
    assert "# cosmo-python" in content
    assert "## Why?" in content


def test_include_doc_with_start_marker() -> None:
    """include_doc extracts content after start marker."""
    content = include_doc("docs/index.md", start_after="## Why?")
    assert "## Why?" not in content  # marker itself excluded
    assert "Single portable binary" in content
    assert "# cosmo-python" not in content  # before the marker


def test_include_doc_with_end_marker() -> None:
    """include_doc extracts content before end marker."""
    content = include_doc("docs/index.md", end_before="## Usage")
    assert "# cosmo-python" in content
    assert "## Why?" in content
    assert "## Usage" not in content


def test_include_doc_heading_level_adjustment() -> None:
    """include_doc adjusts heading levels."""
    content = include_doc("docs/index.md", heading_level=1)
    # # cosmo-python becomes ## cosmo-python
    assert "## cosmo-python" in content
    # ## Why? becomes ### Why?
    assert "### Why?" in content


def test_docs_dir_exists() -> None:
    """DOCS_DIR points to docs/ directory."""
    assert DOCS_DIR.name == "docs"
    assert DOCS_DIR.exists()
    assert (DOCS_DIR / "index.md").exists()
