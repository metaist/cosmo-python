# Supply Chain

All upstream sources are SHA256 verified against known-good hashes in [`upstream.cdx.json`](https://github.com/metaist/cosmo-python/blob/main/upstream.cdx.json). Sources that provide signatures (GPG or [Sigstore](https://sigstore.dev/)) are also cryptographically verified. Only official sources are used (no mirrors except GNU FTP).

## Upstream Dependencies

<!--[[[cog
import sys; sys.path.insert(0, ".")
from ci import cdx

bom = cdx.load("upstream.cdx.json")
cog.outl(bom.upstream_table())
]]]-->
| Dependency | Version | Integrity | Signature | License |
|------------|---------|-----------|-----------|---------|
| [Python](https://www.python.org/ftp/python/3.14.2/Python-3.14.2.tgz) | 3.10–3.14 | SHA256 | Sigstore | [PSF-2.0](https://docs.python.org/3/license.html) |
| [readline](https://ftp.gnu.org/gnu/readline/readline-8.3.tar.gz) | 8.3 | SHA256 | GPG | [GPL-3.0-only](https://git.savannah.gnu.org/cgit/readline.git/tree/COPYING) |
| [bzip2](https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz) | 1.0.8 | SHA256 | GPG | [bzip2-1.0.6](https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE) |
| [gdbm](https://ftp.gnu.org/gnu/gdbm/gdbm-1.26.tar.gz) | 1.26 | SHA256 | GPG | [GPL-3.0-only](https://git.savannah.gnu.org/cgit/gdbm.git/tree/COPYING) |
| [libffi](https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz) | 3.5.2 | SHA256 | — | [MIT](https://github.com/libffi/libffi/blob/master/LICENSE) |
| [ncurses](https://ftp.gnu.org/gnu/ncurses/ncurses-6.6.tar.gz) | 6.6 | SHA256 | GPG | [X11](https://invisible-island.net/ncurses/ncurses-license.html) |
| [OpenSSL](https://github.com/openssl/openssl/releases/download/openssl-3.6.1/openssl-3.6.1.tar.gz) | 3.6.1 | SHA256 | GPG | [Apache-2.0](https://github.com/openssl/openssl/blob/master/LICENSE.txt) |
| [sqlite](https://www.sqlite.org/2026/sqlite-autoconf-3510200.tar.gz) | 3.51.2 | SHA256 | — | [Public Domain](https://www.sqlite.org/copyright.html) |
| [xz/liblzma](https://github.com/tukaani-project/xz/releases/download/v5.8.2/xz-5.8.2.tar.gz) | 5.8.2 | SHA256 | GPG | [Public Domain](https://github.com/tukaani-project/xz/blob/master/COPYING) |
| [zstd](https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz) | 1.5.7 | SHA256 | GPG | [BSD-3-Clause](https://github.com/facebook/zstd/blob/dev/LICENSE) |
| [CA certs](https://curl.se/ca/cacert-2025-12-02.pem) | 2025-12-02 | SHA256 | — | [MPL-2.0](https://www.mozilla.org/en-US/MPL/2.0/) |
| [Cosmopolitan](https://github.com/jart/cosmopolitan/releases/download/4.0.2/cosmocc-4.0.2.zip) | 4.0.2 | SHA256 | — | [ISC](https://github.com/jart/cosmopolitan/blob/master/LICENSE) |
<!--[[[end]]]-->

## GitHub Actions

All GitHub Actions are pinned to SHA hashes and kept updated via [Dependabot](https://github.com/metaist/cosmo-python/blob/main/.github/dependabot.yml).

<!--[[[cog
from ci.common import github_actions_table
cog.outl(github_actions_table())
]]]-->
| Action | Version | Purpose |
|--------|---------|---------|
| [actions/attest-build-provenance](https://github.com/actions/attest-build-provenance) | v3 | Generate SLSA build provenance attestations |
| [actions/cache](https://github.com/actions/cache) | v5 | Cache dependencies between workflow runs |
| [actions/checkout](https://github.com/actions/checkout) | v6 | Clone repository |
| [actions/configure-pages](https://github.com/actions/configure-pages) | v5 | Configure GitHub Pages |
| [actions/deploy-pages](https://github.com/actions/deploy-pages) | v4 | Deploy to GitHub Pages |
| [actions/download-artifact](https://github.com/actions/download-artifact) | v7 | Download workflow artifacts |
| [actions/upload-artifact](https://github.com/actions/upload-artifact) | v6 | Upload workflow artifacts |
| [actions/upload-pages-artifact](https://github.com/actions/upload-pages-artifact) | v3 | Upload GitHub Pages artifact |
| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | v7 | Install uv package manager |
<!--[[[end]]]-->
