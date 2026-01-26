# cosmoext: C Extension Loading

!!! warning "Experimental"
    The cosmoext system is **experimental**. The format and APIs may change.
    It currently works for several real-world extensions but has known limitations.

## Overview

Cosmopolitan Python cannot use traditional dynamic loading (`dlopen`) because APE
binaries are self-contained executables, not shared libraries. The cosmoext system
provides an alternative: **pre-resolved binary blobs** that can be loaded at runtime.

```
Traditional Python:              cosmoext:
┌─────────────┐                 ┌─────────────┐
│ extension.so│ ──dlopen()──►  │.cosmoext    │ ──mmap+relocate──►
│ (ELF/Mach-O)│                 │(custom blob)│
└─────────────┘                 └─────────────┘
```

## Architecture

### The Problem

When you `import numpy` in regular Python:

1. Python finds `numpy/core/_multiarray_umath.cpython-312-linux-x86_64.so`
2. Calls `dlopen()` to load the shared library
3. The dynamic linker resolves symbols (finds `PyModule_Create`, etc.)
4. Python calls `PyInit__multiarray_umath()` to initialize

This doesn't work in Cosmopolitan because:
- APE binaries aren't shared libraries - they're executables
- There's no dynamic linker available at runtime
- The binary's symbols aren't exported for dynamic linking

### The Solution

cosmoext pre-resolves all symbols at build time:

1. **Build phase** (`cosmoext-build`):
   - Compile extension with `cosmocc` (produces both x86_64 and aarch64)
   - Extract symbol table from `python.com`
   - Resolve all external references to concrete addresses
   - Package as fat `.cosmoext` blob with both architectures

2. **Load phase** (`_cosmoext.load()`):
   - Read fat header, select correct architecture payload
   - mmap the blob into executable memory
   - Apply relocations (adjust addresses for actual load location)
   - Resolve external symbols using python.com's symbol table
   - Call `PyInit_*` to initialize the module

### File Format

The `.cosmoext` format is a **fat binary** containing code for both x86_64 and aarch64:

```
┌────────────────────────────────────────────────────────────────┐
│ Fat Header (48 bytes)                                          │
├────────────────────────────────────────────────────────────────┤
│ magic: "CEXT" (0x54584543)                                     │
│ version: 7                                                     │
│ flags: which architectures are present                         │
│ reserved: 0                                                    │
│ x86_64_offset: offset to x86_64 payload (0 if not present)     │
│ x86_64_size: size of x86_64 payload                            │
│ aarch64_offset: offset to aarch64 payload (0 if not present)   │
│ aarch64_size: size of aarch64 payload                          │
├────────────────────────────────────────────────────────────────┤
│ x86_64 Payload (if present)                                    │
│   Architecture-specific header + sections + relocations        │
├────────────────────────────────────────────────────────────────┤
│ aarch64 Payload (if present)                                   │
│   Architecture-specific header + sections + relocations        │
└────────────────────────────────────────────────────────────────┘
```

Each architecture payload contains:
- Header with section/relocation counts
- Section descriptors (code, data, etc.)
- Internal relocation table
- External symbol references
- String table for symbol names
- Actual code and data

### Relocation Types

#### x86_64
| Type | Description |
|------|-------------|
| `R_X86_64_64` | 64-bit absolute address |

#### ARM64 (aarch64)
| Type | Description |
|------|-------------|
| `R_AARCH64_ABS64` | 64-bit absolute address |
| `R_AARCH64_ADR_PREL_PG_HI21` | Page-relative high 21 bits (ADRP) |
| `R_AARCH64_ADD_ABS_LO12_NC` | Low 12 bits (ADD immediate) |
| `R_AARCH64_LDST*_ABS_LO12_NC` | Low 12 bits for load/store |

ARM64 requires special handling:
- **Branch range**: ARM64 branch instructions have ±128MB range
- **Trampolines**: For farther calls, we generate 16-byte stubs that load the full address

### Symbol Resolution

External symbols (like `PyModule_Create2`, `PyArg_ParseTuple`) are resolved at load
time from python.com's embedded symbol table.

**How symbol tables are created:**

The symbol tables are generated **automatically by Cosmopolitan's linker** (`cosmocc`)
during the Python build. No manual generation step is needed. The linker embeds
`.symtab.amd64` and `.symtab.arm64` files in the APE binary's ZIP directory.

