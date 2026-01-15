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
from urllib.parse import urlparse

# Map domains to human-readable source names
SOURCE_NAMES = {
    "github.com": "GitHub",
    "ftp.gnu.org": "GNU FTP",
    "www.python.org": "python.org",
    "www.sqlite.org": "sqlite.org",
    "sourceware.org": "sourceware.org",
    "curl.se": "curl.se",
}

# Display names for packages (default: use key as-is)
DISPLAY_NAMES = {
    "python": "Python",
    "bz2": "bzip2",
    "cacert": "CA certs",
    "cosmocc": "Cosmopolitan",
    "openssl": "OpenSSL",
    "xz": "xz/liblzma",
}

def get_source_name(url):
    """Derive human-readable source name from URL domain."""
    domain = urlparse(url).netloc
    return SOURCE_NAMES.get(domain, domain)

def get_sig_type(ver_info):
    """Get signature type from version info."""
    if "sigstore" in ver_info:
        return "Sigstore"
    elif "gpg" in ver_info:
        return "GPG"
    return "—"

def get_version_display(info):
    """Get version display string (range if multiple, single if one)."""
    vers = list(info["versions"].keys())
    if len(vers) == 1:
        return vers[0]
    # For multiple versions, show range using major.minor
    minors = sorted(set(".".join(v.split(".")[:2]) for v in vers))
    if minors[0] == minors[-1]:
        return minors[0]
    return f"{minors[0]}–{minors[-1]}"

def get_default_ver_info(info):
    """Get version info for the default version."""
    default = info["default"]
    # Handle case where default is a minor version (e.g., "3.13" -> "3.13.11")
    if "latest" in info and default in info["latest"]:
        default = info["latest"][default]
    return info["versions"][default]

cog.outl("| Dependency | Version | Source | Integrity | Signature |")
cog.outl("|------------|---------|--------|-----------|-----------|")

for key, info in versions.items():
    name = DISPLAY_NAMES.get(key, key)
    ver_display = get_version_display(info)
    ver_info = get_default_ver_info(info)
    url = ver_info["url"]
    sig = get_sig_type(ver_info)
    source = get_source_name(url)
    cog.outl(f"| **{name}** | {ver_display} | [{source}]({url}) | SHA256 | {sig} |")
]]]-->
| Dependency | Version | Source | Integrity | Signature |
|------------|---------|--------|-----------|-----------|
| **Python** | 3.10–3.14 | [python.org](https://www.python.org/ftp/python/3.13.11/Python-3.13.11.tgz) | SHA256 | Sigstore |
| **Cosmopolitan** | 4.0.2 | [GitHub](https://github.com/jart/cosmopolitan/releases/download/4.0.2/cosmocc-4.0.2.zip) | SHA256 | — |
| **bzip2** | 1.0.8 | [sourceware.org](https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz) | SHA256 | GPG |
| **CA certs** | 2025-12-02 | [curl.se](https://curl.se/ca/cacert-2025-12-02.pem) | SHA256 | — |
| **gdbm** | 1.23–1.26 | [GNU FTP](https://ftp.gnu.org/gnu/gdbm/gdbm-1.26.tar.gz) | SHA256 | GPG |
| **libffi** | 3.4–3.5 | [GitHub](https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz) | SHA256 | — |
| **ncurses** | 6.4–6.6 | [GNU FTP](https://ftp.gnu.org/gnu/ncurses/ncurses-6.6.tar.gz) | SHA256 | GPG |
| **OpenSSL** | 1.1–3.5 | [GitHub](https://github.com/openssl/openssl/releases/download/openssl-3.5.4/openssl-3.5.4.tar.gz) | SHA256 | GPG |
| **readline** | 8.2–8.3 | [GNU FTP](https://ftp.gnu.org/gnu/readline/readline-8.3.tar.gz) | SHA256 | GPG |
| **sqlite** | 3.51.2 | [sqlite.org](https://www.sqlite.org/2026/sqlite-autoconf-3510200.tar.gz) | SHA256 | — |
| **xz/liblzma** | 5.4–5.8 | [GitHub](https://github.com/tukaani-project/xz/releases/download/v5.8.2/xz-5.8.2.tar.gz) | SHA256 | GPG |
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
