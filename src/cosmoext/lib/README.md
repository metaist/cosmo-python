# libcxx-large Archives

Pre-built C++ standard library archives compiled with `-mcmodel=large` for
use with cosmoext C++ extensions.

## Why these exist

The standard `libcxx.a` from cosmocc uses `PC32` and `PLT32` relocations that
assume code will be within ±2GB of addresses. Our runtime loader places code
at arbitrary addresses (0x7f0000000000), so we need `-mcmodel=large` which
uses 64-bit absolute addressing.

## Files

- `libcxx-large-x86_64.a` - x86_64 archive (~2.7MB)
- `libcxx-large-aarch64.a` - aarch64 archive (~3.0MB)

## Rebuilding

To rebuild these archives:

```bash
./scripts/libcxx-large.sh
```

This script:
1. Downloads cosmocc toolchain if needed
2. Clones cosmopolitan source if needed
3. Applies patches (contention_t.h fix)
4. Compiles all 50 libcxx source files with proper flags
5. Creates the archives

## Build flags

```
-std=c++23           # Required for expected.cpp
-mcmodel=large       # 64-bit addressing for runtime loading
-ffunction-sections  # Enable linker garbage collection
-fdata-sections
-fexceptions         # C++ exception support
-frtti               # Runtime type information
-O2                  # Optimization
-fno-stack-protector # Compatibility
```

## Patches applied

### contention_t.h

The cosmocc toolchain's header doesn't include `__COSMOPOLITAN__` in the
`int32_t` condition, but `cosmo_futex_wait` expects `int*`. We patch it:

```cpp
// Before:
#if defined(__linux__) || (defined(_AIX) && !defined(__64BIT__))

// After:
#if defined(__linux__) || defined(__COSMOPOLITAN__) || (defined(_AIX) && !defined(__64BIT__))
```

## Version independence

These archives are NOT tied to any Python version. The same archives work
with Python 3.10, 3.11, 3.12, 3.13, and 3.14.
