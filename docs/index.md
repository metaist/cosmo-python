# cosmo-python

Standalone versioned [Cosmopolitan](https://github.com/jart/cosmopolitan) Python builds.

## Why?

- **Single portable binary**: runs on Linux, macOS, Windows, FreeBSD, OpenBSD, NetBSD
- **Multiple Python versions**: 3.10 through 3.14 available
- **Verified supply chain**: all [upstream sources](https://docs.metaist.com/cosmo-python/supply-chain/) integrity-checked (SHA256, GPG, Sigstore)
- **Attested releases**: [weekly update checks](https://github.com/metaist/cosmo-python/blob/main/.github/workflows/check-updates.yaml), validated builds, [verifiable artifacts](https://docs.metaist.com/cosmo-python/releases/#verifying-downloads)
- **~45MB self-contained**: no installation, no dependencies, no container

See [Limitations](https://docs.metaist.com/cosmo-python/limitations/) for known differences from standard CPython.

## Usage

<!--[[[cog
import sys; sys.path.insert(0, ".")
from ci import cdx

bom = cdx.load("upstream.cdx.json")
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
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.14.2-cosmo.com
chmod +x python-3.14.2-cosmo.com
./python-3.14.2-cosmo.com --version
```
<!--[[[end]]]-->
