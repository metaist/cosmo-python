# Build Configuration Files

This directory contains configuration files used during the Python build process.

## Files

### `Setup.local.3.10`

Module configuration for Python 3.10.x builds. This file lists all C extension modules
to be built statically into the Python binary.

Python 3.10 uses `setup.py` to build extension modules, which tries to create shared
libraries (`.so` files). Since Cosmopolitan's cosmocc doesn't support shared libraries,
we provide this custom `Setup.local` file that tells the Makefile to build all modules
statically instead.

Python 3.11+ uses `Modules/Setup.stdlib` which has native support for static builds,
so they don't need a custom configuration file.

<!-- cspell:ignore Dflag Ipath Lpath llib -->

## Format

The `Setup.local` format is:

```
module_name source.c [source2.c ...] [-Dflag] [-Ipath] [-Lpath] [-llib]
```

Lines starting with `#` are comments. The `*static*` directive indicates all following
modules should be built statically.
