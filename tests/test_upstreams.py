"""Tests for ci/upstreams/."""

from unittest.mock import MagicMock, patch

from ci.upstreams.github import GitHubDep
from ci.upstreams.gnu import GnuDep
from ci.upstreams.misc import SqliteDep, Bzip2Dep, CacertDep
from ci.upstreams import openssl as openssl_upstream
from ci.upstreams.python import PythonUpstream


# --- GitHub ---


def test_github_dep_build_url_default() -> None:
    """GitHub dep builds URL with v prefix."""
    dep = GitHubDep(owner="libffi", repo="libffi")
    url = dep.build_url("3.5.2")
    assert url == "https://github.com/libffi/libffi/releases/download/v3.5.2/libffi-3.5.2.tar.gz"


def test_github_dep_build_url_no_prefix() -> None:
    """GitHub dep builds URL without prefix."""
    dep = GitHubDep(owner="jart", repo="cosmopolitan", prefix="", artifact="cosmocc", ext=".zip")
    url = dep.build_url("4.0.2")
    assert url == "https://github.com/jart/cosmopolitan/releases/download/4.0.2/cosmocc-4.0.2.zip"


def test_github_dep_build_url_custom_prefix() -> None:
    """GitHub dep builds URL with custom prefix."""
    dep = GitHubDep(owner="openssl", repo="openssl", prefix="openssl-")
    url = dep.build_url("3.5.4")
    assert url == "https://github.com/openssl/openssl/releases/download/openssl-3.5.4/openssl-3.5.4.tar.gz"


@patch("ci.upstreams.github.gh_api")
def test_github_dep_fetch_latest(mock_gh_api: MagicMock) -> None:
    """GitHub dep fetches and strips prefix."""
    mock_gh_api.return_value = {"tag_name": "v3.5.2"}
    dep = GitHubDep(owner="libffi", repo="libffi")
    assert dep.fetch_latest() == "3.5.2"
    mock_gh_api.assert_called_once_with("repos/libffi/libffi/releases/latest")


@patch("ci.upstreams.github.gh_api")
def test_github_dep_fetch_latest_custom_prefix(mock_gh_api: MagicMock) -> None:
    """GitHub dep strips custom prefix."""
    mock_gh_api.return_value = {"tag_name": "openssl-3.5.4"}
    dep = GitHubDep(owner="openssl", repo="openssl", prefix="openssl-")
    assert dep.fetch_latest() == "3.5.4"


@patch("ci.upstreams.github.gh_api")
def test_github_dep_fetch_latest_no_prefix_match(mock_gh_api: MagicMock) -> None:
    """GitHub dep returns full tag when prefix doesn't match."""
    mock_gh_api.return_value = {"tag_name": "release-1.0.0"}  # Doesn't start with 'v'
    dep = GitHubDep(owner="test", repo="test", prefix="v")  # Expects 'v' prefix
    assert dep.fetch_latest() == "release-1.0.0"


# --- GNU ---


def test_gnu_dep_build_url() -> None:
    """GNU dep builds URL."""
    dep = GnuDep(project="ncurses")
    url = dep.build_url("6.6")
    assert url == "https://ftp.gnu.org/gnu/ncurses/ncurses-6.6.tar.gz"


@patch("urllib.request.urlopen")
def test_gnu_dep_fetch_latest(mock_urlopen: MagicMock) -> None:
    """GNU dep parses FTP listing."""
    html = b'''
    <a href="ncurses-6.4.tar.gz">ncurses-6.4.tar.gz</a>
    <a href="ncurses-6.5.tar.gz">ncurses-6.5.tar.gz</a>
    <a href="ncurses-6.6.tar.gz">ncurses-6.6.tar.gz</a>
    '''
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    dep = GnuDep(project="ncurses")
    assert dep.fetch_latest() == "6.6"


@patch("urllib.request.urlopen")
def test_gnu_dep_fetch_latest_failure(mock_urlopen: MagicMock) -> None:
    """GNU dep returns None on error."""
    mock_urlopen.side_effect = OSError("Network error")
    dep = GnuDep(project="ncurses")
    assert dep.fetch_latest() is None


# --- SQLite ---


def test_sqlite_dep_build_url() -> None:
    """SQLite dep builds URL with autoconf version."""
    dep = SqliteDep()
    url = dep.build_url("3.51.2")
    assert "sqlite-autoconf-3510200.tar.gz" in url


def test_sqlite_dep_build_url_with_sub() -> None:
    """SQLite dep builds URL with sub-version."""
    dep = SqliteDep()
    url = dep.build_url("3.51.2.1")
    assert "sqlite-autoconf-3510201.tar.gz" in url


