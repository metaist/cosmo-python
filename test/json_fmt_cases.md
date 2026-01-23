<!-- prettier-ignore-file -->

# JSON Formatter Test Cases

This file contains test cases for `ci/json_fmt.py` - a semantic JSON formatter
that produces human-readable output with intelligent line-breaking decisions.

Each test case has an **Input** JSON block and an **Expected** output block.
The test runner parses this file and verifies each case.

## Design Principles

1. **Compact when possible**: Small structures stay on one line
2. **Semantic length**: High-entropy values (hashes, URLs, paths) count less toward line length
3. **Spaces inside braces**: `{ "key": "value" }` not `{"key": "value"}`
4. **Consistent expansion**: When a structure expands, `[` stays with key, `]` on own line
5. **Trailing collapse**: High-entropy value + closing brackets all count as short together

---

## Primitives

Short primitives stay the same.

### Null / Boolean

**Input:**
```json
null
```

**Expected:**
```json
null
```

**Input:**
```json
true
```

**Expected:**
```json
true
```

### Numerics

**Input:**
```json
42
```

**Expected:**
```json
42
```

**Input:**
```json
3.14159
```

**Expected:**
```json
3.14159
```

### Short strings

**Input:**
```json
""
```

**Expected:**
```json
""
```

**Input:**
```json
"hello"
```

**Expected:**
```json
"hello"
```

### Unicode

Unicode characters are preserved as-is (not escaped).

**Input:**
```json
{"greeting": "Hello, 世界! 🌍"}
```

**Expected:**
```json
{ "greeting": "Hello, 世界! 🌍" }
```

### Special characters in strings

Strings with quotes and backslashes stay escaped.

**Input:**
```json
{"path": "C:\\Users\\test", "quote": "He said \"hello\""}
```

**Expected:**
```json
{ "path": "C:\\Users\\test", "quote": "He said \"hello\"" }
```

---

## Empty Structures

### Empty dict

Empty dict is just `{}` with no spaces.

**Input:**
```json
{}
```

**Expected:**
```json
{}
```

### Empty list

Empty list is just `[]` with no spaces.

**Input:**
```json
[]
```

**Expected:**
```json
[]
```

### Nested empty dict

**Input:**
```json
{"outer": {}}
```

**Expected:**
```json
{ "outer": {} }
```

### Nested empty list

**Input:**
```json
{"outer": []}
```

**Expected:**
```json
{ "outer": [] }
```

---

## Compact Structures

### Simple dict

A dict with one key-value pair stays on one line. Note the spaces inside
the braces: `{ "a": 1 }` not `{"a": 1}`.

**Input:**
```json
{"a": 1}
```

**Expected:**
```json
{ "a": 1 }
```

### Simple list

A list of primitives stays compact.

**Input:**
```json
[1, 2, 3]
```

**Expected:**
```json
[1, 2, 3]
```

### Multiple keys

Dict with multiple short keys stays on one line.

**Input:**
```json
{"name": "test", "version": "1.0"}
```

**Expected:**
```json
{ "name": "test", "version": "1.0" }
```

### Nested dict (compact)

When both outer and inner dicts are short, everything stays on one line.

**Input:**
```json
{"license": {"id": "MIT"}}
```

**Expected:**
```json
{ "license": { "id": "MIT" } }
```

### Deeply nested (compact)

Multiple nesting levels stay compact when short enough.

**Input:**
```json
{"a": {"b": {"c": 1}}}
```

**Expected:**
```json
{ "a": { "b": { "c": 1 } } }
```

### List of small objects (compact)

A list of small objects that fits on one line stays compact.

**Input:**
```json
[{"a": 1}, {"b": 2}]
```

**Expected:**
```json
[{ "a": 1 }, { "b": 2 }]
```

### String list (compact)

Short list of strings stays on one line.

**Input:**
```json
["a", "b", "c"]
```

**Expected:**
```json
["a", "b", "c"]
```

---

## Expanded Structures

When structures are too long for one line, they expand. The opening bracket
stays with the key, each item gets its own line, and the closing bracket
goes on its own line.

### String list (expanded)

When a list is too long (>100 chars), expand to one item per line.

**Input:**
```json
["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu"]
```

**Expected:**
```json
[
  "alpha",
  "beta",
  "gamma",
  "delta",
  "epsilon",
  "zeta",
  "eta",
  "theta",
  "iota",
  "kappa",
  "lambda",
  "mu"
]
```

### List of objects (expanded)

When the list is too long but each object is still small, expand to one
object per line.

**Input:**
```json
{"items": [{"name": "alpha", "value": "one"}, {"name": "beta", "value": "two"}, {"name": "gamma", "value": "three"}]}
```

