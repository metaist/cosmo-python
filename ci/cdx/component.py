"""Component dataclass representing a software package."""

from __future__ import annotations

from dataclasses import dataclass

# Display names for components (only entries that differ from name)
DISPLAY_NAMES: dict[str, str] = {
    "python": "Python",
    "cacert": "CA certs",
    "cosmocc": "Cosmopolitan",
    "openssl": "OpenSSL",
    "xz": "xz/liblzma",
}


@dataclass
class Component:
    """A software component (package/library/application).

    >>> c = Component(
    ...     name="python", version="3.13.11",
    ...     url="https://python.org/ftp/python/3.13.11/Python-3.13.11.tgz",
    ...     sha256="abc123", license="PSF-2.0")
    >>> c.bom_ref
    'python@3.13.11'
    >>> c.display_name
    'Python'
    >>> c.source_domain
    'python.org'
    >>> c.has_sigstore
    False
    >>> c.has_gpg
    False

    >>> c2 = Component(
    ...     name="sqlite", version="3.0", url="https://www.sqlite.org/file.tar.gz",
    ...     sha256="x", license="Public Domain",
    ...     license_url="https://sqlite.org/copyright.html")
    >>> c2.display_name
    'sqlite'
    >>> c2.source_domain
    'sqlite.org'
    >>> c2.license_link
    '[Public Domain](https://sqlite.org/copyright.html)'

    >>> c3 = Component(
    ...     name="test", version="1.0", url="https://ftp.gnu.org/test.tar.gz",
    ...     sha256="x", license="MIT")
    >>> c3.source_domain
    'gnu.org'
    >>> c3.license_link
    'MIT'
    """

    name: str
    version: str
    url: str
    sha256: str
    license: str  # SPDX ID or custom name
    license_url: str | None = None
    purl: str | None = None
    gpg: str | None = None
    sigstore_identity: str | None = None
    sigstore_issuer: str | None = None
    description: str | None = None
    eol: str | None = None  # End of life date (YYYY-MM)
    status: str | None = None  # e.g., "bugfix", "security"
    component_type: str = "library"  # CycloneDX type: application, library, data
    attestation_repo: str | None = None  # GitHub repo for attestation verification

    @property
    def bom_ref(self) -> str:
        """Return the bom-ref identifier (name@version)."""
        return f"{self.name}@{self.version}"

    @property
    def display_name(self) -> str:
        """Return human-readable display name."""
        return DISPLAY_NAMES.get(self.name, self.name)

    @property
    def source_domain(self) -> str:
        """Return the source domain from the URL."""
        from urllib.parse import urlparse

        domain = urlparse(self.url).netloc
        # Strip www/ftp subdomain for cleaner display
        if domain.startswith(("www.", "ftp.")):
            domain = domain.split(".", 1)[1]
        return domain

    @property
    def license_link(self) -> str:
        """Return license as markdown link if URL available, otherwise just the license."""
        if self.license_url:
            return f"[{self.license}]({self.license_url})"
        return self.license

    @property
    def has_sigstore(self) -> bool:
        """Return True if this component has Sigstore verification."""
        return self.sigstore_identity is not None

    @property
    def has_gpg(self) -> bool:
        """Return True if this component has GPG verification."""
        return self.gpg is not None

    @property
    def signature_type(self) -> str:
        """Return the signature type for display."""
        if self.has_sigstore:
            return "Sigstore"
        elif self.has_gpg:
            return "GPG"
        return "—"
