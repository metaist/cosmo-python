# cosmo-python

[![CI][ci-badge]][ci-link] [![Release][release-badge]][release-link]

Standalone versioned [Cosmopolitan][cosmo] Python builds.

## Why?

- **Single portable binary**: runs on Linux, macOS, Windows, FreeBSD, OpenBSD, NetBSD
- **Multiple Python versions**: 3.10 through 3.14 available
- **Automated pipeline**: [weekly update checks][check-updates], validated builds, [attested releases](#build-attestations)
- **Transparent builds**: all sources [verified](#upstream-sources) (SHA256, GPG, Sigstore)
- **~45MB self-contained**: no installation, no dependencies, no container

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
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.13.11-cosmo.com
chmod +x python-3.13.11-cosmo.com
./python-3.13.11-cosmo.com --version
```
<!--[[[end]]]-->

Or use the [manifest][manifest] to find available versions:

```bash
curl -sL https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json | jq .
```

## Releases

We use date-based releases (`YYYYMMDD-HHMMSS`) that are created through a semi-automated pipeline:

1. **[check-updates.yaml][check-updates]** runs weekly to detect new Python/dependency versions and creates a PR
2. **[pr-build.yaml][pr-build]** validates the PR by building all Python versions
3. A maintainer reviews and merges the PR
4. A maintainer triggers **[release.yaml][release-workflow]** to publish the new release

Each release includes:

```
python-3.x.y-cosmo.com
...
manifest.json
checksums.txt
```

### Verifying Downloads

<!--[[[cog
cog.outl("Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"gh attestation verify python-{default_version}-cosmo.com --repo metaist/cosmo-python")
cog.outl("```")
]]]-->
Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:

```bash
gh attestation verify python-3.13.11-cosmo.com --repo metaist/cosmo-python
```
<!--[[[end]]]-->

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
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.13.11-cosmo.com
sha256sum -c checksums.txt --ignore-missing
```
<!--[[[end]]]-->

The [manifest][manifest] also includes SHA256 hashes for programmatic verification.

### Manifest Format

The [manifest][manifest] acts as a spanning registry, tracking all versions across releases:

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
  "default": "3.13"
}
```

For details on how binaries are built and source verification, see [Building](#building).

---

## Building

### Quick Start

<!--[[[cog
cog.outl("```bash")
cog.outl(f"./scripts/build.sh {default_version}  # build specific version")
cog.outl("./scripts/build.sh --all  # build all versions")
cog.outl("```")
]]]-->
```bash
./scripts/build.sh 3.13.11  # build specific version
./scripts/build.sh --all  # build all versions
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
WORK_DIR=/tmp/build DIST_DIR=./output ./scripts/build.sh 3.13.11
```
<!--[[[end]]]-->

### Upstream Sources

All upstream sources are SHA256 verified against known-good hashes in [`versions.json`][versions-json]. Sources that provide signatures (GPG or [Sigstore]) are also cryptographically verified. Only official sources are used (no mirrors except GNU FTP).

<!--[[[cog
# Helper to get signature type for a dep
def get_sig_type(dep, ver):
    v = versions[dep]["versions"][ver]
    if "sigstore" in v:
        return "Sigstore"
    elif "gpg" in v:
        return "GPG"
    return "—"

cog.outl("| Component | Version | Source | Hash | Signature |")
cog.outl("|-----------|---------|--------|------|-----------|")
cog.outl("| **Python** | 3.10-3.14 | [python.org][python-src] | SHA256 | Sigstore |")

deps = [
    ("bz2", "bz2", "[sourceware.org][bz2-src]"),
    ("CA certs", "cacert", "[curl.se][cacert-src]"),
    ("cosmocc", "cosmocc", "[GitHub Releases][cosmocc-src]"),
    ("gdbm", "gdbm", "[GNU FTP][gdbm-src]"),
    ("libffi", "libffi", "[GitHub Releases][libffi-src]"),
    ("ncurses", "ncurses", "[GNU FTP][ncurses-src]"),
    ("OpenSSL", "openssl", "[GitHub Releases][openssl-src]"),
    ("readline", "readline", "[GNU FTP][readline-src]"),
    ("SQLite", "sqlite", "[sqlite.org][sqlite-src]"),
    ("xz", "xz", "[GitHub Releases][xz-src]"),
]

for name, key, source in deps:
    ver = versions[key]["default"]
    sig = get_sig_type(key, ver)
    cog.outl(f"| **{name}** | {ver} | {source} | SHA256 | {sig} |")
]]]-->
| Component | Version | Source | Hash | Signature |
|-----------|---------|--------|------|-----------|
| **Python** | 3.10-3.14 | [python.org][python-src] | SHA256 | Sigstore |
| **bz2** | 1.0.8 | [sourceware.org][bz2-src] | SHA256 | GPG |
| **CA certs** | 2025-12-02 | [curl.se][cacert-src] | SHA256 | — |
| **cosmocc** | 4.0.2 | [GitHub Releases][cosmocc-src] | SHA256 | — |
| **gdbm** | 1.26 | [GNU FTP][gdbm-src] | SHA256 | GPG |
| **libffi** | 3.5.2 | [GitHub Releases][libffi-src] | SHA256 | — |
| **ncurses** | 6.6 | [GNU FTP][ncurses-src] | SHA256 | GPG |
| **OpenSSL** | 3.5.4 | [GitHub Releases][openssl-src] | SHA256 | GPG |
| **readline** | 8.3 | [GNU FTP][readline-src] | SHA256 | GPG |
| **SQLite** | 3.51.2 | [sqlite.org][sqlite-src] | SHA256 | — |
| **xz** | 5.8.2 | [GitHub Releases][xz-src] | SHA256 | GPG |
<!--[[[end]]]-->

---

## Acknowledgments

This project builds upon the excellent work of:

- **[Justine Tunney]** ([@jart]) - Creator of [Cosmopolitan libc][cosmo], the C library that makes truly portable executables.

- **[Gautham Venkatasubramanian]** ([@ahgamut]) - Creator and maintainer of [superconfigure], which provides build infrastructure for compiling Python with Cosmopolitan libc.

- **[python-build-standalone]** - Inspiration for standalone Python distribution patterns.

- **[Claude Opus 4.5]** - AI assistant that wrote most of this codebase with steering from [@metaist].

## License

[MIT License](LICENSE.md)

<!-- badges -->
[ci-badge]: https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml/badge.svg
[ci-link]: https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml
[release-badge]: https://github.com/metaist/cosmo-python/actions/workflows/release.yaml/badge.svg
[release-link]: https://github.com/metaist/cosmo-python/releases/latest

<!-- project links -->
[cosmo]: https://github.com/jart/cosmopolitan
[manifest]: https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json
[versions-json]: https://github.com/metaist/cosmo-python/blob/main/versions.json

<!-- workflows -->
[check-updates]: .github/workflows/check-updates.yaml
[pr-build]: .github/workflows/pr-build.yaml
[release-workflow]: .github/workflows/release.yaml

<!-- upstream sources -->
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
[sigstore]: https://sigstore.dev/

<!-- acknowledgments -->
[justine tunney]: https://justine.lol/
[@jart]: https://github.com/jart
[gautham venkatasubramanian]: https://ahgamut.github.io/
[@ahgamut]: https://github.com/ahgamut
[superconfigure]: https://github.com/ahgamut/superconfigure
[python-build-standalone]: https://github.com/indygreg/python-build-standalone
[claude opus 4.5]: https://www.anthropic.com/claude
[@metaist]: https://github.com/metaist
