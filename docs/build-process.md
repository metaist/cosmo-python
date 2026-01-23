# Build Process Internals

This document explains how cosmo-python builds Python using the Cosmopolitan toolchain.
For instructions on how to build, see [Building](building.md).

## Source of Truth: upstream.cdx.json

Everything starts with `upstream.cdx.json`, a [CycloneDX](https://cyclonedx.org/) Bill of Materials that defines:

- **Default versions** of all components (Python, OpenSSL, etc.)
- **Download URLs** and checksums for each component
- **Dependency graph** between components
- **Signature verification** info (GPG keys, Sigstore identities)

The `ci/cdx.py` CLI reads this file to determine what to build and in what order.

## Build Phases

```
┌─────────────────────────────────────────────────────────────────┐
│ scripts/build.sh                                                │
│   Main orchestrator - runs all phases in order                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐    ┌───────────────────┐    ┌───────────────┐
│ Phase 1: Deps │    │ Phase 2: Python   │    │ Phase 3: Test │
│ build-deps.sh │    │ python/build.sh   │    │ smoke.sh      │
└───────────────┘    └───────────────────┘    └───────────────┘
```

### Phase 1: Dependencies (`scripts/build-deps.sh`)

Builds dependencies in topological order (from `upstream.cdx.json`):

1. **cosmocc.sh** - Downloads Cosmopolitan toolchain
2. **Library scripts** - Each builds a static library:
   - `bzip2.sh`, `xz.sh`, `zstd.sh` (compression)
   - `openssl.sh` (TLS/crypto)
   - `ncurses.sh`, `readline.sh` (terminal)
   - `sqlite.sh`, `gdbm.sh` (databases)
   - `libffi.sh` (foreign function interface)

All libraries are compiled with `cosmocc` to produce portable static archives.

### Phase 2: Python (`scripts/python/build.sh`)

Three sub-phases for each Python version:

```
┌─────────────────────────────────────────────────────────────────┐
│ scripts/python/build.sh <version>                               │
└───────────────────────────────┬─────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐    ┌───────────────────┐    ┌───────────────┐
│ download.sh   │    │ compile.sh        │    │ package.sh    │
│ - Fetch source│    │ - Configure       │    │ - Add stdlib  │
│ - Verify hash │    │ - Apply patches   │    │ - Create ZIP  │
│ - Check sig   │    │ - Patch Makefile  │    │ - Final .com  │
│               │    │ - Build           │    │               │
└───────────────┘    └───────────────────┘    └───────────────┘
```

#### Download (`download.sh`)

1. Downloads Python source tarball (URL from `upstream.cdx.json`)
2. Verifies SHA-256 checksum
3. Verifies Sigstore signature (unless `SKIP_SIGSTORE=1`)
4. Extracts to `work/Python-X.Y.Z/`

#### Compile (`compile.sh`)

This is where most of the complexity lives:

```
┌─────────────────────────────────────────────────────────────────┐
│ compile.sh                                                      │
├─────────────────────────────────────────────────────────────────┤
│ 1. Apply source patches                                         │
│    - scripts/python/all/*.patch (all versions)                  │
│    - scripts/python/3.XX/*.patch (version-specific)             │
├─────────────────────────────────────────────────────────────────┤
│ 2. Run ./configure                                              │
│    - Sets up for static build (--disable-shared)                │
│    - Points to our static libraries (OPENSSL_LIBS, etc.)        │
│    - Generates Makefile                                         │
├─────────────────────────────────────────────────────────────────┤
│ 3. Patch Makefile (post-configure fixes)                        │
│    - Remove -framework flags (macOS-specific)                   │
│    - Remove -Wl,-stack_size (macOS linker syntax)               │
│    - Remove -latomic (Cosmopolitan has built-in atomics)        │
│    - Remove _scproxy module (macOS-only)                        │
│    - Fix _decimal CFLAGS (cross-compile detection issue)        │
├─────────────────────────────────────────────────────────────────┤
│ 4. Run make                                                     │
│    - Compiles with cosmocc (produces fat binary)                │
│    - Output: python.com (runs on Linux, macOS, Windows, etc.)   │
└─────────────────────────────────────────────────────────────────┘
```

#### Package (`package.sh`)

1. Creates stdlib ZIP from `Lib/` directory
2. Appends ZIP to the binary (Cosmopolitan reads it at runtime)
3. Adds `cert.pem` (CA certificates) to the ZIP
4. Outputs final `dist/python-X.Y.Z-cosmo.com`

### Phase 3: Smoke Tests (`scripts/smoke.sh`)

Runs basic tests to verify the build:

- Version check
- Import key modules (ssl, sqlite3, ctypes, etc.)
- Basic functionality tests

## Source Patches

Patches are applied from two locations:

| Location | Applied To | Purpose |
|----------|------------|---------|
| `scripts/python/all/*.patch` | All versions | Universal fixes |
| `scripts/python/3.XX/*.patch` | Specific version | Version-specific fixes |

Current patches:

| Patch | Description |
|-------|-------------|
| `python-args.patch` | Fix argument handling for APE binaries |
| `sqlite-shared-cache.patch` | Disable SQLite shared cache (not supported) |
| `ctypes-cosmopolitan.patch` | Make ctypes work with Cosmopolitan |
| `setup-no-multiarch.patch` | Disable multiarch detection (3.10-3.11) |

## The Configure Problem

Python's `configure` script detects the build environment. When building on macOS, it adds Darwin-specific flags that don't apply to Cosmopolitan:

| Detection | Flag Added | Problem |
|-----------|-----------|---------|
| Darwin OS | `-framework CoreFoundation` | Cosmopolitan doesn't use macOS frameworks |
| Darwin OS | `-Wl,-stack_size,N` | macOS linker syntax, not portable |
| Darwin OS | `_scproxy` module | Requires SystemConfiguration.framework |
| Case-insensitive FS | `BUILDEXE=.exe` | Convention is `.com` |
| Link test fails* | `-latomic` | Cosmopolitan has built-in atomics |

*The `-latomic` false positive occurs because `-framework CoreFoundation` is already in LIBS when the atomics test runs, causing the link to fail for the wrong reason.

### Why Not Cross-Compile?

We could use `--host=x86_64-unknown-linux-gnu` to avoid Darwin detection, but:

1. Cross-compilation requires `--with-build-python` (external Python)
2. Cosmopolitan binaries **run on the build host** (that's the point!)
3. The build uses `_bootstrap_python` which it compiles and runs

### Solution: Makefile Patching

After `configure` generates the Makefile, we patch out platform-specific flags:

```bash
# Remove macOS framework flags
sed -i 's/ -framework [A-Za-z_][A-Za-z_]*//g' Makefile

# Remove macOS linker flags
sed -i 's/ -Wl,-stack_size,[0-9]*//g' Makefile

# Remove -latomic (false positive from failed link test)
sed -i 's/ -latomic//g' Makefile
```

This approach:

- ✅ Works on both Linux and macOS build hosts
- ✅ Works across Python versions without version-specific patches
- ✅ Simple text substitutions, easy to maintain
- ✅ Fixes symptoms without modifying complex configure logic

## Build Artifacts

```
work/
├── deps/                         # Static libraries
│   ├── lib/
│   │   ├── libssl.a
│   │   ├── libreadline.a
│   │   └── ...
│   └── include/
├── Python-3.12.12/               # Source (with patches applied)
└── build-3.12.12-x86_64/         # Build directory
    ├── python.com                # Fat binary (x86_64 + aarch64)
    ├── python.com.dbg            # Debug symbols
    └── libpython3.12.a           # Static library

dist/
└── python-3.12.12-cosmo.com      # Final packaged binary
```

## Why Cosmopolitan is Special

Traditional cross-compilation:

```
Build machine (macOS) ──► Target machine (Linux)
                          Cannot run output on build machine
```

Cosmopolitan:

```
Build machine (any) ──► Universal APE binary
                        Runs on Linux, macOS, Windows, FreeBSD, etc.
```

The `cosmocc` compiler produces Actually Portable Executables (APE) that contain code for multiple architectures and adapt to the host OS at runtime. This is why we can build on macOS but produce binaries that run everywhere - and why we patch out macOS-specific flags rather than truly cross-compiling.
