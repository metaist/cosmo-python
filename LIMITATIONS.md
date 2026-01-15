# Limitations

This document describes known limitations of Cosmopolitan Python compared to standard CPython.

## Modules

### Not Included

| Module | Reason | Alternative |
|--------|--------|-------------|
| `tkinter` | Requires Tk/Tcl libraries | Use web UI, TUI (`curses`), or CLI |
| `_crypt` | Deprecated in 3.11, removed in 3.13 | `hashlib.pbkdf2_hmac()`, `hashlib.scrypt()` |
| `ensurepip` | Single-file binary design | Use [uv](https://docs.astral.sh/uv/) |

### Limited Functionality

| Module | Limitation | Notes |
|--------|------------|-------|
| `multiprocessing` | `spawn` and `Pool` don't work | Import works; fork-based may work on some platforms |
| `_uuid` | Uses fallback implementation | `uuid4()` works fine (uses `os.urandom()`); `uuid1()` uses time-based fallback |
| `dbm` | Only `dbm.gnu` (gdbm) available | `dbm.ndbm` requires ndbm.h we don't have |
| `ctypes` | `ctypes.pythonapi` is `None` | Can't call back into Python C API |
| `ctypes` | Limited dynamic library loading | Static binary can't load `.so`/`.dll` at runtime |

## OpenSSL 3.x

Our OpenSSL build disables features that require syscalls not available in Cosmopolitan:

| Feature | Why Disabled | Impact |
|---------|--------------|--------|
| QUIC | No `sendmmsg`/`recvmmsg` syscalls | No HTTP/3 support (HTTP/1.1 and HTTP/2 work fine) |
| Async | No async syscall support | Sync operations work normally |
| Secure memory | No `shm*` syscalls | Keys stored in regular memory |
| FORTIFY_SOURCE | No `__memcpy_chk` etc. | Defense-in-depth check disabled; OpenSSL is heavily audited |

**Note**: These limitations have minimal impact on typical Python usage. HTTPS, TLS, and all standard crypto operations work correctly.

## Platform Detection

Cosmopolitan binaries are universal (run on Linux, macOS, Windows, *BSD) but Python's platform detection may report unexpected values:

```python
>>> import sys, platform
>>> sys.platform
'cosmo'  # Not 'linux', 'darwin', or 'win32'
>>> platform.system()
'Cosmo'
```

Code that checks `sys.platform == 'linux'` may need adjustment.

## Native Extensions

Cosmopolitan Python is a statically-linked single-file binary. This means:

- **No C extensions at runtime**: Can't `pip install numpy` and have it compile C code
- **Pure Python only**: Packages must be pure Python or have pre-compiled Cosmopolitan support

**Workaround**: Use [cosmofy](https://github.com/metaist/cosmofy) to bundle pure Python dependencies into the binary.

## File System

The binary uses Cosmopolitan's `/zip/` virtual filesystem for bundled resources:

```python
>>> import ssl
>>> ssl.get_default_verify_paths().cafile
'/zip/share/ssl/cert.pem'
```

This is transparent for most operations but may surprise code that expects standard paths.

## Threads vs Processes

- **Threading**: Works normally
- **Subprocess**: `subprocess.run()` works for external commands
- **Multiprocessing**: Limited (see above)

For parallelism, prefer `threading` or `concurrent.futures.ThreadPoolExecutor`.

---

Many of these limitations stem from Cosmopolitan libc rather than this project. As Cosmopolitan evolves, some may be resolved. See [jart/cosmopolitan](https://github.com/jart/cosmopolitan) for updates.
