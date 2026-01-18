"""Miscellaneous upstreams: sqlite, bzip2, cacert."""

from __future__ import annotations

import re
import urllib.request
from datetime import date

from ..common import version_key


class SqliteDep:
    """SQLite dependency with special version encoding."""

    def fetch_latest(self) -> str | None:
        """Fetch latest SQLite version."""
        url = "https://www.sqlite.org/download.html"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                html = resp.read().decode()
            match = re.search(r"sqlite-autoconf-(\d+)\.tar\.gz", html)
            if match:
                autoconf = match.group(1)
                # Convert 3510200 -> 3.51.2
                major = autoconf[0]
                minor = str(int(autoconf[1:3]))
                patch = str(int(autoconf[3:5]))
                sub = int(autoconf[5:7])
                if sub > 0:
                    return f"{major}.{minor}.{patch}.{sub}"
                return f"{major}.{minor}.{patch}"
        except (OSError, ValueError, IndexError):  # pragma: no cover
            pass
        return None  # pragma: no cover - defensive: regex/parse failed

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        parts = version.split(".")
        major, minor, patch = parts[0], parts[1], parts[2]
        sub = parts[3] if len(parts) > 3 else "0"
        autoconf = f"{major}{int(minor):02d}{int(patch):02d}{int(sub):02d}"
        year = date.today().year
        return f"https://www.sqlite.org/{year}/sqlite-autoconf-{autoconf}.tar.gz"

    def build_purl(self, version: str) -> str:
        """Build Package URL for version."""
        return f"pkg:generic/sqlite@{version}"


class Bzip2Dep:
    """bzip2 dependency."""

    def fetch_latest(self) -> str | None:
        """Fetch latest bzip2 version."""
        url = "https://sourceware.org/pub/bzip2/"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                html = resp.read().decode()
            pattern = r'bzip2-(\d+\.\d+\.\d+)\.tar\.gz"'
            versions: list[str] = re.findall(pattern, html)
            if versions:
                return str(sorted(set(versions), key=version_key)[-1])
        except OSError:  # pragma: no cover - network errors
            pass
        return None  # pragma: no cover - defensive: regex found no versions

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        return f"https://sourceware.org/pub/bzip2/bzip2-{version}.tar.gz"

    def build_purl(self, version: str) -> str:
        """Build Package URL for version."""
        return f"pkg:generic/bzip2@{version}"


class CacertDep:
    """CA certificate bundle dependency."""

    def fetch_latest(self) -> str | None:
        """Fetch latest CA cert bundle version."""
        url = "https://curl.se/docs/caextract.html"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                html = resp.read().decode()
            pattern = r"cacert-(\d{4}-\d{2}-\d{2})\.pem"
            versions: list[str] = re.findall(pattern, html)
            if versions:
                return str(sorted(set(versions))[-1])
        except OSError:  # pragma: no cover - network errors
            pass
        return None  # pragma: no cover - defensive: regex found no versions

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        return f"https://curl.se/ca/cacert-{version}.pem"

    def build_purl(self, version: str) -> str:
        """Build Package URL for version."""
        return f"pkg:generic/ca-certificates@{version}"


MISC_DEPS: dict[str, SqliteDep | Bzip2Dep | CacertDep] = {
    "sqlite": SqliteDep(),
    "bzip2": Bzip2Dep(),
    "cacert": CacertDep(),
}
