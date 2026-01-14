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

Each release includes:

```
python-3.x.y-cosmo.zip
checksums.txt
```

## Usage

Download the appropriate release for your Python version:

```bash
# Download
curl -LO https://github.com/metaist/cosmo-python/releases/download/v3.x.y/python-3.x.y-cosmo.zip

# Verify checksum
sha256sum -c checksums.txt

# Extract
unzip python-3.x.y-cosmo.zip

# Run
./python.com --version
```

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