You can verify they exist in the intermediate build:
```bash
unzip -l work/build-3.12.12-x86_64/python.com | grep symtab
#   1785856  ...   .symtab.amd64
#   1851392  ...   .symtab.arm64
```

**How symbol resolution works at runtime:**

1. The `_cosmoext` loader scans the APE binary for ZIP entries matching `.symtab.{arch}`
2. It decompresses the table (uses zlib DEFLATE)
3. For each external symbol in the extension, it looks up the name in the table
4. The resolved address is patched into the blob at the specified offset

**Symbol aliases:**

Some libc symbols have different names in Cosmopolitan's internal implementation:

| Extension uses | Cosmopolitan provides |
|----------------|----------------------|
| `memmove` | `__memmove.default` |
| `iscntrl` | `__iscntrl` |
| `ispunct` | `__ispunct` |
| `isspace` | `__isspace` |

The loader handles these aliases automatically.

### Memory Mapping

The loader uses mmap with architecture-specific flags:

**Linux (both archs)**:
```c
mmap(NULL, size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0)
```

**macOS ARM64** (W^X enforcement):
```c
// 1. Map as writable with MAP_JIT
mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_JIT, -1, 0)

// 2. Copy code, apply relocations

// 3. Switch to executable
pthread_jit_write_protect_np(1);  // Enable JIT protection
sys_icache_invalidate(ptr, size); // Flush instruction cache
```

**macOS x86_64**:
Standard mmap works (no W^X enforcement).

### Thread-Local Storage (TLS)

Extensions can use thread-local variables (`__thread` in C, `thread_local` in C++).
The cosmoext loader handles TLS sections automatically.

**How it works:**

1. **At build time**: The linker detects `.tdata` (initialized) and `.tbss` (uninitialized)
   TLS sections and emits TLS relocations
2. **At load time**: The loader:
   - Identifies TLS sections via the `COSMOEXT_SECTION_TLS` flag (0x4)
   - Allocates TLS space at offset 0x1000 from the thread pointer
   - Copies `.tdata` content to initialize thread-local variables
   - Patches TLS relocations to point to the correct offsets

**TLS Layout:**
```
Thread Pointer (TP)
  │
  ├── 0x0000 - 0x0FFF: python.com's TLS (reserved)
  │
  └── 0x1000+: Extension TLS
        ├── .tbss (uninitialized, zeroed)
        └── .tdata (initialized from blob)
```

**Example:**
```c
__thread int counter = 0;      // Goes in .tbss (zero-initialized)
__thread int magic = 42;       // Goes in .tdata (initialized to 42)

static PyObject* increment(PyObject* self, PyObject* args) {
    counter++;
    return PyLong_FromLong(counter);
}

static PyObject* get_magic(PyObject* self, PyObject* args) {
    return PyLong_FromLong(magic);  // Returns 42
}
```

**Supported TLS relocation types:**

| Architecture | Type | Description |
|--------------|------|-------------|
| x86_64 | `R_X86_64_TPOFF32` | 32-bit offset from thread pointer |
| ARM64 | `R_AARCH64_TLSLE_ADD_TPREL_HI12` | High 12 bits of TP-relative offset |
| ARM64 | `R_AARCH64_TLSLE_ADD_TPREL_LO12_NC` | Low 12 bits of TP-relative offset |

**Limitations:**

- Single extension TLS block (multiple extensions would need offset tracking)
- Limited to ~4KB of TLS data per extension (can be increased if needed)
- Local Exec model only (no dynamic TLS via `__tls_get_addr`)

### Constructor Support (.init_array)

Extensions can use constructor functions that run before `PyInit_*`. This is
essential for C++ static initialization and Rust runtime setup.

**How it works:**

1. **At build time**: Constructors marked with `__attribute__((constructor))` or
   C++ static initializers are placed in the `.init_array` section
2. **The loader parses** `.rela.init_array` relocations to find constructor addresses
3. **At load time**: All constructors are called in order before `PyInit_*`

