# Building

<!--[[[cog
import sys; sys.path.insert(0, ".")
from ci import cdx

bom = cdx.load("upstream.cdx.json")
default_python = bom.get_default_component("python")
default_version = default_python.version
cog.outl("```bash")
cog.outl(f"./scripts/build.sh {default_version}  # build specific version")
cog.outl("./scripts/build.sh --all  # build all versions")
cog.outl("```")
]]]-->
```bash
./scripts/build.sh 3.14.2  # build specific version
./scripts/build.sh --all  # build all versions
```
<!--[[[end]]]-->

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORK_DIR` | `./work` | Build working directory (sources, objects) |
| `DIST_DIR` | `./dist` | Output directory for built binaries |
| `COSMO_DIR` | `/tmp/cosmo` | Cosmopolitan toolchain installation path |
| `DEPS_DIR` | `$WORK_DIR/deps` | Compiled dependencies (openssl, libffi, etc.) |
| `SKIP_SIGSTORE` | _(unset)_ | Set to `1` to skip Python sigstore verification |

<!--[[[cog
cog.outl("Example:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh {default_version}")
cog.outl("```")
]]]-->
Example:

```bash
WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh 3.14.2
```
<!--[[[end]]]-->

## Build Process

The build system is organized into phases:

1. **Setup** (`scripts/setup.sh`) — Install Cosmopolitan toolchain
2. **Dependencies** (`scripts/build-deps.sh`) — Build all libraries (OpenSSL, SQLite, etc.)
3. **Python** (`scripts/python/build.sh`) — Download, patch, compile, and package Python

Each dependency has its own build script in `scripts/`:

- `bzip2.sh`, `gdbm.sh`, `libffi.sh`, `ncurses.sh`
- `openssl.sh`, `readline.sh`, `sqlite.sh`
- `xz.sh`, `zstd.sh`, `cacert.sh`

## Caching

The GitHub Actions workflow caches:

- **Dependencies**: Keyed by `upstream.cdx.json` + script hashes
- **Python binaries**: Keyed per-version by `upstream.cdx.json` + python script hashes

This means PR builds populate the cache, and release builds get cache hits.

## Adding a New Python Version

When a new Python minor version is released (e.g., 3.15):

1. Add version to `upstream.cdx.json` with SHA256 and sigstore info
2. Create `scripts/python/patches/3.15/` directory if patches needed
3. Test build: `./scripts/build.sh 3.15.0`
4. Run smoke tests: `./scripts/smoke.sh dist/python-3.15.0-cosmo.com`
5. Update `python.latest` in `upstream.cdx.json`
