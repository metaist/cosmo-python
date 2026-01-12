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
