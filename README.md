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

[superconfigure]: https://github.com/ahgamut/superconfigure

## Usage

Download and run:

```bash
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.8-cosmo.com
chmod +x python-3.12.8-cosmo.com
./python-3.12.8-cosmo.com --version
```

Or use the manifest to find available versions:

```bash
curl -sL https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json | jq .
```

## Verification

### Checksums

Each release includes `checksums.txt` with SHA256 hashes:

```bash
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/checksums.txt
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.8-cosmo.com
sha256sum -c checksums.txt --ignore-missing
```

The `manifest.json` also includes SHA256 hashes for programmatic verification.

### Build Attestations

Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:

```bash
gh attestation verify python-3.12.8-cosmo.com --repo metaist/cosmo-python
```

## Releases

We use **date-based releases** (e.g., `20260114-153042`) rather than Python-version-based tags. This allows rebuilding the same Python version when Cosmopolitan or our patches change.

Each release includes:

```
python-3.10.16-cosmo.com
python-3.11.11-cosmo.com
python-3.12.8-cosmo.com
python-3.13.1-cosmo.com
manifest.json
checksums.txt
```

### Manifest Format

The `manifest.json` acts as a spanning registry, tracking all versions across releases:

```json
{
  "release": "20260115-120000",
  "cosmocc": "4.0.2",
  "versions": {
    "3.12.8": {
      "url": "https://github.com/metaist/cosmo-python/releases/download/20260114-153042/python-3.12.8-cosmo.com",
      "sha256": "...",
      "release": "20260114-153042"
    },
    "3.12.9": {
      "url": "https://github.com/metaist/cosmo-python/releases/download/20260115-120000/python-3.12.9-cosmo.com",
      "sha256": "...",
      "release": "20260115-120000"
    }
  },
  "latest": { "3.12": "3.12.9", "3.13": "3.13.1" },
  "default": "3.12"
}
```

### When We Release

A new release is triggered when:

- **Upstream Python patch** - New bugfix release (e.g., 3.12.8 → 3.12.9)
- **Cosmopolitan update** - New cosmocc version with fixes
- **Build patches** - Changes to our patches or build configuration
- **Security issues** - CVEs in Python or dependencies

---

## Building

### Quick Start

```bash
./scripts/build.sh 3.12.8      # build specific version
./scripts/build.sh --all       # build all versions
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORK_DIR` | `./work` | Build working directory (sources, objects) |
| `DIST_DIR` | `./dist` | Output directory for built binaries |
| `COSMO_DIR` | `/tmp/cosmo` | Cosmopolitan toolchain installation path |
| `DEPS_DIR` | `$WORK_DIR/deps` | Compiled dependencies (openssl, libffi, etc.) |
| `SKIP_SIGSTORE` | _(unset)_ | Set to `1` to skip Python sigstore verification |

Example:

```bash
WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh 3.12.8
```

### Build Verification

All upstream dependencies are verified during the build:

- **SHA256 checksums** for all downloads (stored in `versions.json`)
- **Official sources** only (no mirrors except GNU FTP)
- **Sigstore verification** for Python source (if `uvx` available)

#### Python Sigstore Verification

Python releases are signed using [Sigstore](https://sigstore.dev/) by the release manager.
If [uv](https://docs.astral.sh/uv/) is installed, the build script automatically verifies signatures:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Build will now verify sigstore signatures
./scripts/build.sh 3.12.8
```

Manual verification:

```bash
curl -LO https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tgz
curl -LO https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tgz.sigstore

uvx sigstore verify identity \
  --bundle Python-3.12.8.tgz.sigstore \
  --cert-identity "thomas@python.org" \
  --cert-oidc-issuer "https://accounts.google.com" \
  Python-3.12.8.tgz
```

### Upstream Sources & Trust

All dependencies are SHA256 verified against known-good hashes in `versions.json`.

| Component | Version | Source | Trust Model |
|-----------|---------|--------|-------------|
| **Python** | 3.10-3.13 | [python.org][python-src] | SHA256 + Sigstore |
| **cosmocc** | 4.0.2 | [GitHub Releases][cosmocc-src] | SHA256 verified (no attestations) |
| **bz2** | 1.0.8 | [sourceware.org][bz2-src] | SHA256 verified |
| **CA certs** | 2025-12-02 | [curl.se][cacert-src] | SHA256 verified |
| **gdbm** | 1.26 | [GNU FTP][gdbm-src] | SHA256 verified |
| **libffi** | 3.5.2 | [GitHub Releases][libffi-src] | SHA256 verified |
| **ncurses** | 6.6 | [GNU FTP][ncurses-src] | SHA256 verified |
| **OpenSSL** | 1.1.1u | [GitHub Releases][openssl-src] | SHA256 verified |
| **readline** | 8.3 | [GNU FTP][readline-src] | SHA256 verified |
| **SQLite** | 3.51.2 | [sqlite.org][sqlite-src] | SHA256 verified |
| **xz** | 5.8.2 | [GitHub Releases][xz-src] | SHA256 verified |

[bz2-src]: https://sourceware.org/pub/bzip2/
[cacert-src]: https://curl.se/docs/caextract.html
[cosmocc-src]: https://github.com/jart/cosmopolitan/releases
[gdbm-src]: https://ftp.gnu.org/gnu/gdbm/
[libffi-src]: https://github.com/libffi/libffi/releases
[ncurses-src]: https://ftp.gnu.org/gnu/ncurses/
[openssl-src]: https://github.com/openssl/openssl/releases
[python-src]: https://www.python.org/ftp/python/
[readline-src]: https://ftp.gnu.org/gnu/readline/
[sqlite-src]: https://www.sqlite.org/download.html
[xz-src]: https://github.com/tukaani-project/xz/releases

---

## Acknowledgments

This project builds upon the excellent work of:

- **[Justine Tunney]** ([@jart]) - Creator of [Cosmopolitan libc], which makes truly portable executables that run on Linux, macOS, Windows, FreeBSD, OpenBSD, and NetBSD.

- **[Gautham Venkatasubramanian]** ([@ahgamut]) - Maintainer of [superconfigure], which provides build infrastructure for compiling Python with Cosmopolitan libc.

[justine tunney]: https://justine.lol/
[@jart]: https://github.com/jart
[cosmopolitan libc]: https://github.com/jart/cosmopolitan
[gautham venkatasubramanian]: https://ahgamut.github.io/
[@ahgamut]: https://github.com/ahgamut

## License

[MIT License](LICENSE.md)
