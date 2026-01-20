# Releases

We use date-based releases (`YYYYMMDD-HHMMSS`) created through a semi-automated pipeline:

1. **[check-updates.yaml](https://github.com/metaist/cosmo-python/blob/main/.github/workflows/check-updates.yaml)** runs weekly to detect new Python/dependency versions and creates a PR
2. **[pr-build.yaml](https://github.com/metaist/cosmo-python/blob/main/.github/workflows/pr-build.yaml)** validates the PR by building all Python versions
3. A maintainer reviews and merges the PR
4. A maintainer triggers **[release.yaml](https://github.com/metaist/cosmo-python/blob/main/.github/workflows/release.yaml)** to publish the new release

Each release includes:

```
python-3.x.y-cosmo.com
...
manifest.cdx.json
checksums.txt
```

## Verifying Downloads

<!--[[[cog
import sys; sys.path.insert(0, ".")
from ci import cdx

bom = cdx.load("upstream.cdx.json")
default_python = bom.get_default_component("python")
default_version = default_python.version
cog.outl("Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:")
cog.outl("")
cog.outl("```bash")
cog.outl(f"gh attestation verify python-{default_version}-cosmo.com --repo metaist/cosmo-python")
cog.outl("```")
]]]-->
Release artifacts include [Sigstore](https://sigstore.dev/) build attestations proving they were built by this repo's GitHub Actions (not uploaded manually). Verify with:

```bash
gh attestation verify python-3.14.2-cosmo.com --repo metaist/cosmo-python
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
curl -LO https://github.com/metaist/cosmo-python/releases/latest/download/python-3.14.2-cosmo.com
sha256sum -c checksums.txt --ignore-missing
```
<!--[[[end]]]-->

## Release Manifest

The [manifest](https://github.com/metaist/cosmo-python/releases/latest/download/manifest.cdx.json) is a [CycloneDX 1.5](https://cyclonedx.org/) SBOM tracking all versions across releases.

**Programmatic download:**

```bash
curl -sL https://github.com/metaist/cosmo-python/releases/latest/download/manifest.cdx.json -o manifest.cdx.json
VERSION=$(jq -r '.metadata.properties[] | select(.name=="cosmo:default:python") | .value' manifest.cdx.json)
curl -Lo python.com $(jq -r --arg v "$VERSION" '.components[] | select(."bom-ref"=="cosmo-python@\($v)") | .externalReferences[0].url' manifest.cdx.json)
chmod +x python.com
./python.com --version
```

## Manifest Properties Reference

### Metadata properties

| Property | Description |
|----------|-------------|
| `cosmo:default:python` | Default Python version (e.g., `3.14.2`) |
| `cosmo:latest:python:3.x` | Latest patch for a minor version |

### Component properties (`cosmo-python` binaries)

| Property | Description |
|----------|-------------|
| `cosmo:attestation:repo` | GitHub repo for `gh attestation verify` |
| `cosmo:release` | Release tag this binary was built in |

### Component properties (upstream sources)

| Property | Description |
|----------|-------------|
| `cosmo:eol` | End of life date (`YYYY-MM`) |
| `cosmo:status` | Release status (`bugfix`, `security`) |
| `cosmo:gpg` | GPG fingerprint for verification |
| `cosmo:sigstore:identity` | Sigstore signer identity |
| `cosmo:sigstore:issuer` | Sigstore OIDC issuer |