**Example:**
```c
static int initialized = 0;
static int magic_value = 0;

__attribute__((constructor))
static void my_init(void) {
    initialized = 1;
    magic_value = 42;
}

static PyObject* check_init(PyObject* self, PyObject* args) {
    if (initialized) {
        return PyLong_FromLong(magic_value);  // Returns 42
    }
    Py_RETURN_NONE;
}
```

**C++ static initialization:**
```cpp
#include <string>

// This constructor runs before PyInit_*
static std::string greeting = "Hello from C++!";

static PyObject* get_greeting(PyObject* self, PyObject* args) {
    return PyUnicode_FromString(greeting.c_str());
}
```

**Format details:**

The cosmoext v7 format includes constructor offsets in the header:
- `num_constructors`: Number of constructor functions
- Constructor offset table: Array of 8-byte offsets into the blob

## Building Extensions

### Prerequisites

- cosmo-python built with `--cosmoext` flag (includes `_cosmoext` module)
- Cosmopolitan toolchain (`cosmocc`)
- Extension source code

### Using cosmoext-build

```bash
# Basic C extension - produces fat binary with both architectures
python.com cosmoext-build.py --python python.com -o myext.cosmoext myext.c

# C++ extension with STL support
python.com cosmoext-build.py --python python.com -o myext.cosmoext --cxx myext.cpp

# With include paths
python.com cosmoext-build.py --python python.com -o myext.cosmoext \
    -I/path/to/headers \
    myext.c

# Multiple source files
python.com cosmoext-build.py --python python.com -o myext.cosmoext \
    src/module.c src/helpers.c

# Single architecture (for debugging)
python.com cosmoext-build.py --python python.com -o myext.cosmoext \
    --arch x86_64 myext.c

# Verbose output
python.com cosmoext-build.py --python python.com -o myext.cosmoext -v myext.c
```

### Compiler Flags

When compiling manually, use these flags:

| Flag | Purpose |
|------|---------|
| `-mcmodel=large` | All addresses as 64-bit (required for relocation) |
| `-fPIC` | Position-independent code |
| `-fno-stack-protector` | Avoid stack canary symbol dependencies |

## Loading Extensions

### Automatic Loading (Recommended)

With cosmo-python, `.cosmoext` files are loaded automatically like `.so` files:

```python
import myextension  # Finds myextension.cosmoext in sys.path
```

The import system:
1. Searches `sys.path` for `{name}.cosmoext`
2. Uses `CosmoExtLoader` (patched into `_bootstrap_external.py`)
3. Calls `_cosmoext.create_dynamic(spec)` to load the module
4. Falls back to normal import if `.cosmoext` not found

### Direct Loading

```python
import _cosmoext
module = _cosmoext.load('/path/to/myextension.cosmoext')
```

This bypasses the import system entirely.

## Working Extensions

These extensions have been tested and work:

| Extension | Type | Notes |
|-----------|------|-------|
| markupsafe | Multi-phase init (PEP 489) | Cython-generated |
| xxhash | Single-phase init | Pure C |
| regex | Single-phase init | Needs libc stubs |
| ujson | Single-phase init | Uses PyState_FindModule |
| crc32c | Single-phase init | Pure C, uses SIMD |
| msgpack | Single-phase init | Cython with relative imports |
| C++ STL | C++ | `std::sort`, `std::string`, etc. via `--cxx` flag |

## Known Limitations

### No dlopen

Extensions that call `dlopen()` themselves won't work. This includes:
- Extensions that load plugins dynamically
- Extensions that link against system shared libraries

### Cython Relative Imports

Cython extensions that do relative imports during init work thanks to
`_cosmoext.create_dynamic(spec)`, which sets the package context before calling
`PyInit_*`. This enables extensions like msgpack's `_cmsgpack` to work correctly.

### C++ Extensions

C++ extensions work, including the full C++ Standard Library (STL).

**What works:**

- C++ classes with constructors/destructors
- Member functions and virtual functions
- Global/static objects
- Exception handling (throw/catch)
- Operators new/delete
- **STL algorithms**: `std::sort`, `std::find`, `std::transform`, etc.
- **STL containers**: `std::string`, `std::vector`, `std::map`, etc.
- **STL utilities**: `std::move`, `std::make_unique`, `std::optional`, etc.

**Building C++ extensions:**

```bash
# Use --cxx flag to enable C++ mode and link libcxx
python.com cosmoext-build.py --python python.com -o myext.cosmoext --cxx myext.cpp
```

