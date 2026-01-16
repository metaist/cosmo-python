"""Tests for ci/json_fmt.py - semantic JSON formatter."""

from ci import json_fmt


def test_empty_dict() -> None:
    """Empty dict returns {}."""
    assert json_fmt.dumps({}) == "{}"


def test_empty_list() -> None:
    """Empty list returns []."""
    assert json_fmt.dumps([]) == "[]"


def test_simple_dict() -> None:
    """Simple dict with spaces inside braces."""
    assert json_fmt.dumps({"a": 1}) == '{ "a": 1 }'


def test_simple_list() -> None:
    """Simple list stays compact."""
    assert json_fmt.dumps([1, 2, 3]) == "[1, 2, 3]"


def test_list_of_simple_dicts() -> None:
    """List of simple dicts stays compact."""
    result = json_fmt.dumps([{"name": "x", "value": "y"}])
    assert result == '[{ "name": "x", "value": "y" }]'


def test_hash_on_one_line() -> None:
    """SHA-256 hash (low entropy) stays on one line."""
    data = {
        "alg": "SHA-256",
        "content": "a078fb2d7a216071ebbe2e34b5f5355dd6b6e9b0cd1bacc4a41c63990c5a0eec",
    }
    result = json_fmt.dumps(data)
    assert "\n" not in result
    assert "SHA-256" in result


def test_url_on_one_line() -> None:
    """URL (low entropy) stays on one line."""
    data = {
        "type": "distribution",
        "url": "https://www.python.org/ftp/python/3.10.19/Python-3.10.19.tgz",
    }
    result = json_fmt.dumps(data)
    assert "\n" not in result


def test_nested_dict_compact() -> None:
    """Nested dict stays compact when short enough."""
    data = {"license": {"id": "MIT", "url": "https://example.com/license"}}
    result = json_fmt.dumps(data)
    assert "\n" not in result
    assert "{ " in result  # spaces inside braces


def test_array_of_objects_expanded_single_line_items() -> None:
    """Array of single-line objects uses standard expansion with ] on own line."""
    data = {
        "components": [
            {"name": "python", "version": "3.13.11", "hashes": [{"alg": "SHA-256", "content": "abc" * 20}]},
            {"name": "cosmocc", "version": "4.0.2", "hashes": [{"alg": "SHA-256", "content": "def" * 20}]},
        ]
    }
    result = json_fmt.dumps(data)
    # Check [ on its own conceptual line (after key)
    assert '"components": [\n' in result
    # Check ] on its own line
    assert "}\n  ]" in result


def test_array_of_objects_expanded_multi_line_items() -> None:
    """Array of multi-line objects with }, { formatting."""
    data = [
        {"type": "app", "name": "python", "version": "3.13.11", "hashes": [{"alg": "SHA-256", "content": "a" * 64}]},
        {"type": "app", "name": "cosmocc", "version": "4.0.2", "hashes": [{"alg": "SHA-256", "content": "b" * 64}]},
    ]
    result = json_fmt.dumps(data)
    # Check }, { together (multi-line items)
    assert "}, {" in result


def test_properties_one_per_line_when_too_long() -> None:
    """Properties array expands to one per line when too many."""
    data = {
        "properties": [
            {"name": "a", "value": "1"},
            {"name": "b", "value": "2"},
            {"name": "c", "value": "3"},
            {"name": "d", "value": "4"},
            {"name": "e", "value": "5"},
        ]
    }
    result = json_fmt.dumps(data, max_line=60)
    lines = result.split("\n")
    # Should expand with each property on its own line
    assert len(lines) > 3


def test_is_hex() -> None:
    """Detect hex strings."""
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


def test_semantic_len_hex_last() -> None:
    """Hex as last value counts as ~5 chars."""
    long_hex = "a" * 64
    assert json_fmt._semantic_len(long_hex, is_last=True) == 5
    # Not last - counts fully
    assert json_fmt._semantic_len(long_hex, is_last=False) == len(f'"{long_hex}"')


