# Building on macOS

!!! warning "Experimental"
    Building cosmo-python on macOS is **experimental**. While it works, there are
    several platform-specific workarounds required. Linux builds are more
    straightforward and recommended for production use.

This document covers macOS-specific build issues and their solutions.

## Overview

Building on macOS introduces challenges because:

1. **Configure detects Darwin** - Adds macOS-specific flags that don't work with Cosmopolitan
2. **BSD tools differ from GNU** - `ar`, `sed`, and other tools behave differently
3. **Homebrew interference** - pkg-config may find Homebrew libraries instead of our deps
4. **Framework dependencies** - macOS uses frameworks (CoreFoundation, etc.) that Cosmopolitan doesn't support

## macOS-Specific Fixes in compile.sh

### 1. Framework Removal

**Problem**: Configure adds `-framework CoreFoundation` to LIBS on Darwin.

**Solution**: Patch configure before running to skip the CoreFoundation addition:

```bash
# In compile.sh
if grep -q 'LIBS="\$LIBS -framework CoreFoundation"' "${SRC_DIR}/configure"; then
  sed_i 's/LIBS="\$LIBS -framework CoreFoundation"/: # disabled for cosmocc/' "${SRC_DIR}/configure"
fi
```

**Why**: The OpenSSL detection test compiles and links a test program. If `-framework CoreFoundation` is in LIBS, cosmocc fails with "CoreFoundation: no such file".

### 2. Makefile Post-Processing

**Problem**: Even with configure patched, some flags slip through.

**Solution**: Remove macOS-specific flags from the generated Makefile:

```bash
# Remove all -framework X flags
sed_i 's/ -framework [A-Za-z_][A-Za-z_]*//g' Makefile

# Remove macOS linker stack size flag
sed_i 's/-Wl,-stack_size,[0-9]* *//g' Makefile
```

### 3. OpenSSL Detection

**Problem**: pkg-config finds Homebrew's OpenSSL instead of our static build.

**Solution**: Explicitly pass OpenSSL paths to configure:

```bash
--with-openssl="${DEPS_DIR}" \
OPENSSL_INCLUDES="-I${DEPS_DIR}/include" \
OPENSSL_LDFLAGS="-L${DEPS_DIR}/lib" \
OPENSSL_LIBS="-lssl -lcrypto" \
```

**Why**: Configure's OpenSSL detection uses `OPENSSL_INCLUDES` and `OPENSSL_LDFLAGS` (not `OPENSSL_CFLAGS`/`OPENSSL_LIBS`) when pkg-config is available.

### 4. libb2 Prevention

**Problem**: Homebrew's libb2 may be detected, breaking portability.

**Solution**: Remove HAVE_LIBB2 from pyconfig.h after configure:

```bash
if grep -q "HAVE_LIBB2" pyconfig.h; then
  sed_i 's/#define HAVE_LIBB2 1/\/* #undef HAVE_LIBB2 *\//' pyconfig.h
fi
```

**Why**: Python should use its built-in blake2 (HACL*) for portability, not an external library.

### 5. pybuilddir.txt Fix

**Problem**: The sysconfig generation creates `build/lib.darwin-X.Y/` but pybuilddir.txt may contain "none".

**Solution**: Fix pybuilddir.txt after the build:

```bash
if [ -f "${BUILD_DIR}/pybuilddir.txt" ]; then
  actual_builddir=$(ls -d "${BUILD_DIR}/build/lib."*"-${PYTHON_MAJOR_MINOR}" 2>/dev/null | head -1)
  if [ -n "$actual_builddir" ]; then
    echo "build/$(basename "$actual_builddir")" > "${BUILD_DIR}/pybuilddir.txt"
    touch "${BUILD_DIR}/pybuilddir.txt"  # Prevent make from regenerating
  fi
fi
```

**Why**: The Makefile's `pybuilddir.txt` rule writes "none" first, then runs generate-posix-vars. If that fails (which can happen during bootstrap), pybuilddir.txt stays as "none", breaking `make install`.

### 6. python.exe vs python.com

**Problem**: On case-insensitive filesystems (macOS default), configure sets `BUILDEXE=.exe`. Renaming to `.com` triggers Makefile rebuilds.

**Solution**: Copy instead of rename:

```bash
if [ -f "${BUILD_DIR}/python.exe" ] && [ ! -f "${BUILD_DIR}/python.com" ]; then
  cp "${BUILD_DIR}/python.exe" "${BUILD_DIR}/python.com"
fi
```

