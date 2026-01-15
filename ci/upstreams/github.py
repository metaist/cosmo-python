"""GitHub-based upstreams: cosmocc, libffi, xz, openssl."""

from __future__ import annotations

from dataclasses import dataclass

from .http import gh_api


@dataclass
class GitHubDep:
    """A dependency hosted on GitHub releases."""

    owner: str
    repo: str
    prefix: str = "v"  # tag prefix to strip
    artifact: str = ""  # defaults to repo
    ext: str = ".tar.gz"

    def __post_init__(self) -> None:
        if not self.artifact:
            self.artifact = self.repo

    def fetch_latest(self) -> str:
        """Fetch latest release version from GitHub."""
        data = gh_api(f"repos/{self.owner}/{self.repo}/releases/latest")
        tag = str(data["tag_name"])
        if tag.startswith(self.prefix):
            tag = tag[len(self.prefix) :]
        return tag

    def build_url(self, version: str) -> str:
        """Build download URL for version."""
        tag = f"{self.prefix}{version}"
        return (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/releases/download/{tag}/{self.artifact}-{version}{self.ext}"
        )


GITHUB_DEPS: dict[str, GitHubDep] = {
    "cosmocc": GitHubDep(
        owner="jart",
        repo="cosmopolitan",
        prefix="",
        artifact="cosmocc",
        ext=".zip",
    ),
    "libffi": GitHubDep(owner="libffi", repo="libffi"),
    "xz": GitHubDep(owner="tukaani-project", repo="xz"),
    "openssl": GitHubDep(owner="openssl", repo="openssl", prefix="openssl-"),
}