The `--cxx` flag:
1. Uses `cosmoc++` instead of `cosmocc`
2. Links against custom `libcxx-large.a` archives
3. Includes C++ runtime stubs in `libc_stubs.c`

**Why custom libcxx archives are needed:**

The standard `libcxx.a` from cosmocc uses `PC32` and `PLT32` relocations that assume
code is within ±2GB of addresses. Our runtime loader places code at arbitrary addresses
(0x7f0000000000), so we need `-mcmodel=large` which uses 64-bit absolute addressing.

The `libcxx-large.a` archives in `src/cosmoext/lib/` are rebuilt with:
```
-mcmodel=large    # 64-bit addressing
-std=c++23        # Full C++23 support
-fexceptions      # Exception handling
-frtti            # Runtime type information
```

See `src/cosmoext/lib/README.md` for build details, or rebuild with:
```bash
./scripts/libcxx-large.sh
```

**Example C++ extension:**

```cpp
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <algorithm>
#include <vector>
#include <string>

static PyObject* sort_list(PyObject* self, PyObject* args) {
    PyObject* list;
    if (!PyArg_ParseTuple(args, "O", &list)) return NULL;

    // Convert to std::vector
    std::vector<long> vec;
    Py_ssize_t size = PyList_Size(list);
    for (Py_ssize_t i = 0; i < size; i++) {
        vec.push_back(PyLong_AsLong(PyList_GetItem(list, i)));
    }

    // Use STL algorithm
    std::sort(vec.begin(), vec.end());

    // Convert back to Python list
    PyObject* result = PyList_New(size);
    for (Py_ssize_t i = 0; i < size; i++) {
        PyList_SetItem(result, i, PyLong_FromLong(vec[i]));
    }
    return result;
}

static PyMethodDef methods[] = {
    {"sort_list", sort_list, METH_VARARGS, "Sort a list using std::sort"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "stltest", NULL, -1, methods
};

PyMODINIT_FUNC PyInit_stltest(void) {
    return PyModule_Create(&module);
}
```

### Symbol Availability

Only symbols exported from python.com are available. If an extension needs a symbol
that isn't exported, it will fail to load.

Current stub symbols (implemented in libc_stubs.c):
- `iscntrl`, `ispunct`, `isalnum`, `toupper`, `isspace`
- `memcpy` (alias to `__memcpy.default`)
- `ceil` (math function)
- `Py_Version` (Cython compatibility)

### Platform Differences

| Platform | Status | Notes |
|----------|--------|-------|
| Linux x86_64 | ✅ Works | Standard mmap |
| Linux aarch64 | ✅ Works | Needs trampolines for long jumps |
| macOS x86_64 | ✅ Works | Standard mmap |
| macOS aarch64 | ✅ Works | MAP_JIT + W^X handling |
| Windows | ❓ Untested | Should work with VirtualAlloc |
| FreeBSD | ❓ Untested | Should work like Linux |

## Embedded Files

Each `python.com` binary includes files needed to build C extensions:

```
.cosmoext/
  include/           # Python headers (Python.h, cpython/, etc.)
    Python.h
    pyconfig.h       # Generated config for this build
    cpython/
    internal/
    ...
  libc_stubs.c       # Stub implementations for missing symbols
```

Extract with:
```python
import zipfile, sys
with zipfile.ZipFile(sys.executable) as zf:
    for name in zf.namelist():
        if name.startswith('.cosmoext/'):
            zf.extract(name, '/path/to/output')
```

Or via command line:
```bash
python.com -c "
import zipfile, sys
with zipfile.ZipFile(sys.executable) as zf:
    [zf.extract(n, '.') for n in zf.namelist() if n.startswith('.cosmoext/')]
"
```

## Implementation Files

| File | Purpose |
|------|---------|
| `src/cosmoext/_cosmoextmodule.c` | C module: blob loading, relocation, symbol resolution |
| `src/cosmoext/relocate.py` | Python: ELF parsing, .cosmoext creation |
| `src/cosmoext/symtab.py` | Python: symbol table extraction from python.com |
| `src/cosmoext/cosmoext-build.py` | CLI: compile → link → convert pipeline |
| `src/cosmoext/libc_stubs.c` | C: stub implementations for missing symbols |
| `src/cosmoext/_cosmoext_importer.py` | Python: import hook (fallback) |
| `src/cosmoext/lib/libcxx-large-*.a` | C++ runtime archives (built with `-mcmodel=large`) |
| `scripts/libcxx-large.sh` | Build script for C++ runtime archives |