def test_semantic_len_url_last() -> None:
    """URL as last value counts as domain + first path segment."""
    url = "https://example.com/path/to/file.tar.gz"
    short_len = json_fmt._semantic_len(url, is_last=True)
    full_len = json_fmt._semantic_len(url, is_last=False)
    assert short_len < full_len
    # Should be around len of "https://example.com/path"
    assert short_len < 35


def test_valid_json_output() -> None:
    """Output is valid JSON."""
    import json

    data = {
        "nested": {"a": 1, "b": [1, 2, 3]},
        "list": [{"x": "y"}, {"z": "w"}],
    }
    result = json_fmt.dumps(data)
    # Should parse without error
    parsed = json.loads(result)
    assert parsed == data


def test_multi_line_dict_in_array() -> None:
    """Dict that must expand in array context."""
    data = [
        {
            "type": "application",
            "bom-ref": "python@3.13.11",
            "name": "python",
            "version": "3.13.11",
            "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
        }
    ]
    result = json_fmt.dumps(data)
    # Should have [{ on first line
    assert result.startswith("[{")
    # Should have }] at end
    assert result.rstrip().endswith("}]")


def test_list_of_strings_expanded() -> None:
    """Long list of strings expands properly."""
    data = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
    result = json_fmt.dumps(data, max_line=30)
    assert "\n" in result


def test_empty_nested_dict() -> None:
    """Empty nested dict in compact output."""
    data = {"outer": {}}
    result = json_fmt.dumps(data)
    assert result == '{ "outer": {} }'


def test_empty_nested_list() -> None:
    """Empty nested list in compact output."""
    data = {"outer": []}
    result = json_fmt.dumps(data)
    assert result == '{ "outer": [] }'


def test_dict_with_nested_list_too_long() -> None:
    """Dict expands when nested list is too long."""
    data = {"key": ["a" * 30, "b" * 30]}
    result = json_fmt.dumps(data, max_line=50)
    assert "\n" in result


def test_dict_with_nested_dict_too_long() -> None:
    """Dict expands when nested dict is too long."""
    data = {"outer": {"inner": "x" * 80}}  # x is not hex
    result = json_fmt.dumps(data, max_line=50)
    assert "\n" in result


def test_empty_dict_semantic_len() -> None:
    """Empty dict has semantic length of 2."""
    assert json_fmt._dict_semantic_len({}, 0) == 2


def test_empty_list_semantic_len() -> None:
    """Empty list has semantic length of 2."""
    assert json_fmt._list_semantic_len([]) == 2


def test_all_single_line_array_fits() -> None:
    """Array of single-line objects fits on one line."""
    data = [{"a": 1}, {"b": 2}]
    result = json_fmt.dumps(data)
    assert "\n" not in result
    assert result == '[{ "a": 1 }, { "b": 2 }]'


def test_nested_dict_forces_expansion() -> None:
    """Dict with too-long nested dict forces expansion."""
    # Nested dict is too long when checked for compaction
    data = {"key": {"nested": "x" * 100}}
    result = json_fmt.dumps(data, max_line=50)
    assert "\n" in result


def test_nested_list_forces_expansion() -> None:
    """Dict with too-long nested list forces expansion."""
    data = {"key": ["x" * 50, "y" * 50]}
    result = json_fmt.dumps(data, max_line=50)
    assert "\n" in result


def test_multi_line_dict_inside_array() -> None:
    """Multi-line dict item in array gets }, { formatting."""
    # Force the inner dict to be multi-line by making it long enough
    data = [
        {"a": 1, "b": 2, "c": 3, "d": 4, "e": "x" * 50},
        {"a": 1, "b": 2, "c": 3, "d": 4, "e": "y" * 50},
    ]
    result = json_fmt.dumps(data, max_line=50)
    # Should have }, { on same line
    assert "}, {" in result
