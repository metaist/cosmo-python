"""GNU FTP-based upstreams: ncurses, readline, gdbm."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass

from ..common import version_key


@dataclass
class GnuDep:
    """A dependency hosted on GNU FTP."""

    project: str

    def fetch_latest(self) -> str | None:
        """Fetch latest version from GNU FTP."""
        url = f"https://ftp.gnu.org/gnu/{self.project}/"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                html = resp.read().decode()
            pattern = rf'{self.project}-(\d+\.\d+(?:\.\d+)?).tar.gz"'
            versions: list[str] = re.findall(pattern, html)
            if versions:
                return str(sorted(set(versions), key=version_key)[-1])
        except Exception:
            pass
        return None

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        return f"https://ftp.gnu.org/gnu/{self.project}/{self.project}-{version}.tar.gz"


GNU_DEPS: dict[str, GnuDep] = {
    "ncurses": GnuDep(project="ncurses"),
    "readline": GnuDep(project="readline"),
    "gdbm": GnuDep(project="gdbm"),
}
