"""Semantic JSON formatter.

Formats JSON with smart compaction based on semantic entropy - high-entropy
values (hashes, URLs) are treated as shorter since you scan/skip over them.
"""

from __future__ import annotations

import json
import re
from typing import Any

# High-entropy values count as this many chars for line-length decisions
HIGH_ENTROPY_LEN = 5


def _is_hex(s: str) -> bool:
    """Check if string is a long hex value (32+ chars)."""
    return len(s) >= 32 and bool(re.fullmatch(r"[a-f0-9]+", s, re.IGNORECASE))


def _is_url(s: str) -> bool:
    """Check if string is a URL."""
    return s.startswith("http://") or s.startswith("https://")


def _semantic_compact_len(compact: str) -> int:
    """Calculate semantic length of a compact JSON string.

    If the string ends with a high-entropy value (hash/URL) followed only by
    closing brackets/braces, those trailing chars collapse to nearly nothing.
    This handles deeply nested structures like [[[{ "a": "hash..." }]]].
    """
    # Match: hex hash at end, followed only by closing punctuation
    match = re.search(r'"([a-f0-9]{32,})"\s*[\s}\]]*$', compact, re.IGNORECASE)
    if match:
        # Everything before the hash + small constant for hash
        return match.start(1) + HIGH_ENTROPY_LEN

    # Match: URL at end, followed only by closing punctuation
    match = re.search(r'"(https?://[^"]+)"\s*[\s}\]]*$', compact)
    if match:
        return match.start(1) + HIGH_ENTROPY_LEN

    return len(compact)


def _json_str(v: Any) -> str:
    """Serialize value to JSON, preserving unicode."""
    return json.dumps(v, ensure_ascii=False)


def _compact_value(v: Any) -> str:
    """Format a value for compact (single-line) output."""
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [f"{_json_str(k)}: {_compact_value(val)}" for k, val in v.items()]
        return "{ " + ", ".join(items) + " }"
    elif isinstance(v, list):
        if not v:
            return "[]"
        items = [_compact_value(item) for item in v]
        return "[" + ", ".join(items) + "]"
    else:
        return _json_str(v)


def _format_dict(d: dict[str, Any], indent: int, max_line: int, level: int) -> str:
    """Format a dict, possibly compacted."""
    if not d:
        return "{}"

    prefix = " " * (indent * level)

    # Try compact - format first, then check semantic length
    compact = _compact_value(d)
    if len(prefix) + _semantic_compact_len(compact) <= max_line:
        return compact

    # Multi-line
    child_prefix = " " * (indent * (level + 1))
    items = []
    for k, v in d.items():
        formatted_v = _format_value(v, indent, max_line, level + 1)
        items.append(f"{child_prefix}{_json_str(k)}: {formatted_v}")

    return "{\n" + ",\n".join(items) + "\n" + prefix + "}"


def _format_list(lst: list[Any], indent: int, max_line: int, level: int) -> str:
    """Format a list, possibly compacted."""
    if not lst:
        return "[]"

    prefix = " " * (indent * level)
    child_prefix = " " * (indent * (level + 1))

    # Try compact - format first, then check semantic length
    compact = _compact_value(lst)
    if len(prefix) + _semantic_compact_len(compact) <= max_line:
        return compact

    # Check if it's an array of objects
    if all(isinstance(item, dict) for item in lst):
        return _format_list_of_dicts(lst, indent, max_line, level, prefix, child_prefix)

    # Regular multi-line list (primitives or mixed)
    items = [child_prefix + _format_value(item, indent, max_line, level + 1) for item in lst]
    return "[\n" + ",\n".join(items) + "\n" + prefix + "]"


def _format_list_of_dicts(
    lst: list[dict[str, Any]],
    indent: int,
    max_line: int,
    level: int,
    prefix: str,
    child_prefix: str,
) -> str:
    """Format a list of dicts with smart expansion."""
    # Format each dict independently - some may be compact, some expanded
    formatted_items: list[str] = []
    for item in lst:
        # Check if this dict can be compact
        compact = _compact_value(item)
        if len(child_prefix) + _semantic_compact_len(compact) <= max_line:
            formatted_items.append(compact)
        else:
            # Need multi-line for this dict
            formatted_items.append(_format_dict(item, indent, max_line, level + 1))

    # Check if ALL items are single-line (compact)
    all_single_line = all("\n" not in s for s in formatted_items)

    if all_single_line:
        # Try fitting all on one line
        one_line = "[" + ", ".join(formatted_items) + "]"
        if len(prefix) + _semantic_compact_len(one_line) <= max_line:
            return one_line
        # Standard expansion: each item on own line, ] on own line
        items = [child_prefix + item for item in formatted_items]
        return "[\n" + ",\n".join(items) + "\n" + prefix + "]"

    # Mixed or all multi-line: use }, { continuation for multi-line items
    # but standard lines for single-line items
    result_lines: list[str] = ["["]
    prev_was_multiline = False

    for i, formatted in enumerate(formatted_items):
        is_multiline = "\n" in formatted
        is_last = i == len(formatted_items) - 1
        comma = "" if is_last else ","

        if is_multiline:
            if i == 0:
                # First item, multi-line: [ then { on next conceptual line
                # but we use }, { style so start is [\n  {\n
                result_lines.append(child_prefix + formatted + comma)
            elif prev_was_multiline:
                # }, { continuation
                # Remove last line's comma if present, replace with }, {
                last_line = result_lines[-1]
                if last_line.endswith(","):
                    result_lines[-1] = last_line[:-1]
                result_lines[-1] += ", " + formatted + comma
            else:
                # Previous was single-line, this is multi-line
                result_lines.append(child_prefix + formatted + comma)
        else:
            # Single-line item
            if prev_was_multiline:
                # After multi-line, single-line goes on own line
                result_lines.append(child_prefix + formatted + comma)
            else:
                # Single-line after single-line (or first)
                result_lines.append(child_prefix + formatted + comma)

        prev_was_multiline = is_multiline

    result_lines.append(prefix + "]")
    return "\n".join(result_lines)


def _format_value(obj: Any, indent: int, max_line: int, level: int) -> str:
    """Format any JSON value."""
    if isinstance(obj, dict):
        return _format_dict(obj, indent, max_line, level)
    elif isinstance(obj, list):
        return _format_list(obj, indent, max_line, level)
    else:
        return _json_str(obj)


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
