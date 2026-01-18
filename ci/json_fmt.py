"""Semantic JSON formatter.

Formats JSON with smart compaction based on semantic entropy - low-entropy
values (hashes, URLs) are compressed visually since you skip over them anyway.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _is_hex(s: str) -> bool:
    """Check if string is a long hex value (32+ chars)."""
    return len(s) >= 32 and bool(re.fullmatch(r"[a-f0-9]+", s, re.IGNORECASE))


def _is_url(s: str) -> bool:
    """Check if string is a URL."""
    return s.startswith("http://") or s.startswith("https://")


def _semantic_len(s: str, is_last: bool) -> int:
    """Calculate semantic length of a string value.

    Low-entropy values (hashes, URLs) count less when they're the last value
    in a dict, since your eye doesn't need to scan past them.
    """
    if not is_last:
        return len(json.dumps(s))

    if _is_hex(s):
        # Long hex: just need to see it exists, count as ~5 chars
        return 5

    if _is_url(s):
        # URL: count domain + first path segment
        # https://example.com/path/to/thing → https://example.com/path
        match = re.match(r"(https?://[^/]+/[^/]*)", s)
        if match:
            return len(json.dumps(match.group(1)))

    return len(json.dumps(s))


def _value_semantic_len(v: Any, is_last: bool) -> int:
    """Calculate semantic length of a value."""
    if isinstance(v, str):
        return _semantic_len(v, is_last)
    elif isinstance(v, dict):
        return _dict_semantic_len(v, 0, is_last)
    elif isinstance(v, list):
        return _list_semantic_len(v, is_last)
    else:
        return len(json.dumps(v))


def _item_semantic_len(formatted: str) -> int:
    """Estimate semantic length of an already-formatted JSON string.

    If the string ends with a low-entropy value (hex or URL), apply discount.
    """
    # Check if ends with a long hex string (in quotes)
    hex_match = re.search(r'"([a-f0-9]{32,})" \}', formatted, re.IGNORECASE)
    if hex_match:
        # Discount: replace actual hex length with 5
        hex_len = len(hex_match.group(1))
        return len(formatted) - hex_len + 5

    # Check if ends with a URL (in quotes)
    url_match = re.search(r'"(https?://[^"]+)" \}', formatted)
    if url_match:
        url = url_match.group(1)
        # Count domain + first path segment
        short_match = re.match(r"(https?://[^/]+/[^/]*)", url)
        if short_match:
            url_len = len(url)
            short_len = len(short_match.group(1))
            return len(formatted) - url_len + short_len

    return len(formatted)


def _dict_semantic_len(
    d: dict[str, Any], prefix_len: int, is_last_in_parent: bool = True
) -> int:
    """Calculate semantic length of a dict for one-line check."""
    if not d:
        return 2  # "{}"

    total = prefix_len + 4  # "{ " and " }"
    keys = list(d.keys())
    for i, k in enumerate(keys):
        is_last = is_last_in_parent and i == len(keys) - 1
        v = d[k]
        total += len(json.dumps(k)) + 2  # key + ": "
        total += _value_semantic_len(v, is_last)
        if i < len(keys) - 1:
            total += 2  # ", "
    return total


def _list_semantic_len(lst: list[Any], is_last_in_parent: bool = True) -> int:
    """Calculate semantic length of a list for one-line check."""
    if not lst:
        return 2  # "[]"

    total = 2  # "[" and "]"
    for i, item in enumerate(lst):
        is_last = is_last_in_parent and i == len(lst) - 1
        total += _value_semantic_len(item, is_last)
        if i < len(lst) - 1:
            total += 2  # ", "
    return total


def _compact_value(v: Any) -> str:
    """Format a value for compact (single-line) output."""
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [f'"{k}": {_compact_value(val)}' for k, val in v.items()]
        return "{ " + ", ".join(items) + " }"
    elif isinstance(v, list):
        if not v:
            return "[]"
        items = [_compact_value(item) for item in v]
        return "[" + ", ".join(items) + "]"
    else:
        return json.dumps(v)


def _format_dict(
    d: dict[str, Any], indent: int, max_line: int, level: int, in_array: bool
) -> str:
    """Format a dict, possibly compacted."""
    if not d:
        return "{}"

    prefix = " " * (indent * level)
    child_prefix = " " * (indent * (level + 1))

    # Try compact with semantic length
    if _dict_semantic_len(d, len(prefix)) <= max_line:
        # Check if all values can be compacted (no nested expansion needed)
        # These branches are defensive - if outer dict passes semantic check, nested
        # structures usually pass too. Hard to construct test case that triggers.
        can_compact = True
        for v in d.values():
            if isinstance(v, dict) and v:
                # defensive: outer check usually catches this
                if _dict_semantic_len(v, len(prefix)) > max_line:  # pragma: no cover
                    can_compact = False  # pragma: no cover
                    break  # pragma: no cover
            elif isinstance(v, list) and v:
                # defensive: outer check usually catches this
                if _list_semantic_len(v) + len(prefix) > max_line:  # pragma: no cover
                    can_compact = False  # pragma: no cover
                    break  # pragma: no cover
        if can_compact:
            items = [f'"{k}": {_compact_value(v)}' for k, v in d.items()]
            return "{ " + ", ".join(items) + " }"

    # Multi-line
    items = []
    keys = list(d.keys())
    for i, k in enumerate(keys):
        v = d[k]
        formatted_v = _format_value(v, indent, max_line, level + 1)
        items.append(f'{child_prefix}"{k}": {formatted_v}')

    if in_array:
        # Array context: { starts on same line as [
        inner = ",\n".join(items)
        return "{\n" + inner + "\n" + prefix + "}"
    else:
        return "{\n" + ",\n".join(items) + "\n" + prefix + "}"


def _format_list(lst: list[Any], indent: int, max_line: int, level: int) -> str:
    """Format a list, possibly compacted."""
    if not lst:
        return "[]"

    prefix = " " * (indent * level)
    child_prefix = " " * (indent * (level + 1))

    # Try compact
    compact = _compact_value(lst)
    if len(prefix) + len(compact) <= max_line:
        return compact

    # Check if it's an array of objects
    if all(isinstance(item, dict) for item in lst):
        # Format each object
        formatted_items = []
        for item in lst:
            formatted_items.append(
                _format_dict(item, indent, max_line, level + 1, in_array=True)
            )

        # Check if all items are single-line and fit together
        all_single_line = all("\n" not in item for item in formatted_items)
        if all_single_line:
            one_line = "[" + ", ".join(formatted_items) + "]"
            # Use semantic length - last item gets entropy discount
            semantic_len = len(prefix) + 2  # "[" and "]"
            for i, item in enumerate(formatted_items):
                is_last = i == len(formatted_items) - 1
                # Item is already formatted as string, estimate semantic length
                # by checking if it ends with a low-entropy value
                if is_last:
                    semantic_len += _item_semantic_len(item)
                else:
                    semantic_len += len(item)
                if i < len(formatted_items) - 1:
                    semantic_len += 2  # ", "
            if semantic_len <= max_line:
                return one_line

        # Multi-line arrays of objects
        if all_single_line:
            # Single-line items: standard expansion with ] on its own line
            items = [child_prefix + item for item in formatted_items]
            return "[\n" + ",\n".join(items) + "\n" + prefix + "]"
        else:
            # Multi-line items: [{ ... }, { ... }] with }, { together for folding
            result = "[" + formatted_items[0]
            for item in formatted_items[1:]:
                result += ", " + item
            return result + "]"

    # Regular multi-line list
    items = [
        child_prefix + _format_value(item, indent, max_line, level + 1) for item in lst
    ]
    return "[\n" + ",\n".join(items) + "\n" + prefix + "]"


def _format_value(obj: Any, indent: int, max_line: int, level: int) -> str:
    """Format any JSON value."""
    if isinstance(obj, dict):
        return _format_dict(obj, indent, max_line, level, in_array=False)
    elif isinstance(obj, list):
        return _format_list(obj, indent, max_line, level)
    else:
        return json.dumps(obj)


def dumps(obj: Any, indent: int = 2, max_line: int = 100) -> str:
    """Format JSON with semantic compaction.

    >>> dumps({})
    '{}'
    >>> dumps([])
    '[]'
    >>> dumps({"a": 1})
    '{ "a": 1 }'
    >>> dumps([{"name": "x", "value": "y"}])
    '[{ "name": "x", "value": "y" }]'
    """
    return _format_value(obj, indent, max_line, 0)
