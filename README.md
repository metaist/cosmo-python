# cosmo-python

> **Note:** This project is under development and has not yet published any releases.
> See the [issues] for progress.

Standalone versioned [Cosmopolitan] Python builds.

[issues]: https://github.com/metaist/cosmo-python/issues

[cosmopolitan]: https://github.com/jart/cosmopolitan

## Why?

Existing Cosmopolitan Python builds (from [superconfigure]) are bundled with other tools in larger archives, making it difficult to:

- Specify a particular Python version
- Verify build integrity with checksums
- Track provenance of builds

This project provides clean, versioned Python builds as standalone releases.

## Releases

We use **date-based releases** (e.g., `20260114-153042`) rather than Python-version-based tags. This allows rebuilding the same Python version when Cosmopolitan or our patches change. The format is `YYYYMMDD-HHMMSS` to support multiple releases per day if needed.

Each release includes:

```
python-3.10.16-cosmo-x86_64.com
python-3.11.11-cosmo-x86_64.com
python-3.12.8-cosmo-x86_64.com
python-3.13.1-cosmo-x86_64.com
manifest.json
checksums.txt
```

The `manifest.json` provides metadata for programmatic access. It acts as a spanning registry, tracking all available versions across releases:

```json
{
  "release": "20260115-120000",
  "cosmocc": "4.0.2",
  "versions": {
    "3.12.8": {
      "url": "https://github.com/metaist/cosmo-python/releases/download/20260114-153042/python-3.12.8-cosmo-x86_64.com",
      "sha256": "...",
      "release": "20260114-153042"
    },
    "3.12.9": {
      "url": "https://github.com/metaist/cosmo-python/releases/download/20260115-120000/python-3.12.9-cosmo-x86_64.com",
      "sha256": "...",
      "release": "20260115-120000"
    }
  },
  "latest": {
    "3.12": "3.12.9",
    "3.13": "3.13.1"
  },
  "default": "3.12"
}
```

Each version entry includes a `release` field indicating which release contains that binary. This allows consumers to fetch specific versions while the manifest only needs to be fetched from the latest release.

## Usage

Download the appropriate release for your Python version:

```bash
# Download latest release
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.8-cosmo-x86_64.com

# Or fetch manifest to find available versions
curl -sL https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json | jq .

# Make executable and run
chmod +x python-3.12.8-cosmo-x86_64.com
./python-3.12.8-cosmo-x86_64.com --version
```

## When We Release

A new release is triggered when:

- **Upstream Python patch** - New Python bugfix release (e.g., 3.12.8 → 3.12.9)
- **Cosmopolitan update** - New cosmocc version with fixes or improvements
- **Build patches** - Changes to our patches or build configuration
- **Security issues** - CVEs in Python or dependencies

## Verification

### Download Verification

Each release includes `checksums.txt` with SHA256 hashes:

```bash
# Download checksums and binary
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/checksums.txt
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.8-cosmo-x86_64.com

# Verify
sha256sum -c checksums.txt --ignore-missing
```

The `manifest.json` also includes SHA256 hashes for programmatic verification.

### Build Verification

All upstream dependencies are verified during the build:

- **SHA256 checksums** for all downloads (stored in `versions.json`)
- **Official sources** only (no mirrors except GNU FTP)

### Trust Assumptions

| Component | Trust Model |
|-----------|-------------|
| **Python source** | SHA256 verified; sigstore attestations available (verification planned) |
| **cosmocc** | SHA256 verified; no upstream attestations currently available |
| **Other deps** | SHA256 verified against known-good hashes |

Note: cosmocc (Cosmopolitan toolchain) does not currently provide attestations. We pin to a specific version and verify its SHA256 hash, but cannot cryptographically verify its provenance.

## Upstream Sources

All external dependencies are fetched from official sources:

| Component | Version | Source | Why |
|-----------|---------|--------|-----|
| **cosmocc** | 4.0.2 | [GitHub Releases][cosmocc-src] | Official Cosmopolitan compiler toolchain |
| **Python** | 3.10-3.13 | [python.org][python-src] | Official release tarballs with pre-generated `configure` and sigstore attestations |
| **OpenSSL** | 1.1.1u | [GitHub Releases][openssl-src] | Official releases |
| **libffi** | 3.4.2 | [GitHub Releases][libffi-src] | Official releases |
| **xz** | 5.4.5 | [GitHub Releases][xz-src] | Official releases (liblzma for LZMA compression) |
| **bz2** | 1.0.8 | [sourceware.org][bz2-src] | Official bzip2 releases |
| **ncurses** | 6.4 | [GNU FTP][ncurses-src] | Official GNU releases |
| **readline** | 8.2 | [GNU FTP][readline-src] | Official GNU releases |

[cosmocc-src]: https://github.com/jart/cosmopolitan/releases
[python-src]: https://www.python.org/ftp/python/
[openssl-src]: https://github.com/openssl/openssl/releases
[libffi-src]: https://github.com/libffi/libffi/releases
[xz-src]: https://github.com/tukaani-project/xz/releases
[bz2-src]: https://sourceware.org/pub/bzip2/
[ncurses-src]: https://ftp.gnu.org/gnu/ncurses/
[readline-src]: https://ftp.gnu.org/gnu/readline/

## Acknowledgments

This project builds upon the excellent work of:

- **[Justine Tunney]** ([@jart]) - Creator of [Cosmopolitan libc], which makes it possible to build truly portable executables that run on Linux, macOS, Windows, FreeBSD, OpenBSD, and NetBSD.

- **[Gautham Venkatasubramanian]** ([@ahgamut]) - Maintainer of [superconfigure], which provides the build infrastructure for compiling Python and other software with Cosmopolitan libc.

[justine tunney]: https://justine.lol/
[@jart]: https://github.com/jart
[cosmopolitan libc]: https://github.com/jart/cosmopolitan

[gautham venkatasubramanian]: https://ahgamut.github.io/
[@ahgamut]: https://github.com/ahgamut
[superconfigure]: https://github.com/ahgamut/superconfigure

## License

[MIT License](LICENSE.md)
