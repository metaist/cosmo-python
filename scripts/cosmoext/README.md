# cosmoext Test Scripts

Scripts for testing C extensions with cosmoext.

## Usage

```bash
# Run all tests (download, build, smoke test, benchmark)
./scripts/cosmoext/test.sh python.com --ext all

# Test specific extensions
./scripts/cosmoext/test.sh python.com --ext markupsafe,xxhash

# Just benchmark (if .cosmoext files already exist)
python.com scripts/cosmoext/benchmark.py

# Just smoke test
./scripts/cosmoext/test.sh python.com --ext markupsafe --no-benchmark
```

## Supported Extensions

| Extension | Type | Notes |
|-----------|------|-------|
| markupsafe | Cython | HTML escaping |
| xxhash | C | Fast hashing |
| ujson | C++ | Fast JSON |
| regex | C | Advanced regex |
| crc32c | C | CRC32C with SSE4.2 |
| msgpack | Cython | MessagePack serialization |

## Files

- `test.sh` - Main entry point (download, build, test, benchmark)
- `benchmark.py` - Python benchmark script (run with python.com)
- `extensions/` - Extension-specific build/test configs
