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
   - Compile extension with `-mcmodel=large -fno-pic` (position-independent addresses)
   - Extract symbol table from `python.com`
   - Resolve all external references to concrete addresses
   - Package as `.cosmoext` blob with relocation metadata

2. **Load phase** (`_cosmoext.load()`):
   - mmap the blob into executable memory
   - Apply relocations (adjust addresses for actual load location)
   - Resolve external symbols using python.com's symbol table
   - Call `PyInit_*` to initialize the module

### File Format (v6)

```
┌────────────────────────────────────────────────────────────────┐
│ Header (80 bytes)                                              │
├────────────────────────────────────────────────────────────────┤
│ magic: "CEXT" (0x54584543)                                     │
│ version: 6                                                     │
│ load_address: 0 (position-independent)                         │
│ total_size: size of code+data sections                         │
│ init_offset: offset to PyInit_* function                       │
│ header_size: 80                                                │
│ num_sections: number of code/data sections                     │
│ num_relocs: number of internal relocations                     │
│ num_external_symbols: symbols to resolve from python.com       │
│ string_table_size: size of symbol name strings                 │
│ get_def_offset: offset to shim function (for multi-phase init) │
├────────────────────────────────────────────────────────────────┤
│ Sections[] (16 bytes each)                                     │
│   offset, size, flags                                          │
├────────────────────────────────────────────────────────────────┤
│ Relocations[] (24 bytes each)                                  │
│   blob_offset, reloc_type, size, target_offset                 │
├────────────────────────────────────────────────────────────────┤
│ External Symbols[] (16 bytes each)                             │
│   patch_offset, name_offset (into string table)                │
├────────────────────────────────────────────────────────────────┤
│ String Table                                                   │
│   null-terminated symbol names                                 │
├────────────────────────────────────────────────────────────────┤
│ Code + Data Sections                                           │
│   the actual executable code and initialized data              │
└────────────────────────────────────────────────────────────────┘
```

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

External symbols are resolved at load time from python.com's symbol table:

1. The symbol table is embedded in python.com as `.symtab.{arch}` (compressed)
2. At load time, `_cosmoext` reads and decompresses the table
3. Each external symbol name is looked up to find its address
4. The address is patched into the blob at the specified offset

