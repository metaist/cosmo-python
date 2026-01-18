"""Tests for ci/json_fmt.py - parsed from json_fmt_cases.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ci import json_fmt

# -----------------------------------------------------------------------------
# Literate test cases from markdown
# -----------------------------------------------------------------------------

CASES_FILE = Path(__file__).parent / "json_fmt_cases.md"


def parse_test_cases(md_path: Path) -> list[tuple[str, str, str]]:
    """Parse test cases from markdown file.

    Returns list of (name, input_json, expected_json) tuples.
    """
    content = md_path.read_text()
    cases: list[tuple[str, str, str]] = []

    # Find all ### headings followed by Input/Expected blocks
    pattern = re.compile(
        r"###\s+(.+?)\n"  # Heading
        r"(.*?)"  # Description (captured but not used)
        r"\*\*Input:\*\*\s*\n```json\n(.*?)\n```\s*\n"  # Input block
        r"\*\*Expected:\*\*\s*\n```json\n(.*?)\n```",  # Expected block
        re.DOTALL,
    )

    for match in pattern.finditer(content):
        name = match.group(1).strip()
        input_json = match.group(3).strip()
        expected_json = match.group(4).strip()
        cases.append((name, input_json, expected_json))

    return cases


TEST_CASES = parse_test_cases(CASES_FILE)


@pytest.mark.parametrize(
    ("name", "input_json", "expected"),
    TEST_CASES,
    ids=[case[0] for case in TEST_CASES],
)
def test_format_case(name: str, input_json: str, expected: str) -> None:
    """Test case from json_fmt_cases.md."""
    data = json.loads(input_json)
    result = json_fmt.dumps(data)
    assert result == expected, f"Case '{name}' failed"


def test_cases_file_exists() -> None:
    """Verify test cases file exists and has cases."""
    assert CASES_FILE.exists(), f"Test cases file not found: {CASES_FILE}"
    assert len(TEST_CASES) > 0, "No test cases found in markdown file"


def test_all_cases_produce_valid_json() -> None:
    """All expected outputs should be valid JSON."""
    for name, _input_json, expected in TEST_CASES:
        try:
            json.loads(expected)
        except json.JSONDecodeError as e:
            pytest.fail(f"Case '{name}' expected output is not valid JSON: {e}")


def test_formatter_preserves_data() -> None:
    """Formatting should not change the data, only the representation."""
    for name, input_json, _expected in TEST_CASES:
        data = json.loads(input_json)
        result = json_fmt.dumps(data)
        parsed_result = json.loads(result)
        assert parsed_result == data, f"Case '{name}' changed data during formatting"


# -----------------------------------------------------------------------------
# Additional unit tests for internal functions
# -----------------------------------------------------------------------------


def test_is_hex() -> None:
    """Detect hex strings (32+ chars)."""
    assert json_fmt._is_hex("abcdef0123456789" * 2)  # 32 chars
    assert json_fmt._is_hex("ABCDEF0123456789" * 2)  # uppercase
    assert not json_fmt._is_hex("abc")  # too short
    assert not json_fmt._is_hex("ghijkl0123456789" * 2)  # not hex


def test_is_url() -> None:
    """Detect URLs."""
    assert json_fmt._is_url("https://example.com")
    assert json_fmt._is_url("http://example.com")
    assert not json_fmt._is_url("ftp://example.com")
    assert not json_fmt._is_url("not a url")
