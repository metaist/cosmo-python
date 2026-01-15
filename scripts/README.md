# Build Scripts

This directory contains all build scripts and configuration for building Cosmopolitan Python.

## Structure

- `00-setup/` - Setup scripts (cosmocc toolchain, Python source download, system dependencies)
- `01-deps/` - Dependency build scripts (OpenSSL, SQLite, readline, etc.)
- `02-python/` - Python compilation scripts
- `03-package/` - Packaging scripts (create final `.com` binary with stdlib)
- `04-test/` - Test and validation scripts
- `config/` - Build configuration files
- `patches/` - Source code patches

## Main Entry Points

- `build.sh` - Build a single Python version
- `check-updates.sh` - Check for dependency updates
- `test-scripts.sh` - Validate script syntax and structure