**Expected:**
```json
{
  "items": [
    { "name": "alpha", "value": "one" },
    { "name": "beta", "value": "two" },
    { "name": "gamma", "value": "three" }
  ]
}
```

### Mixed size objects in list

When a list has some large objects and some small ones, large ones expand
but small ones can stay compact.

**Input:**
```json
{"deps": [{"ref": "large@1.0", "dependsOn": ["a@1", "b@2", "c@3", "d@4", "e@5", "f@6", "g@7", "h@8", "i@9", "j@10"]}, {"ref": "small@1.0", "dependsOn": ["x@1"]}, {"ref": "tiny@1.0", "dependsOn": ["y@1"]}]}
```

**Expected:**
```json
{
  "deps": [
    {
      "ref": "large@1.0",
      "dependsOn": ["a@1", "b@2", "c@3", "d@4", "e@5", "f@6", "g@7", "h@8", "i@9", "j@10"]
    },
    { "ref": "small@1.0", "dependsOn": ["x@1"] },
    { "ref": "tiny@1.0", "dependsOn": ["y@1"] }
  ]
}
```

### Multi-line objects in list

When objects need multiple lines, each object expands independently.

**Input:**
```json
[{"name": "first", "description": "This is a much longer description that will cause the object to expand"}, {"name": "second", "description": "Another lengthy description forcing multi-line formatting here"}]
```

**Expected:**
```json
[
  {
    "name": "first",
    "description": "This is a much longer description that will cause the object to expand"
  }, {
    "name": "second",
    "description": "Another lengthy description forcing multi-line formatting here"
  }
]
```

### Compact object after expanded

When a compact object follows an expanded object, it goes on its own line.

**Input:**
```json
[{"name": "first", "description": "This is a much longer description that will cause the object to expand"}, {"name": "second"}]
```

**Expected:**
```json
[
  {
    "name": "first",
    "description": "This is a much longer description that will cause the object to expand"
  },
  { "name": "second" }
]
```

### Expanded object after compact

When an expanded object follows a compact object, it also goes on its own line.

**Input:**
```json
[{"name": "first"}, {"name": "second", "description": "This is a much longer description that will cause the object to expand"}]
```

**Expected:**
```json
[
  { "name": "first" },
  {
    "name": "second",
    "description": "This is a much longer description that will cause the object to expand"
  }
]
```

---

## High-Entropy Values

The formatter recognizes "high-entropy" values - strings that are long but
predictable (hashes, URLs, file paths). These count as shorter (~5 chars)
for line-length calculations because humans scan/skip them.

When a high-entropy value is at the end of a structure, the closing brackets
also collapse into the count. So `{ "hash": "abc...xyz" }]]]` counts as
roughly `{ "hash": ##### }]]]` ≈ 20 chars regardless of hash length.

### SHA-256 hash

64-character hex hash counts as ~5 characters.

**Input:**
```json
{"alg": "SHA-256", "content": "a078fb2d7a216071ebbe2e34b5f5355dd6b6e9b0cd1bacc4a41c63990c5a0eec"}
```

**Expected:**
```json
{ "alg": "SHA-256", "content": "a078fb2d7a216071ebbe2e34b5f5355dd6b6e9b0cd1bacc4a41c63990c5a0eec" }
```

### URL

URLs are recognized by `http://` or `https://` prefix.

**Input:**
```json
{"type": "distribution", "url": "https://www.python.org/ftp/python/3.10.19/Python-3.10.19.tgz"}
```

**Expected:**
```json
{ "type": "distribution", "url": "https://www.python.org/ftp/python/3.10.19/Python-3.10.19.tgz" }
```

### License with URL

Nested structures with URLs also benefit from semantic length.

**Input:**
```json
{"license": {"id": "PSF-2.0", "url": "https://docs.python.org/3/license.html"}}
```

**Expected:**
```json
{ "license": { "id": "PSF-2.0", "url": "https://docs.python.org/3/license.html" } }
```

### Deeply nested with hash

High-entropy value plus all closing brackets count as short together.
This 55-bracket structure stays on one line because the hash + trailing
`}]]]...]]]` all collapse.

**Input:**
```json
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{"a": "a078fb2d7a216071ebbe2e34b5f5355dd6b6e9b0cd1bacc4a41c63990c5a0eec"}]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

**Expected:**
```json
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{ "a": "a078fb2d7a216071ebbe2e34b5f5355dd6b6e9b0cd1bacc4a41c63990c5a0eec" }]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

---

## Real-World CycloneDX Examples

### CycloneDX hash entry

**Input:**
```json
{"hashes": [{"alg": "SHA-256", "content": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269"}]}
```

**Expected:**
```json
{ "hashes": [{ "alg": "SHA-256", "content": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269" }] }
```

### CycloneDX license entry

