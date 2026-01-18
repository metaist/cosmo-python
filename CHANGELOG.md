# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog] and this project adheres to date-based versioning (`YYYYMMDD-HHMMSS`).

Sections order is: `Fixed`, `Changed`, `Added`, `Deprecated`, `Removed`, `Security`.

[keep a changelog]: https://keepachangelog.com/en/1.1.0/

---

## [Unreleased]

[unreleased]: https://github.com/metaist/cosmo-python/compare/prod...main

These are changes that are on `main` that are not yet in `prod`.

**Changed**

- [#47] default Python version changed to 3.13
- [#47] `versions.json` subkeys sorted to `eol`, `status`, `sha256`
- [#49] check-updates reads Python versions from `versions.json` instead of hardcoding
- [#49] check-updates uses endoflife.date API for status/eol
- [#49] check-updates uses `ds cog` for README regeneration
- [#13] upgraded OpenSSL from 1.1.1u (EOL) to 3.5.4
- [#60] `versions.json` replaced by `upstream.cdx.json` (CycloneDX 1.5 format)
- [#60] release `manifest.json` replaced by `manifest.cdx.json` (CycloneDX SBOM)
- [#60] built binaries are `cosmo-python` in manifest (depends on upstream `python` + libs)

**Added**

- [#46] Python 3.14.2 support
- [#47] `python.disabled` mapping in `versions.json` for yank feature
- [#13] OpenSSL 3.x support with Cosmopolitan compatibility
- [#48] GPG signature verification for upstream deps (xz, gdbm, ncurses, readline, bz2, openssl)
- [#48] `keys.asc` with GPG public keys for upstream maintainers
- [#48] per-version signing metadata (`sigstore`, `gpg`) in `versions.json`
- [#51] license tracking (`license`, `license_url`) in `versions.json`
- [#51] License column in README upstream sources table
- [#60] `ci/cdx.py` - CycloneDX BOM parsing and generation
- [#60] `ci/json_fmt.py` - semantic JSON formatter (entropy-aware compaction)
- [#60] manifest includes full dependency graph (python source + libraries)

**Removed**

- [#60] `versions.json` (replaced by `upstream.cdx.json`)
- [#60] `ci/normalize.py` (replaced by `ci/cdx.py` and `ci/json_fmt.py`)

---

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
[#46]: https://github.com/metaist/cosmo-python/issues/46
[#47]: https://github.com/metaist/cosmo-python/issues/47
[#48]: https://github.com/metaist/cosmo-python/issues/48
[#49]: https://github.com/metaist/cosmo-python/issues/49
[#51]: https://github.com/metaist/cosmo-python/issues/51
[#60]: https://github.com/metaist/cosmo-python/issues/60
[#13]: https://github.com/metaist/cosmo-python/issues/13
[20260115-134426]: https://github.com/metaist/cosmo-python/releases/tag/20260115-134426

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