Some symbols have aliases (Cosmopolitan's internal naming):
- `memmove` → `__memmove.default`
- `iscntrl` → `__iscntrl`

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

## Building Extensions

### Prerequisites

- cosmo-python built with `--cosmoext` flag (includes `_cosmoext` module)
- Cosmopolitan toolchain (`cosmocc`)
- Extension source code

### Using cosmoext-build

```bash
# Basic usage
python -m cosmoext.cosmoext_build -o myext.cosmoext myext.c

# With include paths
python -m cosmoext.cosmoext_build -o myext.cosmoext \
    -I/path/to/headers \
    myext.c

# Multiple source files
python -m cosmoext.cosmoext_build -o myext.cosmoext \
    src/module.c src/helpers.c

# Verbose output
python -m cosmoext.cosmoext_build -v -o myext.cosmoext myext.c
```

### Manual Build Steps

If you need more control:

```bash
# 1. Compile with cosmocc
cosmocc -c -mcmodel=large -fno-pic -I/path/to/python/include myext.c -o myext.o

# 2. Link into relocatable object
cosmocc -r -mcmodel=large myext.o -o myext.ro

# 3. Convert to .cosmoext
python -c "
from cosmoext.relocate import create_cosmoext
create_cosmoext('myext.ro', 'myext.cosmoext', 'python.com', init_name='PyInit_myext')
"
```

### Compiler Flags

| Flag | Purpose |
|------|---------|
| `-mcmodel=large` | All addresses as 64-bit (required for relocation) |
| `-fno-pic` | Disable position-independent code (we handle it ourselves) |
| `-fno-plt` | Direct calls instead of PLT (simplifies relocations) |

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

### Method 2: Manual Import Hook

If you have an older build without the `_bootstrap_external.py` patch:

```python
import _cosmoext_importer  # Install the import hook
import myextension         # Now finds myextension.cosmoext
```

### Method 3: Direct Loading

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

## Known Limitations

### No dlopen

Extensions that call `dlopen()` themselves won't work. This includes:
- Extensions that load plugins dynamically
- Extensions that link against system shared libraries

### Cython Relative Imports

Cython extensions that do relative imports during init now work thanks to
`_cosmoext.create_dynamic(spec)`, which sets the package context before calling
`PyInit_*`. This enables extensions like msgpack's `_cmsgpack` to work correctly.

### C++ Extensions

C++ extensions are untested. Potential issues:
- Static constructors may not run
- Exception handling may not work
- RTTI may not work

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

## Implementation Files

| File | Purpose |
|------|---------|
| `src/cosmoext/_cosmoextmodule.c` | C module: blob loading, relocation, symbol resolution |
| `src/cosmoext/relocate.py` | Python: ELF parsing, .cosmoext creation |
| `src/cosmoext/symtab.py` | Python: symbol table extraction from python.com |
| `src/cosmoext/cosmoext-build.py` | CLI: compile → link → convert pipeline |
| `src/cosmoext/libc_stubs.c` | C: stub implementations for missing symbols |
| `src/cosmoext/_cosmoext_importer.py` | Python: import hook |

## Development Notes

These notes capture practical knowledge for developers working on cosmoext.

### Testing cosmoext

Run the smoke test:
```bash
./scripts/smoke-cosmoext.sh dist/python-3.12.12-cosmo.com
```

**Requirements**:
- Python binary built with `--cosmoext` flag
- cosmocc toolchain at `/tmp/cosmo`
- Python source headers in `work/Python-X.Y.Z/Include` (kept after build)

If `work/` is cleaned, the smoke test skips gracefully but can't verify functionality.

### Fat Binaries and Architecture

cosmocc produces **fat binaries** by default—both x86_64 and aarch64 in one build:
- Main `.o` file: x86_64
- `.aarch64/` subdirectory: aarch64 version

When building `.cosmoext` for ARM64, `cosmoext-build.py` automatically uses the
`.aarch64/` version if present. This is handled in the `--arch aarch64` code path.

### Rebuilding After Code Changes

Python's build system caches aggressively. After modifying `_cosmoextmodule.c`:

1. Copy updated source: `cp src/cosmoext/_cosmoextmodule.c work/Python-X.Y.Z/Modules/`
2. Remove the compiled binary: `rm work/build-X.Y.Z-x86_64/python.com`
3. Recompile: `./scripts/python/compile.sh X.Y.Z --cosmoext`
4. Repackage: `rm dist/python-X.Y.Z-cosmo.com && ./scripts/python/package.sh X.Y.Z`

Just updating the source file is **not enough**—you must remove outputs to trigger rebuild.

### macOS Build Quirks

**Curses fails on Python 3.11+**: The `-undefined dynamic_lookup` linker flag isn't
supported by cosmocc. Python 3.10 works because it uses a different build path.
This is a known limitation, not a bug to fix.

**W^X on ARM64**: macOS ARM64 enforces Write XOR Execute. The loader:
1. Maps memory as writable with `MAP_JIT`
2. Copies code and applies relocations
3. Switches to executable via `pthread_jit_write_protect_np(1)`

Data sections that need to remain writable are copied to heap before the switch.

### Format Version History

| Version | Status | Notes |
|---------|--------|-------|
| v3, v4, v5 | Removed | Never released; didn't work on ARM64 |
| v6 | Current | Includes `reloc_type` field for proper ARM64 ADRP/ADD patching |

Only v6 is supported. The loader rejects other versions.

## Future Work

1. **C++ support**: Test and fix C++ extension loading
2. **Windows testing**: Verify VirtualAlloc-based loading works
3. **Symbol table optimization**: Faster lookup, smaller embedded table
4. **More extensions**: Test and document additional popular extensions