## Development Notes

These notes capture practical knowledge for developers working on cosmoext.

### Testing cosmoext

The `scripts/cosmoext/test.sh` script downloads, builds, tests, and benchmarks extensions:

```bash
# Test all supported extensions
./scripts/cosmoext/test.sh python.com --ext all

# Test specific extensions
./scripts/cosmoext/test.sh python.com --ext markupsafe,xxhash

# Skip benchmarks (faster)
./scripts/cosmoext/test.sh python.com --ext ujson --no-benchmark

# Force rebuild
./scripts/cosmoext/test.sh python.com --ext markupsafe --force
```

Run benchmarks only (if `.cosmoext` files already exist in `/tmp`):
```bash
python.com scripts/cosmoext/benchmark.py
python.com scripts/cosmoext/benchmark.py markupsafe xxhash
```

**Supported extensions:**

| Extension | Type | Notes |
|-----------|------|-------|
| `markupsafe` | Cython | HTML escaping, ~1.2M calls/sec |
| `xxhash` | Pure C | Fast hashing, ~400 MB/s |
| `ujson` | C + C++ | Fast JSON, ~170K enc/dec per sec |
| `regex` | Pure C | Advanced regex engine |

**Requirements**:

- Python binary built with `--cosmoext` flag
- cosmocc toolchain at `/tmp/cosmo`
- Python 3 with pyelftools (for cosmoext-build)
- Network access (to download extension sources)

The test script is idempotent—it skips downloads and builds if files already exist.

### Fat Binaries

`cosmocc` produces **fat object files** by default—both x86_64 and aarch64:
- Main `.o` file: x86_64
- `.aarch64/` subdirectory: aarch64 version

`cosmoext-build` automatically uses both when creating `.cosmoext` files.
The resulting `.cosmoext` is also a fat binary that works on either architecture.

### Rebuilding After Code Changes

Python's build system caches aggressively. After modifying `_cosmoextmodule.c`,
use the `--clean` flag for a full rebuild:

```bash
# Clean rebuild with cosmoext (recommended)
./scripts/build.sh 3.12.12 --clean --cosmoext
```

Or manually:

1. Copy updated source: `cp src/cosmoext/_cosmoextmodule.c work/Python-X.Y.Z/Modules/`
2. Remove the compiled binary: `rm work/build-X.Y.Z-x86_64/python.com`
3. Recompile: `./scripts/python/compile.sh X.Y.Z --cosmoext`
4. Repackage: `rm dist/python-X.Y.Z-cosmo.com && ./scripts/python/package.sh X.Y.Z`

Just updating the source file is **not enough**—you must remove outputs to trigger rebuild.
The `--clean` flag handles this automatically by removing `work/build-*`, `work/Python-*`,
and `dist/python-*.com` for the specified versions.

### macOS Build Quirks

**Curses fails on Python 3.11+**: The `-undefined dynamic_lookup` linker flag isn't
supported by cosmocc. Python 3.10 works because it uses a different build path.
This is a known limitation, not a bug to fix.

**W^X on ARM64**: macOS ARM64 enforces Write XOR Execute. The loader:
1. Maps memory as writable with `MAP_JIT`
2. Copies code and applies relocations
3. Switches to executable via `pthread_jit_write_protect_np(1)`

Data sections that need to remain writable are copied to heap before the switch.

## Future Work

1. **Windows testing**: Verify VirtualAlloc-based loading works
2. **Symbol table optimization**: Faster lookup, smaller embedded table
3. **More extensions**: Test and document additional popular extensions
4. **libffi callbacks**: Fix `ffi_closure_alloc` crash on macOS (see [#112](https://github.com/metaist/cosmo-python/issues/112))
5. **PyO3/Rust extensions**: Requires Rust `compiler_builtins` for Cosmopolitan (see [#116](https://github.com/metaist/cosmo-python/issues/116))
6. **Multi-extension TLS**: Track TLS offsets across multiple loaded extensions