**Input:**
```json
{"licenses": [{"license": {"id": "MIT", "url": "https://github.com/libffi/libffi/blob/master/LICENSE"}}]}
```

**Expected:**
```json
{ "licenses": [{ "license": { "id": "MIT", "url": "https://github.com/libffi/libffi/blob/master/LICENSE" } }] }
```

### CycloneDX external reference

**Input:**
```json
{"externalReferences": [{"type": "distribution", "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz"}]}
```

**Expected:**
```json
{ "externalReferences": [{ "type": "distribution", "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz" }] }
```

### CycloneDX properties (short)

**Input:**
```json
{"properties": [{"name": "cosmo:gpg", "value": "ABC123"}]}
```

**Expected:**
```json
{ "properties": [{ "name": "cosmo:gpg", "value": "ABC123" }] }
```

### CycloneDX properties (multiple)

Multiple properties expand to one per line.

**Input:**
```json
{"properties": [{"name": "cosmo:eol", "value": "2030-10"}, {"name": "cosmo:status", "value": "bugfix"}, {"name": "cosmo:sigstore:identity", "value": "hugo@python.org"}, {"name": "cosmo:sigstore:issuer", "value": "https://github.com/login/oauth"}]}
```

**Expected:**
```json
{
  "properties": [
    { "name": "cosmo:eol", "value": "2030-10" },
    { "name": "cosmo:status", "value": "bugfix" },
    { "name": "cosmo:sigstore:identity", "value": "hugo@python.org" },
    { "name": "cosmo:sigstore:issuer", "value": "https://github.com/login/oauth" }
  ]
}
```

### CycloneDX component (full)

**Input:**
```json
{"type": "library", "bom-ref": "bzip2@1.0.8", "name": "bzip2", "version": "1.0.8", "hashes": [{"alg": "SHA-256", "content": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269"}], "licenses": [{"license": {"id": "bzip2-1.0.6", "url": "https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE"}}], "externalReferences": [{"type": "distribution", "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz"}], "properties": [{"name": "cosmo:gpg", "value": "BA5473A2B0587B07FB27CF2D216094DFD0CB81EF"}]}
```

**Expected:**
```json
{
  "type": "library",
  "bom-ref": "bzip2@1.0.8",
  "name": "bzip2",
  "version": "1.0.8",
  "hashes": [{ "alg": "SHA-256", "content": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269" }],
  "licenses": [{ "license": { "id": "bzip2-1.0.6", "url": "https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE" } }],
  "externalReferences": [{ "type": "distribution", "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz" }],
  "properties": [{ "name": "cosmo:gpg", "value": "BA5473A2B0587B07FB27CF2D216094DFD0CB81EF" }]
}
```

### CycloneDX dependencies (mixed sizes)

Large entries expand, small entries stay compact.

**Input:**
```json
{"dependencies": [{"ref": "cosmo-python@3.14.2", "dependsOn": ["bzip2@1.0.8", "cacert@2025-12-02", "cosmocc@4.0.2", "gdbm@1.26", "libffi@3.5.2", "ncurses@6.6", "openssl@3.5.4", "python@3.14.2", "readline@8.3", "sqlite@3.51.2", "xz@5.8.2"]}, {"ref": "openssl@3.5.4", "dependsOn": ["cacert@2025-12-02"]}, {"ref": "readline@8.3", "dependsOn": ["ncurses@6.6"]}]}
```

**Expected:**
```json
{
  "dependencies": [
    {
      "ref": "cosmo-python@3.14.2",
      "dependsOn": [
        "bzip2@1.0.8",
        "cacert@2025-12-02",
        "cosmocc@4.0.2",
        "gdbm@1.26",
        "libffi@3.5.2",
        "ncurses@6.6",
        "openssl@3.5.4",
        "python@3.14.2",
        "readline@8.3",
        "sqlite@3.51.2",
        "xz@5.8.2"
      ]
    },
    { "ref": "openssl@3.5.4", "dependsOn": ["cacert@2025-12-02"] },
    { "ref": "readline@8.3", "dependsOn": ["ncurses@6.6"] }
  ]
}
```

### Metadata properties

**Input:**
```json
{"metadata": {"properties": [{"name": "cosmo:default:python", "value": "3.14.2"}, {"name": "cosmo:latest:python:3.10", "value": "3.10.19"}, {"name": "cosmo:latest:python:3.11", "value": "3.11.14"}]}}
```

**Expected:**
```json
{
  "metadata": {
    "properties": [
      { "name": "cosmo:default:python", "value": "3.14.2" },
      { "name": "cosmo:latest:python:3.10", "value": "3.10.19" },
      { "name": "cosmo:latest:python:3.11", "value": "3.11.14" }
    ]
  }
}
```
