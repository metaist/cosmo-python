# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to date-based versioning (`YYYYMMDD-HHMMSS`).

Sections order is: `Fixed`, `Changed`, `Added`, `Deprecated`, `Removed`, `Security`.

[keep a changelog]: https://keepachangelog.com/en/1.1.0/

---

## [Unreleased]

[unreleased]: https://github.com/metaist/cosmo-python/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Fixed**

- [#70] `MISC_DEPS` key mismatch (`bz2` vs `bzip2`)
- [#71] PURL not regenerated when updating dependencies
- [#72] hardcoded publisher in `ci/cdx/io.py`
- [#73] hardcoded repo URL in `ci/release_notes.py`
- [#76] `check_updates.py` crashes on `gh api` failures
- [#77] Python version fetcher uses non-existent API filter
- [#82] dependency refs not updated when default version changes
- [#84] new component versions don't inherit dependencies
- [#86] incorrect source path for `common.sh` in build scripts
- [#87] `CDX_CLI` fails when run from different directory
- [#88] `bz2.sh` script name doesn't match `bzip2` component
- [#91] `compileall` stripdir not working (traceback paths wrong)
- [#92] HACL endianness macro redefinition warnings (48 warnings removed)

**Changed**

- [#13] upgraded OpenSSL from 1.1.1u (EOL) to 3.5.4
- [#47] default Python version changed to 3.14
- [#47] `versions.json` subkeys sorted to `eol`, `status`, `sha256`
- [#49] check-updates reads Python versions from `versions.json` instead of hardcoding
- [#49] check-updates uses endoflife.date API for status/eol
- [#49] check-updates uses `ds cog` for README regeneration
- [#52] build scripts use URLs from `versions.json`
- [#53] standardized key ordering in JSON files
- [#54] wide-ranging delinting and cleanup
- [#58] use maximum ZIP compression for smaller binaries
- [#59] CI scripts rewritten in Python with shared module
- [#60] `versions.json` replaced by `upstream.cdx.json` (CycloneDX 1.5 format)
- [#60] release `manifest.json` replaced by `manifest.cdx.json` (CycloneDX SBOM)
- [#60] built binaries are `cosmo-python` in manifest (depends on upstream `python` + libs)
- [#62] flatten scripts structure with build caching
- [#64] restrict `pr-build.yaml` to trusted actors
- [#65] rename `versions.cdx.json` to `upstream.cdx.json`
- [#67] split `cdx.py` into `ci/cdx/` package
- [#68] `json_fmt` array expansion and trailing collapse fixes
- [#74] simplify trailing collapse heuristic (length + spaces)
- [#75] `pr-build.yaml` uses approval-based workflow
- [#93] consolidate release logic into `ci/release.py`

**Added**

- [#13] OpenSSL 3.x support with Cosmopolitan compatibility
- [#46] Python 3.14.2 support
- [#47] `python.disabled` mapping in `versions.json` for yank feature
- [#48] GPG signature verification for upstream deps (xz, gdbm, ncurses, readline, bz2, openssl)
- [#48] `keys.asc` with GPG public keys for upstream maintainers
- [#48] per-version signing metadata (`sigstore`, `gpg`) in `versions.json`
- [#51] license tracking (`license`, `license_url`) in `versions.json`
- [#51] License column in README upstream sources table
- [#55] `LIMITATIONS.md` documenting known limitations
- [#56] unit tests for `ci/` modules
- [#57] pre-compile `.pyc` files for faster startup
- [#60] `ci/cdx.py` - CycloneDX BOM parsing and generation
- [#60] `ci/json_fmt.py` - semantic JSON formatter
- [#60] manifest includes full dependency graph (python source + libraries)
- [#61] dependency graph and `build-order` command
- [#63] auto-generate release notes from changelog and deps
- [#66] `pyproject.toml` for proper Python project setup
- [#69] OpenSSL EOL tracking in check-updates
- [#75] approval-based PR build workflow for contributors
- [#89] disable deprecated Java raw API in libffi (cleaner build logs)
- [#90] zstd dependency for Python 3.14 `compression.zstd` module

**Removed**

- [#60] `versions.json` (replaced by `upstream.cdx.json`)
- [#60] `ci/normalize.py` (replaced by `ci/cdx.py` and `ci/json_fmt.py`)
- [#93] `ci/release_notes.py` (replaced by `ci/release.py`)

[#13]: https://github.com/metaist/cosmo-python/issues/13
[#46]: https://github.com/metaist/cosmo-python/issues/46
[#47]: https://github.com/metaist/cosmo-python/issues/47
[#48]: https://github.com/metaist/cosmo-python/issues/48
[#49]: https://github.com/metaist/cosmo-python/issues/49
[#51]: https://github.com/metaist/cosmo-python/issues/51
[#52]: https://github.com/metaist/cosmo-python/issues/52
[#53]: https://github.com/metaist/cosmo-python/issues/53
[#54]: https://github.com/metaist/cosmo-python/issues/54
[#55]: https://github.com/metaist/cosmo-python/issues/55
[#56]: https://github.com/metaist/cosmo-python/issues/56
[#57]: https://github.com/metaist/cosmo-python/issues/57
[#58]: https://github.com/metaist/cosmo-python/issues/58
[#59]: https://github.com/metaist/cosmo-python/issues/59
[#60]: https://github.com/metaist/cosmo-python/issues/60
[#61]: https://github.com/metaist/cosmo-python/issues/61
[#62]: https://github.com/metaist/cosmo-python/issues/62
[#63]: https://github.com/metaist/cosmo-python/issues/63
[#64]: https://github.com/metaist/cosmo-python/issues/64
[#65]: https://github.com/metaist/cosmo-python/issues/65
[#66]: https://github.com/metaist/cosmo-python/issues/66
[#67]: https://github.com/metaist/cosmo-python/issues/67
[#68]: https://github.com/metaist/cosmo-python/issues/68
[#69]: https://github.com/metaist/cosmo-python/issues/69
[#70]: https://github.com/metaist/cosmo-python/issues/70
[#71]: https://github.com/metaist/cosmo-python/issues/71
[#72]: https://github.com/metaist/cosmo-python/issues/72
[#73]: https://github.com/metaist/cosmo-python/issues/73
[#74]: https://github.com/metaist/cosmo-python/issues/74
[#75]: https://github.com/metaist/cosmo-python/issues/75
[#76]: https://github.com/metaist/cosmo-python/issues/76
[#77]: https://github.com/metaist/cosmo-python/issues/77
[#82]: https://github.com/metaist/cosmo-python/issues/82
[#84]: https://github.com/metaist/cosmo-python/issues/84
[#86]: https://github.com/metaist/cosmo-python/issues/86
[#87]: https://github.com/metaist/cosmo-python/issues/87
[#88]: https://github.com/metaist/cosmo-python/issues/88
[#89]: https://github.com/metaist/cosmo-python/issues/89
[#90]: https://github.com/metaist/cosmo-python/issues/90
[#91]: https://github.com/metaist/cosmo-python/issues/91
[#92]: https://github.com/metaist/cosmo-python/issues/92
[#93]: https://github.com/metaist/cosmo-python/issues/93

---

## [20260115-134426] - 2026-01-15

Initial release with Python 3.10.19, 3.11.14, 3.12.12, 3.13.11.

**Fixed**

- [#24] Python 3.10 build fails with missing `-ltermcap`
- [#25] stale/hardcoded version references in workflows
- [#26] Python 3.10.x fails to build with cosmocc due to system header conflicts
- [#27] Python 3.10.x build missing modules compared to 3.12+
- [#28] binary naming mismatch in `build.sh`
- [#29] README contains inaccurate/stale information
- [#30] add `_ctypes` module to Python 3.10 Setup.local
- [#31] patches not applied to existing source directories
- [#35] Python 3.11+ builds fail due to missing library flags in Setup.stdlib

**Changed**

- [#32] fix minor comment inconsistencies in scripts
- [#36] consolidate GitHub workflows with matrix builds
- [#37] update GitHub Actions to latest versions (checkout v6, cache v5, etc.)
- [#38] split deps build into separate job with caching
- [#40] clarify release triggers in README
- [#43] post-release README cleanup (remove disclaimer, add badges, OpenSSL note)
- [#45] expand Why? section with links and automation highlights

**Added**

- [#19] `_curses`/`_curses_panel` module support
- [#20] `_gdbm` module support
- [#21] `.args` file support for embedded script execution
- [#22] speed up Python compilation with ccache
- [#23] build script quality of life improvements
- [#33] basic `ctypes` smoke test
- [#34] timeouts for long-running build steps
- [#39] `01-deps/build.sh` as single source of truth for deps
- [#41] consolidate APE/binfmt setup into `00-setup/cosmocc.sh`
- [#44] attestations for manifest.json and checksums.txt

[#19]: https://github.com/metaist/cosmo-python/issues/19
[#20]: https://github.com/metaist/cosmo-python/issues/20
[#21]: https://github.com/metaist/cosmo-python/issues/21
[#22]: https://github.com/metaist/cosmo-python/issues/22
[#23]: https://github.com/metaist/cosmo-python/issues/23
[#24]: https://github.com/metaist/cosmo-python/issues/24
[#25]: https://github.com/metaist/cosmo-python/issues/25
[#26]: https://github.com/metaist/cosmo-python/issues/26
[#27]: https://github.com/metaist/cosmo-python/issues/27
[#28]: https://github.com/metaist/cosmo-python/issues/28
[#29]: https://github.com/metaist/cosmo-python/issues/29
[#30]: https://github.com/metaist/cosmo-python/issues/30
[#31]: https://github.com/metaist/cosmo-python/issues/31
[#32]: https://github.com/metaist/cosmo-python/issues/32
[#33]: https://github.com/metaist/cosmo-python/issues/33
[#34]: https://github.com/metaist/cosmo-python/issues/34
[#35]: https://github.com/metaist/cosmo-python/issues/35
[#36]: https://github.com/metaist/cosmo-python/issues/36
[#37]: https://github.com/metaist/cosmo-python/issues/37
[#38]: https://github.com/metaist/cosmo-python/issues/38
[#39]: https://github.com/metaist/cosmo-python/issues/39
[#40]: https://github.com/metaist/cosmo-python/issues/40
[#41]: https://github.com/metaist/cosmo-python/issues/41
[#43]: https://github.com/metaist/cosmo-python/issues/43
[#44]: https://github.com/metaist/cosmo-python/issues/44
[#45]: https://github.com/metaist/cosmo-python/issues/45
[20260115-134426]: https://github.com/metaist/cosmo-python/releases/tag/20260115-134426
