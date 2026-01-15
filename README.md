# cosmo-python

[![CI](https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml/badge.svg)](https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml)
[![Release](https://github.com/metaist/cosmo-python/actions/workflows/release.yaml/badge.svg)](https://github.com/metaist/cosmo-python/releases/latest)

Standalone versioned [Cosmopolitan] Python builds.

[cosmopolitan]: https://github.com/jart/cosmopolitan

## Why?

Existing Cosmopolitan Python builds (from [superconfigure]) are bundled with other tools in larger archives, making it difficult to:

- [Specify a particular Python version](#releases)
- [Verify build integrity with checksums](#verifying-downloads)
- [Track provenance of builds](#build-attestations)

This project provides:

- **Single portable binary** — runs on Linux, macOS, Windows, FreeBSD, OpenBSD, NetBSD
- **Automated pipeline** — [weekly update checks][check-updates.yaml], validated builds, [attested releases](#build-attestations)
- **Transparent builds** — all sources [SHA256 verified](#upstream-sources--trust), Python [Sigstore verified](#python-sigstore-verification)
- **~45MB self-contained** — no installation, no dependencies, no container

[superconfigure]: https://github.com/ahgamut/superconfigure
[check-updates.yaml]: .github/workflows/check-updates.yaml

## Usage

<!--[[[cog
import json
versions = json.load(open("versions.json"))
default_minor = versions["python"]["default"]
default_version = versions["python"]["latest"][default_minor]
cog.outl(f"Download and run:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-{default_version}-cosmo.com")
cog.outl(f"chmod +x python-{default_version}-cosmo.com")
cog.outl(f"./python-{default_version}-cosmo.com --version")
cog.outl("```")
]]]-->
Download and run:

```bash
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.12-cosmo.com
chmod +x python-3.12.12-cosmo.com
./python-3.12.12-cosmo.com --version
```
<!--[[[end]]]-->

Or use the manifest to find available versions:

```bash
curl -sL https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json | jq .
```

## Releases

We use **date-based releases** (e.g., `YYYYMMDD-HHMMSS`) rather than Python-version-based tags. This allows rebuilding the same Python version when Cosmopolitan or our patches change.

<!--[[[cog
cog.outl("Each release includes:")
cog.outl("")
cog.outl("```")
for minor in sorted(versions["python"]["latest"].keys()):
    ver = versions["python"]["latest"][minor]
    cog.outl(f"python-{ver}-cosmo.com")
cog.outl("manifest.json")
cog.outl("checksums.txt")
cog.outl("```")
]]]-->
Each release includes:

```
python-3.10.19-cosmo.com
python-3.11.14-cosmo.com
python-3.12.12-cosmo.com
python-3.13.11-cosmo.com
manifest.json
checksums.txt
```
<!--[[[end]]]-->

### How Releases Work

Releases are created through a semi-automated pipeline:

1. **[check-updates.yaml]** runs weekly to detect new Python/dependency versions and creates a PR
2. **[pr-build.yaml]** validates the PR by building all Python versions
3. A maintainer reviews and merges the PR
4. A maintainer triggers **[release.yaml]** to publish the new release

[check-updates.yaml]: .github/workflows/check-updates.yaml
[pr-build.yaml]: .github/workflows/pr-build.yaml
[release.yaml]: .github/workflows/release.yaml

### Verifying Downloads

#### Checksums

<!--[[[cog
cog.outl("Each release includes `checksums.txt` with SHA256 hashes:")
cog.outl("")
cog.outl("```bash")
cog.outl("curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/checksums.txt")
cog.outl(f"curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-{default_version}-cosmo.com")
cog.outl("sha256sum -c checksums.txt --ignore-missing")
cog.outl("```")
]]]-->
Each release includes `checksums.txt` with SHA256 hashes:

```bash
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/checksums.txt
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.12.12-cosmo.com
sha256sum -c checksums.txt --ignore-missing
```
<!--[[[end]]]-->

The `manifest.json` also includes SHA256 hashes for programmatic verification.

#### Build Attestations

<!--[[[cog
cog.outl("Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"gh attestation verify python-{default_version}-cosmo.com --repo metaist/cosmo-python")
cog.outl("```")
]]]-->
Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:

```bash
gh attestation verify python-3.12.12-cosmo.com --repo metaist/cosmo-python
```
<!--[[[end]]]-->

### Manifest Format

The `manifest.json` acts as a spanning registry, tracking all versions across releases:

```json
{
  "release": "YYYYMMDD-HHMMSS",
  "cosmocc": "X.Y.Z",
  "versions": {
    "3.12.8": {
      "url": "https://github.com/metaist/cosmo-python/releases/download/.../python-3.12.8-cosmo.com",
      "sha256": "...",
      "release": "YYYYMMDD-HHMMSS"
    }
  },
  "latest": { "3.12": "3.12.9", "3.13": "3.13.1" },
  "default": "3.12"
}
```

For details on how binaries are built and source verification, see [Building](#building).

---

## Building

### Quick Start

<!--[[[cog
cog.outl("```bash")
cog.outl(f"./scripts/build.sh {default_version}      # build specific version")
cog.outl("./scripts/build.sh --all       # build all versions")
cog.outl("```")
]]]-->
```bash
./scripts/build.sh 3.12.12      # build specific version
./scripts/build.sh --all       # build all versions
```
<!--[[[end]]]-->

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORK_DIR` | `./work` | Build working directory (sources, objects) |
| `DIST_DIR` | `./dist` | Output directory for built binaries |
| `COSMO_DIR` | `/tmp/cosmo` | Cosmopolitan toolchain installation path |
| `DEPS_DIR` | `$WORK_DIR/deps` | Compiled dependencies (openssl, libffi, etc.) |
| `SKIP_SIGSTORE` | _(unset)_ | Set to `1` to skip Python sigstore verification |

<!--[[[cog
cog.outl("Example:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh {default_version}")
cog.outl("```")
]]]-->
Example:

```bash
WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh 3.12.12
```
<!--[[[end]]]-->

### Source Verification

All upstream sources are verified during the build:

- **SHA256 checksums** for all downloads (stored in `versions.json`)
- **Official sources** only (no mirrors except GNU FTP)
- **Sigstore verification** for Python source (if `uvx` available)

#### Python Sigstore Verification

<!--[[[cog
# Get release manager for default version
minor = default_version.rsplit(".", 1)[0]
if minor in ("3.10", "3.11"):
    release_manager = "pablogsal@python.org"
else:
    release_manager = "thomas@python.org"

cog.outl("Python releases are signed using [Sigstore](https://sigstore.dev/) by the release manager.")
cog.outl("If [uv](https://docs.astral.sh/uv/) is installed, the build script automatically verifies signatures:")
cog.outl("")
cog.outl("```bash")
cog.outl("# Install uv (if not already installed)")
cog.outl("curl -LsSf https://astral.sh/uv/install.sh | sh")
cog.outl("")
cog.outl("# Build will now verify sigstore signatures")
cog.outl(f"./scripts/build.sh {default_version}")
cog.outl("```")
cog.outl("")
cog.outl("Manual verification:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"curl -LO https://www.python.org/ftp/python/{default_version}/Python-{default_version}.tgz")
cog.outl(f"curl -LO https://www.python.org/ftp/python/{default_version}/Python-{default_version}.tgz.sigstore")
cog.outl("")
cog.outl("uvx sigstore verify identity \\")
cog.outl(f"  --bundle Python-{default_version}.tgz.sigstore \\")
cog.outl(f'  --cert-identity "{release_manager}" \\')
cog.outl('  --cert-oidc-issuer "https://accounts.google.com" \\')
cog.outl(f"  Python-{default_version}.tgz")
cog.outl("```")
]]]-->
Python releases are signed using [Sigstore](https://sigstore.dev/) by the release manager.
If [uv](https://docs.astral.sh/uv/) is installed, the build script automatically verifies signatures:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Build will now verify sigstore signatures
./scripts/build.sh 3.12.12
```

Manual verification:

```bash
curl -LO https://www.python.org/ftp/python/3.12.12/Python-3.12.12.tgz
curl -LO https://www.python.org/ftp/python/3.12.12/Python-3.12.12.tgz.sigstore

uvx sigstore verify identity \
  --bundle Python-3.12.12.tgz.sigstore \
  --cert-identity "thomas@python.org" \
  --cert-oidc-issuer "https://accounts.google.com" \
  Python-3.12.12.tgz
```
<!--[[[end]]]-->

### Upstream Sources & Trust

All dependencies are SHA256 verified against known-good hashes in `versions.json`.

<!--[[[cog
cog.outl("| Component | Version | Source | Trust Model |")
cog.outl("|-----------|---------|--------|-------------|")
cog.outl("| **Python** | 3.10-3.13 | [python.org][python-src] | SHA256 + Sigstore |")
cog.outl(f"| **cosmocc** | {versions['cosmocc']['default']} | [GitHub Releases][cosmocc-src] | SHA256 verified (no attestations) |")
cog.outl(f"| **bz2** | {versions['bz2']['default']} | [sourceware.org][bz2-src] | SHA256 verified |")
cog.outl(f"| **CA certs** | {versions['cacert']['default']} | [curl.se][cacert-src] | SHA256 verified |")
cog.outl(f"| **gdbm** | {versions['gdbm']['default']} | [GNU FTP][gdbm-src] | SHA256 verified |")
cog.outl(f"| **libffi** | {versions['libffi']['default']} | [GitHub Releases][libffi-src] | SHA256 verified |")
cog.outl(f"| **ncurses** | {versions['ncurses']['default']} | [GNU FTP][ncurses-src] | SHA256 verified |")
cog.outl(f"| **OpenSSL** | {versions['openssl']['default']} | [GitHub Releases][openssl-src] | SHA256 verified |")
cog.outl(f"| **readline** | {versions['readline']['default']} | [GNU FTP][readline-src] | SHA256 verified |")
cog.outl(f"| **SQLite** | {versions['sqlite']['default']} | [sqlite.org][sqlite-src] | SHA256 verified |")
cog.outl(f"| **xz** | {versions['xz']['default']} | [GitHub Releases][xz-src] | SHA256 verified |")
]]]-->
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
<!--[[[end]]]-->

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

> **Note:** We currently use OpenSSL 1.1.x due to [Cosmopolitan compatibility issues with OpenSSL 3.0.x][openssl-issue].
> This version is still receiving security updates. See [#13][openssl-issue] for tracking.

[openssl-issue]: https://github.com/metaist/cosmo-python/issues/13

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
