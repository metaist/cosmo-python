# Source Code Patches

This directory contains patches applied to Python source code during the build process.

## Patch Types

### Universal Patches (`*.patch`)

Patches in this directory (not in subdirectories) are applied to **all** Python versions.
These typically patch Python's standard library or C source files that are consistent
across versions.

### Version-Specific Patches (`3.xx/*.patch`)

Patches in version subdirectories (e.g., `3.10/`, `3.11/`) are applied only to that
specific Python minor version. Use these for fixes that only apply to certain versions.

## Naming Convention

Patches can also use filename suffixes to indicate version ranges:

- `foo.patch` - Applied to all versions
- `foo-3.10.patch` - Applied only to Python 3.10.x
- `foo-3.10-3.11.patch` - Applied to Python 3.10.x and 3.11.x

## When Patches Are Applied

- Universal and version-specific patches in subdirectories are applied by
  `00-setup/python-source.sh` when downloading/extracting Python source.
- Patches with version suffixes in the filename are applied by
  `02-python/compile.sh` during compilation.