@patch("urllib.request.urlopen")
def test_sqlite_dep_fetch_latest(mock_urlopen: MagicMock) -> None:
    """SQLite dep parses download page."""
    html = b'''
    <a href="2026/sqlite-autoconf-3510200.tar.gz">sqlite-autoconf-3510200.tar.gz</a>
    '''
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    dep = SqliteDep()
    assert dep.fetch_latest() == "3.51.2"


@patch("urllib.request.urlopen")
def test_sqlite_dep_fetch_latest_failure(mock_urlopen: MagicMock) -> None:
    """SQLite dep returns None on error."""
    mock_urlopen.side_effect = OSError("Network error")
    dep = SqliteDep()
    assert dep.fetch_latest() is None


@patch("urllib.request.urlopen")
def test_sqlite_dep_fetch_latest_with_sub(mock_urlopen: MagicMock) -> None:
    """SQLite dep parses version with sub-patch."""
    html = b'''
    <a href="2026/sqlite-autoconf-3510201.tar.gz">sqlite-autoconf-3510201.tar.gz</a>
    '''
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    dep = SqliteDep()
    assert dep.fetch_latest() == "3.51.2.1"


# --- Bzip2 ---


def test_bzip2_dep_build_url() -> None:
    """Bzip2 dep builds URL."""
    dep = Bzip2Dep()
    url = dep.build_url("1.0.8")
    assert url == "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz"


@patch("urllib.request.urlopen")
def test_bzip2_dep_fetch_latest_failure(mock_urlopen: MagicMock) -> None:
    """Bzip2 dep returns None on error."""
    mock_urlopen.side_effect = OSError("Network error")
    dep = Bzip2Dep()
    assert dep.fetch_latest() is None


@patch("urllib.request.urlopen")
def test_bzip2_dep_fetch_latest(mock_urlopen: MagicMock) -> None:
    """Bzip2 dep parses directory listing."""
    html = b'''
    <a href="bzip2-1.0.6.tar.gz">bzip2-1.0.6.tar.gz</a>
    <a href="bzip2-1.0.8.tar.gz">bzip2-1.0.8.tar.gz</a>
    '''
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    dep = Bzip2Dep()
    assert dep.fetch_latest() == "1.0.8"


# --- Cacert ---


def test_cacert_dep_build_url() -> None:
    """Cacert dep builds URL."""
    dep = CacertDep()
    url = dep.build_url("2025-12-02")
    assert url == "https://curl.se/ca/cacert-2025-12-02.pem"


@patch("urllib.request.urlopen")
def test_cacert_dep_fetch_latest_failure(mock_urlopen: MagicMock) -> None:
    """Cacert dep returns None on error."""
    mock_urlopen.side_effect = OSError("Network error")
    dep = CacertDep()
    assert dep.fetch_latest() is None


@patch("urllib.request.urlopen")
def test_cacert_dep_fetch_latest(mock_urlopen: MagicMock) -> None:
    """Cacert dep parses caextract page."""
    html = b'''
    cacert-2025-11-01.pem
    cacert-2025-12-02.pem
    '''
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    dep = CacertDep()
    assert dep.fetch_latest() == "2025-12-02"


# --- Python ---


@patch("ci.upstreams.python.fetch_json")
def test_python_fetch_latest(mock_fetch: MagicMock) -> None:
    """Python upstream fetches latest for minor."""
    mock_fetch.return_value = {
        "results": [
            {"name": "Python 3.13.0", "is_published": True},
            {"name": "Python 3.13.1", "is_published": True},
            {"name": "Python 3.13.2", "is_published": False},
        ]
    }
    py = PythonUpstream()
    assert py.fetch_latest("3.13") == "3.13.1"


