"""Tests for bash functions in scripts/common.sh.

These tests call bash functions via subprocess and verify output/exit codes.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COMMON_SH = REPO_ROOT / "scripts" / "common.sh"


def run_bash(script: str) -> tuple[int, str, str]:
    """Run bash snippet, return (exit_code, stdout, stderr)."""
    full_script = f'source "{COMMON_SH}" && {script}'
    result = subprocess.run(
        ["bash", "-c", full_script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return result.returncode, result.stdout.strip(), result.stderr


# --- sqlite_autoconf ---


def test_sqlite_autoconf_simple() -> None:
    """sqlite_autoconf converts 3.51.2 to 3510200."""
    code, out, _ = run_bash('sqlite_autoconf "3.51.2"')
    assert code == 0
    assert out == "3510200"


def test_sqlite_autoconf_with_sub() -> None:
    """sqlite_autoconf converts 3.51.2.1 to 3510201."""
    code, out, _ = run_bash('sqlite_autoconf "3.51.2.1"')
    assert code == 0
    assert out == "3510201"


def test_sqlite_autoconf_single_digits() -> None:
    """sqlite_autoconf handles single digit minor/patch."""
    code, out, _ = run_bash('sqlite_autoconf "3.8.5"')
    assert code == 0
    assert out == "3080500"


# --- get_pkg_url, get_pkg_sha256, get_dep_version ---


def test_get_dep_version() -> None:
    """get_dep_version returns default version."""
    code, out, _ = run_bash('get_dep_version "cosmocc"')
    assert code == 0
    assert out  # Should return a version string


def test_get_pkg_sha256() -> None:
    """get_pkg_sha256 returns sha256 for version."""
    # First get the default version, then get its sha256
    code, out, _ = run_bash('''
        version=$(get_dep_version "cosmocc")
        get_pkg_sha256 "cosmocc" "$version"
    ''')
    assert code == 0
    assert len(out) == 64  # SHA256 is 64 hex chars


def test_get_pkg_url() -> None:
    """get_pkg_url returns URL for version."""
    code, out, _ = run_bash('''
        version=$(get_dep_version "cosmocc")
        get_pkg_url "cosmocc" "$version"
    ''')
    assert code == 0
    assert out.startswith("https://")
    assert "cosmocc" in out


def test_get_python_latest() -> None:
    """get_python_latest returns version for minor."""
    code, out, _ = run_bash('get_python_latest "3.13"')
    assert code == 0
    assert out.startswith("3.13.")


# --- verify_checksum ---


def test_verify_checksum_success(tmp_path: Path) -> None:
    """verify_checksum succeeds with correct hash."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\n")
    # SHA256 of "hello world\n" (compute actual hash)
    expected = "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"

    code, out, _ = run_bash(f'verify_checksum "{test_file}" "{expected}"')
    assert code == 0
    assert "checksum verified" in out


def test_verify_checksum_failure(tmp_path: Path) -> None:
    """verify_checksum fails with wrong hash."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\n")
    wrong_hash = "0" * 64

    code, _, err = run_bash(f'verify_checksum "{test_file}" "{wrong_hash}"')
    assert code == 1
    assert "checksum mismatch" in err


# --- logging functions ---


def test_log_info() -> None:
    """log_info outputs message."""
    code, out, _ = run_bash('log_info "test message"')
    assert code == 0
    assert "test message" in out


def test_log_build() -> None:
    """log_build outputs BUILD prefix."""
    code, out, _ = run_bash('log_build "building something"')
    assert code == 0
    assert "BUILD" in out
    assert "building something" in out


def test_log_skip() -> None:
    """log_skip outputs with SKIP prefix."""
    code, out, _ = run_bash('log_skip "skipped"')
    assert code == 0
    assert "SKIP" in out
    assert "skipped" in out


def test_log_error() -> None:
    """log_error outputs to stderr."""
    code, _, err = run_bash('log_error "error message"')
    assert code == 0
    assert "error message" in err


# --- skip_if_exists ---


def test_skip_if_exists_file_present(tmp_path: Path) -> None:
    """skip_if_exists exits 0 when file exists."""
    test_file = tmp_path / "exists.txt"
    test_file.write_text("content")

    # skip_if_exists calls exit 0 when file exists
    code, out, _ = run_bash(f'skip_if_exists "{test_file}" "test"')
    assert code == 0
    assert "SKIP" in out


def test_skip_if_exists_file_missing(tmp_path: Path) -> None:
    """skip_if_exists continues (doesn't exit) when file missing."""
    # When file doesn't exist, skip_if_exists returns without calling exit
    # So we can run another command after it
    code, out, _ = run_bash(f'''
        skip_if_exists "{tmp_path}/nonexistent" "test"
        echo "continued"
    ''')
    assert code == 0
    assert "continued" in out


# --- ensure_dirs ---


def test_ensure_dirs_creates_directories(tmp_path: Path) -> None:
    """ensure_dirs creates WORK_DIR and DEPS_DIR."""
    work = tmp_path / "work"
    deps = tmp_path / "deps"

    code, _, _ = run_bash(f'''
        export WORK_DIR="{work}"
        export DEPS_DIR="{deps}"
        ensure_dirs
    ''')
    assert code == 0
    assert work.exists()
    assert deps.exists()
    assert (deps / "lib").exists()
    assert (deps / "include").exists()


# --- print_diagnostics ---


def test_print_diagnostics() -> None:
    """print_diagnostics outputs system info."""
    code, out, _ = run_bash("print_diagnostics")
    assert code == 0
    assert "uname" in out.lower() or "linux" in out.lower()
