#!/usr/bin/env python3
"""Benchmark cosmoext extensions.

Usage:
    python.com scripts/benchmark-cosmoext.py [extension...]
    
Examples:
    python.com scripts/benchmark-cosmoext.py              # Run all
    python.com scripts/benchmark-cosmoext.py markupsafe   # Run one
    python.com scripts/benchmark-cosmoext.py xxhash ujson # Run several
"""

import sys
import time
import platform

def benchmark(name, func, iterations=100000):
    """Run a benchmark and return calls/sec."""
    start = time.time()
    for _ in range(iterations):
        func()
    elapsed = time.time() - start
    rate = iterations / elapsed
    return rate, elapsed

def format_rate(rate, unit="calls/sec"):
    """Format rate with appropriate suffix."""
    if rate >= 1e9:
        return f"{rate/1e9:.2f}G {unit}"
    elif rate >= 1e6:
        return f"{rate/1e6:.2f}M {unit}"
    elif rate >= 1e3:
        return f"{rate/1e3:.1f}K {unit}"
    else:
        return f"{rate:.0f} {unit}"

def test_markupsafe(path):
    """Benchmark markupsafe HTML escaping."""
    import _cosmoext
    ms = _cosmoext.load(path)
    
    test_str = '<div class="foo">Hello & goodbye</div>'
    rate, _ = benchmark("escape", lambda: ms._escape_inner(test_str))
    print(f"  _escape_inner: {format_rate(rate)}")
    return True

def test_xxhash(path):
    """Benchmark xxhash hashing."""
    import _cosmoext
    xxhash = _cosmoext.load(path)
    
    data = b'x' * 1000
    rate, elapsed = benchmark("xxh64", lambda: xxhash.xxh64(data))
    mb_per_sec = (100000 * 1000) / elapsed / 1e6
    print(f"  xxh64 (1KB): {format_rate(mb_per_sec, 'MB/s')}")
    
    data_large = b'x' * 10000
    rate, elapsed = benchmark("xxh64_10k", lambda: xxhash.xxh64(data_large), iterations=10000)
    mb_per_sec = (10000 * 10000) / elapsed / 1e6
    print(f"  xxh64 (10KB): {format_rate(mb_per_sec, 'MB/s')}")
    return True

def test_ujson(path):
    """Benchmark ujson JSON encoding/decoding."""
    import _cosmoext
    ujson = _cosmoext.load(path)
    
    # Simple encode
    rate, _ = benchmark("dumps_int", lambda: ujson.dumps(12345))
    print(f"  dumps(int): {format_rate(rate)}")
    
    # Complex encode
    data = {'key': 'value', 'number': 12345, 'float': 3.14159, 'array': [1,2,3,4,5]}
    rate, _ = benchmark("dumps_dict", lambda: ujson.dumps(data))
    print(f"  dumps(dict): {format_rate(rate)}")
    
    # Decode
    json_str = '{"key":"value","number":12345,"float":3.14159,"array":[1,2,3,4,5]}'
    rate, _ = benchmark("loads", lambda: ujson.loads(json_str))
    print(f"  loads(dict): {format_rate(rate)}")
    return True

def test_regex(path):
    """Benchmark regex module (basic load test)."""
    import _cosmoext
    regex = _cosmoext.load(path)
    
    # regex._regex is low-level, just verify it loads
    print(f"  module loaded: {regex.copyright.strip()}")
    print(f"  functions: {len([x for x in dir(regex) if not x.startswith('_')])}")
    return True

def test_crc32c(path):
    """Benchmark crc32c checksums."""
    import _cosmoext
    crc = _cosmoext.load(path)
    
    data = b'x' * 1000
    rate, elapsed = benchmark("crc32c", lambda: crc.crc32c(data))
    mb_per_sec = (100000 * 1000) / elapsed / 1e6
    print(f"  crc32c (1KB): {format_rate(mb_per_sec, 'MB/s')}")
    return True

EXTENSIONS = {
    'markupsafe': ('markupsafe.cosmoext', test_markupsafe),
    'xxhash': ('xxhash.cosmoext', test_xxhash),
    'ujson': ('ujson.cosmoext', test_ujson),
    'regex': ('regex.cosmoext', test_regex),
    'crc32c': ('crc32c.cosmoext', test_crc32c),
}

def main():
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    print()
    
    # Determine which extensions to test
    if len(sys.argv) > 1:
        to_test = sys.argv[1:]
    else:
        to_test = list(EXTENSIONS.keys())
    
    # Find extension files
    import os
    search_paths = ['/tmp', '.', 'dist', 'experiments/cosmoext/real_extensions']
    
    results = {}
    for name in to_test:
        if name not in EXTENSIONS:
            print(f"Unknown extension: {name}")
            continue
            
        filename, test_func = EXTENSIONS[name]
        
        # Find the file
        path = None
        for search in search_paths:
            candidate = os.path.join(search, filename)
            if os.path.exists(candidate):
                path = candidate
                break
            # Also check subdirectories
            candidate = os.path.join(search, name, filename)
            if os.path.exists(candidate):
                path = candidate
                break
        
        if not path:
            print(f"{name}: NOT FOUND (searched {search_paths})")
            results[name] = 'not found'
            continue
        
        print(f"{name}: {path}")
        try:
            success = test_func(path)
            results[name] = 'pass' if success else 'fail'
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = 'error'
        print()
    
    # Summary
    print("=" * 40)
    print("Summary:")
    for name, status in results.items():
        symbol = {'pass': '✓', 'fail': '✗', 'error': '!', 'not found': '?'}[status]
        print(f"  {symbol} {name}: {status}")

if __name__ == '__main__':
    main()
