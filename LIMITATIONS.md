# Limitations

This document describes known limitations of Cosmopolitan Python compared to standard CPython.

## What Works

Most of the standard library works normally. Here are modules people often ask about:

| Module | Status | Notes |
|--------|--------|-------|
| `ssl`, `hashlib` | ✅ | HTTPS, TLS, crypto all work |
| `sqlite3` | ✅ | Fully functional |
| `asyncio` | ✅ | Full async/await support |
| `threading` | ✅ | Works normally |
| `subprocess` | ✅ | Can run external commands |
| `multiprocessing` | ⚠️ | `fork` works; `spawn` doesn't ([details](#multiprocessing)) |
| `json`, `csv`, `xml` | ✅ | All data formats work |
| `re`, `difflib` | ✅ | Text processing works |
| `http.server` | ✅ | Can serve HTTP |
| `unittest`, `doctest` | ✅ | Testing works |
| `curses` | ✅ | TUI applications work |
| `gzip`, `bz2`, `lzma` | ✅ | All compression works |
| `ctypes` | ⚠️ | Structs work; no dlopen ([details](#ctypes)) |

---

## What Doesn't Work

| Feature | Module | Status | Notes |
|---------|--------|--------|-------|
| [GUI](#gui) | `tkinter` | ❌ | Requires Tk/Tcl |
| [Packages](#package-management) | `ensurepip` | ❌ | Single-file design |
| [Concurrency](#concurrency) | `multiprocessing` | ⚠️ | `spawn` fails; `fork` works |
| [FFI](#foreign-function-interface) | `ctypes` | ⚠️ | No dynamic loading |
| [FFI](#foreign-function-interface) | C extensions | ❌ | Can't pip install native packages |
| [Cryptography](#cryptography) | `_crypt` | ❌ | Deprecated; use `hashlib` |
| [Cryptography](#cryptography) | `ssl` | ⚠️ | No QUIC/HTTP/3 |
| [Platform](#platform-detection) | `sys.platform` | ⚠️ | Varies by host OS |
| [Database](#database) | `dbm` | ⚠️ | Only gdbm backend |
| [Miscellaneous](#miscellaneous) | `_uuid` | ⚠️ | Fallback implementation |

---

## GUI

### tkinter

**Not available.** Tk/Tcl requires dynamic linking and X11/platform windowing libraries that can't be statically linked into a portable binary.

This is a fundamental constraint shared by [python-build-standalone] and other static Python builds—GUI toolkits assume a specific platform.

**Alternatives:**
- **TUI**: [textual], [rich], [curses] for terminal interfaces
- **Web**: Serve a local web UI with `http.server` + browser
- **CLI**: [argparse], [click] for command-line interfaces

---

## Package Management

### ensurepip

**Not available.** Cosmopolitan Python is a single-file binary by design—there's no `site-packages` directory to install into at runtime.

**Alternatives:**
- [uv]: Fast Python package manager (can install pip if needed)
- **Vendoring**: Copy dependencies directly into your project

**Bundling dependencies:** Use [cosmofy] to bundle pure Python packages (including pip itself) into Cosmopolitan binaries.

**Why this design?** The value proposition of Cosmopolitan Python is "one file, runs everywhere." Adding runtime package installation would require a writable filesystem and defeat the portability goal.

---

## Concurrency

### multiprocessing

**Partially works.** Behavior depends on the start method:

| Start Method | Status | Notes |
|--------------|--------|-------|
| `fork` | ✅ Works | Default on Linux; `Pool` works |
| `spawn` | ❌ Fails | Can't re-import `__main__` |
| `forkserver` | ❌ Fails | Same issue as spawn |

**Why spawn fails:** The `spawn` method starts a fresh Python interpreter via `sys.executable` and re-imports your script using `runpy.run_path()`. Cosmopolitan binaries can't satisfy Python's import machinery this way—the spawned process fails to locate `__main__` as a file path.

This isn't a [Cosmopolitan libc][jart/cosmopolitan] limitation per se—it's how Python's multiprocessing module works. The same issue would affect any single-file Python distribution.

**Recommendations:**

```python
# Option 1: Use fork (works)
import multiprocessing as mp
mp.set_start_method('fork')  # default on Linux anyway
with mp.Pool(4) as pool:
    results = pool.map(func, data)

# Option 2: Use threads instead (often simpler)
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(func, data))

# Option 3: Use asyncio for I/O-bound work
import asyncio
results = await asyncio.gather(*[async_func(x) for x in data])
```

### Summary

| Approach | Status |
|----------|--------|
| `threading` | ✅ Works |
| `asyncio` | ✅ Works |
| `subprocess.run()` | ✅ Works |
| `multiprocessing` (fork) | ✅ Works |
| `multiprocessing` (spawn) | ❌ Fails |
| `concurrent.futures.ThreadPoolExecutor` | ✅ Works |
| `concurrent.futures.ProcessPoolExecutor` | ⚠️ Fork only |

---

## Foreign Function Interface

### ctypes

**Limited.** Two restrictions:

1. **`ctypes.pythonapi` is `None`**: Can't call back into Python's C API
2. **No `dlopen()`**: Can't load `.so`/`.dll` files at runtime

**Why:** Cosmopolitan produces statically-linked, position-independent executables. The dynamic linker (`ld.so`) isn't available, so `dlopen()` can't work. This is fundamental to how [Cosmopolitan libc][jart/cosmopolitan] achieves cross-platform portability.

**Comparison:**
- [python-build-standalone]: Can load C extensions (not portable)
- Cosmopolitan Python: Can't load C extensions (portable)

**Workaround:** If you need native code, compile it into the binary at build time. See [superconfigure] for upstream recipes and our own [build scripts][scripts/01-deps] for how we build OpenSSL, SQLite, libffi, etc.

### Native Extensions (pip install)

**Can't install packages with C extensions at runtime.**

- ❌ `pip install numpy` — needs to compile C code
- ❌ `pip install cryptography` — needs OpenSSL headers
- ✅ `pip install requests` — pure Python, works via [cosmofy]

**Why:** No compiler, linker, or headers in the binary. Even if there were, resulting `.so` files couldn't be loaded (see above).

**Solutions:**
1. **Pure Python**: Many packages work—use [cosmofy] to bundle them
2. **Fork and build**: Add C extensions at compile time in your own build
3. **Alternative packages**: Often a pure-Python alternative exists

---

## Cryptography

### _crypt

**Not available.** Deprecated in Python 3.11, removed in 3.13. We omit it from Python 3.10 and 3.11 builds as well because the underlying `crypt(3)` function varies across platforms (Linux, macOS, BSD) and isn't available on Windows. Since Cosmopolitan targets all these platforms with a single binary, there's no consistent implementation to provide.

**Alternatives:** [`hashlib.pbkdf2_hmac()`][pbkdf2], [`hashlib.scrypt()`][scrypt], or the [bcrypt] package.

### OpenSSL

Our OpenSSL 3.x build disables features requiring syscalls unavailable in [Cosmopolitan libc][jart/cosmopolitan]:

| Feature | Why Disabled | Impact |
|---------|--------------|--------|
| QUIC | No `sendmmsg`/`recvmmsg` | No HTTP/3 (HTTP/1.1 and HTTP/2 work) |
| Async | No async syscall support | Sync operations work normally |
| Secure memory | No `shm*` syscalls | Keys in regular memory |

**Note:** Standard HTTPS, TLS, and all crypto operations work correctly. These are edge-case features most code never uses.

See our [OpenSSL build script][openssl.sh] for the exact configuration.

---

## Platform Detection

Cosmopolitan binaries run on Linux, macOS, Windows, FreeBSD, NetBSD, and OpenBSD. Platform detection reports the **current host OS**, not a special value:

```python
# On Linux:
>>> import sys, platform
>>> sys.platform
'linux'
>>> platform.system()
'Linux'

# On macOS: 'darwin' / 'Darwin'
# On Windows: 'win32' / 'Windows'
```

**Detecting Cosmopolitan:** The version string identifies Cosmopolitan:

```python
>>> import platform
>>> platform.uname().version
'Cosmopolitan 4.0.2 MODE=x86_64; #174-Ubuntu SMP ...'

>>> 'Cosmopolitan' in platform.uname().version
True
```

**Impact:** Code checking `sys.platform == 'linux'` works on Linux, but the same binary reports differently on other platforms. If you need Cosmopolitan-specific behavior, check the version string instead.

---

## File System

### Virtual Filesystem

Bundled resources live in Cosmopolitan's `/zip/` virtual filesystem:

```python
>>> import ssl
>>> ssl.get_default_verify_paths().cafile
'/zip/share/ssl/cert.pem'
```

This is transparent for most operations but may surprise code expecting paths like `/etc/ssl/certs/`.

**Why `/zip/`?** The Python standard library, CA certificates, and other resources are stored in a ZIP archive appended to the binary. Cosmopolitan's VFS makes them accessible at runtime without extraction.

---

## Database

### dbm

**Only `dbm.gnu` (gdbm) available.** The `dbm.ndbm` backend requires `ndbm.h`, which isn't in our build.

```python
import dbm
db = dbm.open('mydb', 'c')  # Uses gdbm backend
```

For portable databases, consider `sqlite3` (fully supported).

---

## Miscellaneous

### _uuid

**Uses fallback implementation.**

- `uuid4()`: ✅ Works (uses `os.urandom()`)
- `uuid1()`: ⚠️ Time-based fallback (no MAC address)

Most code uses `uuid4()` and works fine.

---

## Further Information

Many limitations stem from [Cosmopolitan libc][jart/cosmopolitan] design choices that enable cross-platform portability. As Cosmopolitan evolves, some may be resolved.

**Useful resources:**
- [jart/cosmopolitan] — The underlying C library
- [superconfigure] — Build recipes for dependencies (OpenSSL, SQLite, etc.)
- [python-build-standalone] — Alternative static Python builds (platform-specific)
- [cosmofy] — Tool for bundling dependencies into Cosmopolitan binaries

**Found an issue not listed here?** Please check existing issues first, then [open a new one](https://github.com/metaist/cosmo-python/issues).

<!-- link references -->
[jart/cosmopolitan]: https://github.com/jart/cosmopolitan
[superconfigure]: https://github.com/ahgamut/superconfigure
[python-build-standalone]: https://github.com/indygreg/python-build-standalone
[cosmofy]: https://github.com/metaist/cosmofy
[uv]: https://docs.astral.sh/uv/
[textual]: https://github.com/Textualize/textual
[rich]: https://github.com/Textualize/rich
[curses]: https://docs.python.org/3/library/curses.html
[argparse]: https://docs.python.org/3/library/argparse.html
[click]: https://click.palletsprojects.com/
[scripts/01-deps]: https://github.com/metaist/cosmo-python/tree/main/scripts/01-deps
[pbkdf2]: https://docs.python.org/3/library/hashlib.html#hashlib.pbkdf2_hmac
[scrypt]: https://docs.python.org/3/library/hashlib.html#hashlib.scrypt
[bcrypt]: https://pypi.org/project/bcrypt/
[openssl.sh]: https://github.com/metaist/cosmo-python/blob/main/scripts/01-deps/openssl.sh
