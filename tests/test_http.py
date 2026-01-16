"""Tests for ci/upstreams/http.py."""

from unittest.mock import MagicMock, patch

from ci.upstreams.http import fetch_json, fetch_sha256, gh_api


@patch("urllib.request.urlopen")
def test_fetch_json(mock_urlopen: MagicMock) -> None:
    """fetch_json parses JSON response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"key": "value"}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = fetch_json("https://example.com/api")
    assert result == {"key": "value"}


@patch("urllib.request.urlopen")
def test_fetch_sha256(mock_urlopen: MagicMock) -> None:
    """fetch_sha256 computes hash of response."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"test content"
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = fetch_sha256("https://example.com/file")
    # SHA256 of "test content"
    assert result == "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"


@patch("subprocess.run")
def test_gh_api(mock_run: MagicMock) -> None:
    """gh_api calls gh CLI and parses JSON."""
    mock_run.return_value = MagicMock(stdout='{"tag_name": "v1.0.0"}')

    result = gh_api("repos/owner/repo/releases/latest")
    assert result == {"tag_name": "v1.0.0"}
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["gh", "api", "repos/owner/repo/releases/latest"]
