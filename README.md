# cosmo-python

[![CI][ci-badge]][ci-link] [![Release][release-badge]][release-link]

Standalone versioned [Cosmopolitan][cosmo] Python builds.

## Why?

- **Single portable binary**: runs on Linux, macOS, Windows, FreeBSD, OpenBSD, NetBSD
- **Multiple Python versions**: 3.10 through 3.14 available
- **Automated pipeline**: [weekly update checks][check-updates], validated builds, [attested releases](#build-attestations)
- **Transparent builds**: all sources [verified](#upstream-sources) (SHA256, GPG, Sigstore)
- **~45MB self-contained**: no installation, no dependencies, no container

See [LIMITATIONS.md](LIMITATIONS.md) for known differences from standard CPython.

## Usage

<!--[[[cog
import sys; sys.path.insert(0, ".")
from ci import cdx

bom = cdx.load("versions.cdx.json")
default_python = bom.get_default_component("python")
default_version = default_python.version
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

All upstream sources are SHA256 verified against known-good hashes in [`versions.cdx.json`][versions-cdx]. Sources that provide signatures (GPG or [Sigstore]) are also cryptographically verified. Only official sources are used (no mirrors except GNU FTP).

<!--[[[cog
cog.outl("| Dependency | Version | Source | Integrity | Signature | License |")
cog.outl("|------------|---------|--------|-----------|-----------|---------|")

for name in bom.component_names():
    comp = bom.get_default_component(name)
    if not comp:
        continue
    ver = f"{bom.python_minors()[0]}–{bom.python_minors()[-1]}" if name == "python" else comp.version
    cog.outl(f"| **{comp.display_name}** | {ver} | [{comp.source_domain}]({comp.url}) | SHA256 | {comp.signature_type} | {comp.license_link} |")
]]]-->
| Dependency | Version | Source | Integrity | Signature | License |
|------------|---------|--------|-----------|-----------|---------|
| **Python** | 3.10–3.14 | [python.org](https://www.python.org/ftp/python/3.13.11/Python-3.13.11.tgz) | SHA256 | Sigstore | [PSF-2.0](https://docs.python.org/3/license.html) |
| **Cosmopolitan** | 4.0.2 | [github.com](https://github.com/jart/cosmopolitan/releases/download/4.0.2/cosmocc-4.0.2.zip) | SHA256 | — | [ISC](https://github.com/jart/cosmopolitan/blob/master/LICENSE) |
| **bzip2** | 1.0.8 | [sourceware.org](https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz) | SHA256 | GPG | [bzip2-1.0.6](https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE) |
| **CA certs** | 2025-12-02 | [curl.se](https://curl.se/ca/cacert-2025-12-02.pem) | SHA256 | — | [MPL-2.0](https://www.mozilla.org/en-US/MPL/2.0/) |
| **gdbm** | 1.26 | [gnu.org](https://ftp.gnu.org/gnu/gdbm/gdbm-1.26.tar.gz) | SHA256 | GPG | [GPL-3.0-only](https://git.savannah.gnu.org/cgit/gdbm.git/tree/COPYING) |
| **libffi** | 3.5.2 | [github.com](https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz) | SHA256 | — | [MIT](https://github.com/libffi/libffi/blob/master/LICENSE) |
| **ncurses** | 6.6 | [gnu.org](https://ftp.gnu.org/gnu/ncurses/ncurses-6.6.tar.gz) | SHA256 | GPG | [X11](https://invisible-island.net/ncurses/ncurses-license.html) |
| **OpenSSL** | 3.5.4 | [github.com](https://github.com/openssl/openssl/releases/download/openssl-3.5.4/openssl-3.5.4.tar.gz) | SHA256 | GPG | [Apache-2.0](https://github.com/openssl/openssl/blob/master/LICENSE.txt) |
| **readline** | 8.3 | [gnu.org](https://ftp.gnu.org/gnu/readline/readline-8.3.tar.gz) | SHA256 | GPG | [GPL-3.0-only](https://git.savannah.gnu.org/cgit/readline.git/tree/COPYING) |
| **sqlite** | 3.51.2 | [sqlite.org](https://www.sqlite.org/2026/sqlite-autoconf-3510200.tar.gz) | SHA256 | — | [Public Domain](https://www.sqlite.org/copyright.html) |
| **xz/liblzma** | 5.8.2 | [github.com](https://github.com/tukaani-project/xz/releases/download/v5.8.2/xz-5.8.2.tar.gz) | SHA256 | GPG | [Public Domain](https://github.com/tukaani-project/xz/blob/master/COPYING) |
<!--[[[end]]]-->

---

## Acknowledgments

This project builds upon the excellent work of:

- **[Justine Tunney]** ([@jart]) - Creator of [Cosmopolitan libc][cosmo], the C library that makes truly portable executables.

- **[Gautham Venkatasubramanian]** ([@ahgamut]) - Creator and maintainer of [superconfigure], which provides build infrastructure for compiling Python with Cosmopolitan libc.

- **[Gregory Szorc]** ([@indygreg]) - Creator of [python-build-standalone], now maintained by [Astral]. Inspiration for standalone Python distribution patterns.

- **[Claude Opus 4.5]** - AI assistant that wrote most of this codebase with steering from [@metaist].

## License

[MIT License](LICENSE.md)

Upstream dependency licenses are shown in the [Upstream Sources](#upstream-sources) table.

<!-- badges -->
[ci-badge]: https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml/badge.svg
[ci-link]: https://github.com/metaist/cosmo-python/actions/workflows/ci.yaml
[release-badge]: https://github.com/metaist/cosmo-python/actions/workflows/release.yaml/badge.svg
[release-link]: https://github.com/metaist/cosmo-python/releases/latest

<!-- project links -->
[cosmo]: https://github.com/jart/cosmopolitan
[manifest]: https://github.com/metaist/cosmo-python/releases/latest/download/manifest.json
[versions-cdx]: https://github.com/metaist/cosmo-python/blob/main/versions.cdx.json

<!-- workflows -->
[check-updates]: .github/workflows/check-updates.yaml
[pr-build]: .github/workflows/pr-build.yaml
[release-workflow]: .github/workflows/release.yaml

[sigstore]: https://sigstore.dev/

<!-- acknowledgments -->
[justine tunney]: https://justine.lol/
[@jart]: https://github.com/jart
[gautham venkatasubramanian]: https://ahgamut.github.io/
[@ahgamut]: https://github.com/ahgamut
[superconfigure]: https://github.com/ahgamut/superconfigure
[gregory szorc]: https://gregoryszorc.com/
[@indygreg]: https://github.com/indygreg
[python-build-standalone]: https://github.com/astral-sh/python-build-standalone
[astral]: https://astral.sh/
[claude opus 4.5]: https://www.anthropic.com/claude
[@metaist]: https://github.com/metaist