def test_python_build_url() -> None:
    """Python upstream builds URL."""
    py = PythonUpstream()
    url = py.build_url("3.13.1")
    assert url == "https://www.python.org/ftp/python/3.13.1/Python-3.13.1.tgz"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_bugfix(mock_eol: MagicMock) -> None:
    """Python status returns bugfix when in support period."""
    mock_eol.return_value = [
        {"cycle": "3.13", "releaseDate": "2024-10-01", "support": "2030-01-01", "eol": "2029-10-01"}
    ]
    py = PythonUpstream()
    assert py.get_status("3.13") == "bugfix"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_security(mock_eol: MagicMock) -> None:
    """Python status returns security when past support."""
    mock_eol.return_value = [
        {"cycle": "3.10", "releaseDate": "2021-10-01", "support": "2023-01-01", "eol": "2030-01-01"}
    ]
    py = PythonUpstream()
    assert py.get_status("3.10") == "security"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_eol(mock_eol: MagicMock) -> None:
    """Python EOL returns YYYY-MM format."""
    mock_eol.return_value = [
        {"cycle": "3.13", "eol": "2029-10-31"}
    ]
    py = PythonUpstream()
    assert py.get_eol("3.13") == "2029-10"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_eol_unknown(mock_eol: MagicMock) -> None:
    """Python EOL returns empty for unknown version (empty data)."""
    mock_eol.return_value = []
    py = PythonUpstream()
    assert py.get_eol("3.99") == ""


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_eol_not_found(mock_eol: MagicMock) -> None:
    """Python EOL returns empty when minor not in data."""
    mock_eol.return_value = [{"cycle": "3.13", "eol": "2029-10-31"}]  # Data exists but not 3.99
    py = PythonUpstream()
    assert py.get_eol("3.99") == ""


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_not_found(mock_eol: MagicMock) -> None:
    """Python status returns unknown when minor not in data."""
    mock_eol.return_value = [{"cycle": "3.13", "releaseDate": "2024-10-01", "support": "2030-01-01", "eol": "2029-10-01"}]
    py = PythonUpstream()
    assert py.get_status("3.99") == "unknown"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_unknown(mock_eol: MagicMock) -> None:
    """Python status returns unknown for unknown version (empty data)."""
    mock_eol.return_value = []
    py = PythonUpstream()
    assert py.get_status("3.99") == "unknown"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_eol(mock_eol: MagicMock) -> None:
    """Python status returns eol when past eol date."""
    mock_eol.return_value = [
        {"cycle": "3.8", "releaseDate": "2019-10-01", "support": "2021-01-01", "eol": "2024-01-01"}
    ]
    py = PythonUpstream()
    assert py.get_status("3.8") == "eol"


@patch("ci.upstreams.python._fetch_endoflife_data")
def test_python_get_status_prerelease(mock_eol: MagicMock) -> None:
    """Python status returns prerelease for future release."""
    mock_eol.return_value = [
        {"cycle": "3.99", "releaseDate": "2099-10-01", "support": "2100-01-01", "eol": "2104-01-01"}
    ]
    py = PythonUpstream()
    assert py.get_status("3.99") == "prerelease"


@patch("ci.upstreams.python.fetch_json")
def test_python_fetch_latest_failure(mock_fetch: MagicMock) -> None:
    """Python fetch_latest returns None on error."""
    mock_fetch.side_effect = OSError("Network error")
    py = PythonUpstream()
    assert py.fetch_latest("3.13") is None


@patch("ci.upstreams.python.fetch_json")
def test_python_fetch_latest_no_results(mock_fetch: MagicMock) -> None:
    """Python fetch_latest returns None if no published releases."""
    mock_fetch.return_value = {"results": []}
    py = PythonUpstream()
    assert py.fetch_latest("3.13") is None


# --- OpenSSL ---


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_eol(mock_fetch: MagicMock) -> None:
    """OpenSSL get_eol returns YYYY-MM format."""
    mock_fetch.return_value = {"3.5": ("2030-04-08", "lts")}
    assert openssl_upstream.get_eol("3.5.4") == "2030-04"
    assert openssl_upstream.get_eol("3.5") == "2030-04"


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_eol_unknown(mock_fetch: MagicMock) -> None:
    """OpenSSL get_eol returns empty for unknown version."""
    mock_fetch.return_value = {}
    assert openssl_upstream.get_eol("9.9.9") == ""


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_status_lts(mock_fetch: MagicMock) -> None:
    """OpenSSL get_status returns lts for LTS versions."""
    mock_fetch.return_value = {"3.5": ("2030-04-08", "lts")}
    assert openssl_upstream.get_status("3.5.4") == "lts"


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_status_supported(mock_fetch: MagicMock) -> None:
    """OpenSSL get_status returns supported for non-LTS active versions."""
    mock_fetch.return_value = {"3.4": ("2026-10-22", "supported")}
    assert openssl_upstream.get_status("3.4.0") == "supported"


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_status_eol(mock_fetch: MagicMock) -> None:
    """OpenSSL get_status returns eol for EOL versions."""
    mock_fetch.return_value = {"3.1": ("2025-03-14", "eol")}
    assert openssl_upstream.get_status("3.1.0") == "eol"


@patch("ci.upstreams.openssl._fetch_eol_data")
def test_openssl_get_status_unknown(mock_fetch: MagicMock) -> None:
    """OpenSSL get_status returns unknown for unknown version."""
    mock_fetch.return_value = {}
    assert openssl_upstream.get_status("9.9.9") == "unknown"