**Why**: The Makefile uses `python.exe` as a target. Moving it away makes `make install` think it needs to rebuild.

## macOS-Specific Fixes in Dependency Scripts

### OpenSSL (openssl.sh)

**Problem**: BSD `ar` creates `__.SYMDEF` symbol tables that GNU `ld` ignores.

**Solution**: Use GNU ar from cosmocc for aarch64 archives:

```bash
# Create aarch64 archives with GNU ar (not BSD ar)
"${COSMO_DIR}/bin/aarch64-linux-cosmo-ar" rcs "${DEPS_DIR}/lib/.aarch64/libcrypto.a" $OBJS
```

**Problem**: libcrypto.a needs objects from multiple prefixes.

**Solution**: Include all object patterns:

```bash
CRYPTO_OBJS=$(find . -path "*/.aarch64/libcrypto-*.o" \
                  -o -path "*/.aarch64/libdefault-*.o" \
                  -o -path "*/.aarch64/libcommon-*.o")
```

### ncurses (ncurses.sh)

**Problem**: macOS's `tic` (ncurses 6.0) can't compile newer terminfo.src (ncurses 6.6).

**Solution**: Generate a minimal fallback.c stub:

```c
NCURSES_EXPORT(const TERMTYPE2 *)
_nc_fallback2(const char *name GCC_UNUSED)
{
    return ((const TERMTYPE2 *)0);  // Use system terminfo
}
```

**Why**: The fallback mechanism is only used when no terminfo database exists at runtime. Most systems have `/usr/share/terminfo`.

### Multiple Definition Errors

**Problem**: cosmocc generates stub functions for `if (func != NULL)` patterns, causing multiple definition errors.

**Solution**: Add linker flag:

```bash
LDFLAGS="-Wl,--allow-multiple-definition"
```

## Stub Modules

Some macOS-specific modules can't work with Cosmopolitan. We provide Python stubs:

### _scproxy

**Location**: `src/stubs/_scproxy.py`

**Purpose**: macOS proxy settings via SystemConfiguration.framework

**Stub behavior**: Returns empty proxy settings

```python
def _get_proxy_settings():
    return {'exclude_simple': False, 'exceptions': []}

def _get_proxies():
    return {}
```

**Why**: urllib.request imports _scproxy on Darwin. Without a stub, `import urllib.request` fails.

## Known Limitations on macOS

| Module | Status | Reason |
|--------|--------|--------|
| `_curses` | ❌ Disabled | terminfo fallback stub returns NULL |
| `_curses_panel` | ❌ Disabled | Depends on _curses |
| `_scproxy` | ⚠️ Stub | SystemConfiguration.framework not available |
| `_crypt` | ❌ Fails import | crypt() not available in Cosmopolitan |

## Verifying macOS Builds

After building on macOS, verify:

```bash
# Check platform detection
./dist/python-3.12.12-cosmo.com -c "import sys; print(sys.platform)"
# Should print: darwin (when run on macOS)

# Check SSL works
./dist/python-3.12.12-cosmo.com -c "import ssl; print(ssl.OPENSSL_VERSION)"
# Should print: OpenSSL 3.x.x ...

# Check urllib works (tests _scproxy stub)
./dist/python-3.12.12-cosmo.com -c "import urllib.request; print('OK')"
# Should print: OK

# Run smoke tests
./scripts/smoke.sh dist/python-3.12.12-cosmo.com
# Should pass 52/53 tests (curses expected to fail)
```

## Troubleshooting

### "CoreFoundation: no such file"

Configure's OpenSSL test is failing. Check that:
1. The configure script was patched to skip CoreFoundation
2. OPENSSL_INCLUDES and OPENSSL_LDFLAGS are set correctly

### "undefined reference to tls1_cbc_remove_padding_and_mac"

The aarch64 libcrypto.a is missing objects. Rebuild OpenSSL:
```bash
rm -rf work/openssl-* work/deps/lib/*ssl* work/deps/lib/*crypto*
./scripts/openssl.sh
```

### "No module named '_sysconfigdata__darwin_'"

pybuilddir.txt has wrong content. Check:
```bash
cat work/build-3.12.12-x86_64/pybuilddir.txt
# Should be: build/lib.darwin-3.12 (or similar)
```

### make install hangs or rebuilds everything

python.exe was moved instead of copied. The fix is in compile.sh - it should copy, not move.
