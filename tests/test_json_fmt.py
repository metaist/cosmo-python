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


def test_is_skippable() -> None:
    """Detect visual blobs humans skip over."""
    # URLs - always skippable
    assert json_fmt._is_skippable("https://example.com/path/to/resource")
    assert json_fmt._is_skippable("http://example.com/path/to/resource")
    # Hashes (long, no spaces)
    assert json_fmt._is_skippable("abcdef0123456789" * 2)
    assert json_fmt._is_skippable("ABCDEF0123456789" * 2)
    # File paths (long, no spaces)
    assert json_fmt._is_skippable("/home/user/path/to/some/file.tar.gz")
    # Repeated chars (long blob)
    assert json_fmt._is_skippable("a" * 40)
    # Short strings - always readable
    assert not json_fmt._is_skippable("abc")
    assert not json_fmt._is_skippable("short")
    assert not json_fmt._is_skippable("python")
    assert not json_fmt._is_skippable("3.14.2")
    # Long with spaces = prose = readable
    assert not json_fmt._is_skippable("This is a longer description with varied chars")


# -----------------------------------------------------------------------------
# CLI tests
# -----------------------------------------------------------------------------


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --help shows usage."""
    result = json_fmt.main(["--help"])
    assert result == 0
    captured = capsys.readouterr()
    assert "Usage:" in captured.out


def test_main_stdin_stdout(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI reads stdin and writes formatted output to stdout."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('{"b":1,"a":2}'))
    result = json_fmt.main(["-"])
    assert result == 0
    captured = capsys.readouterr()
    assert captured.out == '{ "b": 1, "a": 2 }\n'


def test_main_format_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI formats a file in place."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{"b":1,"a":2}')

    result = json_fmt.main([str(test_file)])
    assert result == 0

    assert test_file.read_text() == '{ "b": 1, "a": 2 }\n'
    captured = capsys.readouterr()
    assert "formatted" in captured.err


def test_main_file_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI reports unchanged when file is already formatted."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{ "a": 1 }\n')

    result = json_fmt.main([str(test_file)])
    assert result == 0

    captured = capsys.readouterr()
    assert "unchanged" in captured.err


def test_main_check_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --check returns 0 when file is formatted."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{ "a": 1 }\n')

    result = json_fmt.main(["--check", str(test_file)])
    assert result == 0

    captured = capsys.readouterr()
    assert "ok" in captured.err


def test_main_check_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --check returns 1 when file is not formatted."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{"a":1}')

    result = json_fmt.main(["--check", str(test_file)])
    assert result == 1

    captured = capsys.readouterr()
    assert "not formatted" in captured.err
    # File should not be modified
    assert test_file.read_text() == '{"a":1}'


def test_main_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI handles invalid JSON gracefully."""
    test_file = tmp_path / "bad.json"
    test_file.write_text('{invalid}')

    result = json_fmt.main([str(test_file)])
    assert result == 1

    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err


def test_main_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI handles missing file gracefully."""
    result = json_fmt.main(["/nonexistent/file.json"])
    assert result == 1

    captured = capsys.readouterr()
    assert "No such file" in captured.err or "nonexistent" in captured.err


def test_main_multiple_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI processes multiple files."""
    file1 = tmp_path / "a.json"
    file2 = tmp_path / "b.json"
    file1.write_text('{"x":1}')
    file2.write_text('{"y":2}')

    result = json_fmt.main([str(file1), str(file2)])
    assert result == 0

    assert file1.read_text() == '{ "x": 1 }\n'
    assert file2.read_text() == '{ "y": 2 }\n'


def test_main_no_args_reads_stdin(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI with no args reads from stdin."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('{"z":3}'))
    result = json_fmt.main([])
    assert result == 0
    captured = capsys.readouterr()
    assert captured.out == '{ "z": 3 }\n'


def test_main_check_stdin(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI --check with stdin just formats (can't check)."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('{"a":1}'))
    result = json_fmt.main(["--check", "-"])
    assert result == 0
    captured = capsys.readouterr()
    assert captured.out == '{ "a": 1 }\n'


def test_main_default_args(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI uses sys.argv when args=None."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO('{"q":9}'))
    monkeypatch.setattr("sys.argv", ["json_fmt", "-"])
    result = json_fmt.main(None)
    assert result == 0
    captured = capsys.readouterr()
    assert captured.out == '{ "q": 9 }\n'
