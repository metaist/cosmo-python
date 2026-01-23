#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyelftools>=0.31"]
# ///
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

"""
cosmoext-build: Build .cosmoext files from C/C++ extension source.

Usage:
    cosmoext-build <source files> --python <python.com> --output <output.cosmoext> [options]

Examples:
    # Simple C extension
    cosmoext-build myext.c --python dist/python.com -o myext.cosmoext

    # Multi-file extension with includes
    cosmoext-build src/*.c --python dist/python.com -o myext.cosmoext -I include/

    # C++ extension
    cosmoext-build myext.cpp --python dist/python.com -o myext.cosmoext --cxx

    # Multi-phase init extension (PEP 489)
    cosmoext-build myext.c --python dist/python.com -o myext.cosmoext --shim

    # Pre-compiled object files
    cosmoext-build build/*.o --python dist/python.com -o myext.cosmoext
"""

# Find the cosmoext directory (where this script lives)
SCRIPT_DIR = Path(__file__).parent.resolve()
SHIM_SOURCE = SCRIPT_DIR / "cosmoext_shim.c"
LIBC_STUBS = SCRIPT_DIR / "libc_stubs.c"
RELOCATE_PY = SCRIPT_DIR / "relocate.py"

# Symbols that need stubs (not exported from python.com)
STUB_SYMBOLS = {"iscntrl", "ispunct", "isspace"}


def find_tool(name: str, search_paths: list[Path] | None = None) -> Path | None:
    """Find a tool by name in common locations."""
    import shutil

    # Check PATH first
    result = shutil.which(name)
    if result:
        return Path(result)

    # Check common locations
    candidates = [
        Path("/tmp/cosmo/bin") / name,
        Path.home() / ".cosmo/bin" / name,
        Path("/opt/cosmo/bin") / name,
    ]
    if search_paths:
        candidates = [p / name for p in search_paths] + candidates

    for p in candidates:
        if p.exists():
            return p
    return None


def find_cosmo_root(cosmocc: Path) -> Path:
    """Find the Cosmopolitan root directory from cosmocc location."""
    # cosmocc is typically at /path/to/cosmo/bin/cosmocc
    return cosmocc.parent.parent


def find_linker(cosmo_root: Path, arch: str = "x86_64") -> Path | None:
    """Find the appropriate linker for the architecture."""
    # The linker is in libexec/gcc/<triple>/<version>/ld.bfd
    libexec = cosmo_root / "libexec/gcc"
    if not libexec.exists():
        return None

    # Find the right triple directory
    for triple_dir in libexec.iterdir():
        if arch in triple_dir.name and "cosmo" in triple_dir.name:
            # Find version directory
            for version_dir in triple_dir.iterdir():
                ld = version_dir / "ld.bfd"
                if ld.exists():
                    return ld
    return None


def get_python_includes(python_path: Path) -> list[Path]:
    """Get include directories for Python headers."""
    includes = []
    build_dir = python_path.parent

    # Check if it's in a work/build-* directory structure (cosmo-python layout)
    if "work" in str(python_path) and "build-" in build_dir.name:
        work_dir = build_dir.parent
        # Extract version from build dir name (e.g., "build-3.12.12-x86_64" -> "3.12.12")
        parts = build_dir.name.replace("build-", "").split("-")
        version = parts[0] if parts else ""

        # Find matching Python source
        source_dir = work_dir / f"Python-{version}"
        if (source_dir / "Include").exists():
            includes.append(source_dir / "Include")

        # Build dir has pyconfig.h
        includes.append(build_dir)

    return includes


def run_cmd(
    cmd: list[str | Path],
    verbose: bool = False,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command, optionally capturing output.

    Uses shell=True to handle APE (Actually Portable Executable) binaries
    that may not be directly executable without binfmt_misc.
    """
    cmd_str = [str(c) for c in cmd]
    if verbose:
        print(f"  $ {' '.join(cmd_str)}")

    # Use shell mode for APE binary compatibility
    shell_cmd = " ".join(f'"{c}"' if " " in c else c for c in cmd_str)
    result = subprocess.run(
        shell_cmd,
        capture_output=capture,
        text=True,
        shell=True,
    )
    if check and result.returncode != 0:
        print(f"Command failed: {shell_cmd}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result


def get_undefined_symbols(obj_path: Path, nm_path: Path | None = None) -> set[str]:
    """Get undefined symbols from an object file."""
    nm = nm_path or find_tool("nm")
    if not nm:
        return set()

    result = run_cmd([nm, "-u", obj_path], check=False)
    if result.returncode != 0:
        return set()

    symbols = set()
    for line in result.stdout.strip().split("\n"):
        # nm -u output: "                 U symbol_name"
        parts = line.split()
        if len(parts) >= 2 and parts[-2] == "U":
            symbols.add(parts[-1])
        elif len(parts) == 1:
            symbols.add(parts[0])
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build .cosmoext files from C/C++ extension source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        nargs="+",
        help="Source file(s) (.c, .cpp, .cc) or object file(s) (.o)",
    )
    parser.add_argument(
        "--python",
        required=True,
        help="Path to python.com binary (for symbol resolution)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output .cosmoext file",
    )
    parser.add_argument(
        "--include",
        "-I",
        action="append",
        default=[],
        help="Additional include directories",
    )
    parser.add_argument(
        "--define",
        "-D",
        action="append",
        default=[],
        help="Preprocessor definitions",
    )
    parser.add_argument(
        "--cxx",
        action="store_true",
        help="Compile as C++ (use cosmoc++)",
    )
    parser.add_argument(
        "--shim",
        action="store_true",
        help="Link with shim for multi-phase init (PEP 489) extensions",
    )
    parser.add_argument(
        "--cosmo-root",
        help="Path to Cosmopolitan toolchain root (auto-detected from cosmocc)",
    )
    parser.add_argument(
        "--arch",
        default="x86_64",
        choices=["x86_64", "aarch64"],
        help="Target architecture (default: x86_64)",
    )
    parser.add_argument(
        "--load-address",
        default="0x7f0000000000",
        help="Load address for relocations (default: 0x7f0000000000)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Find Cosmopolitan toolchain
    # For ARM64, we need to use the architecture-specific compiler wrapper
    # aarch64-unknown-cosmo-cc handles include paths properly (unlike aarch64-linux-cosmo-cc)
    if args.arch == "aarch64":
        compiler_suffix = "aarch64-unknown-cosmo-"
        compiler_name = compiler_suffix + ("c++" if args.cxx else "cc")
    else:
        # x86_64: use cosmocc/cosmoc++ which produces fat binaries
        compiler_name = "cosmoc++" if args.cxx else "cosmocc"
    compiler = find_tool(compiler_name)
    if not compiler:
        print(f"Error: Could not find {compiler_name}", file=sys.stderr)
        sys.exit(1)

    assert compiler is not None  # verified above
    cosmo_root: Path
    if args.cosmo_root:
        cosmo_root = Path(args.cosmo_root)
    else:
        cosmo_root = find_cosmo_root(compiler)
    if not cosmo_root.exists():
        print(f"Error: Cosmopolitan root not found: {cosmo_root}", file=sys.stderr)
        sys.exit(1)

    linker = find_linker(cosmo_root, args.arch)
    if not linker:
        print(f"Error: Could not find linker for {args.arch}", file=sys.stderr)
        sys.exit(1)

    assert linker is not None  # verified above

    python_path = Path(args.python).resolve()
    if not python_path.exists():
        print(f"Error: Python binary not found: {python_path}", file=sys.stderr)
        sys.exit(1)

    # Get Python include dirs
    py_includes = get_python_includes(python_path)
    all_includes = py_includes + [Path(p) for p in args.include]

    if args.verbose:
        print(f"Cosmopolitan root: {cosmo_root}")
        print(f"Compiler: {compiler}")
        print(f"Linker: {linker}")
        print(f"Python: {python_path}")
        print(f"Includes: {all_includes}")

    # Create temp dir - keep it for debugging if verbose
    tmpdir = Path(tempfile.mkdtemp(prefix="cosmoext_"))
    if args.verbose:
        print(f"Temp directory: {tmpdir}")

    try:
        object_files: list[Path] = []

        # Process each source file
        for src in args.source:
            src_path = Path(src).resolve()
            if not src_path.exists():
                print(f"Error: Source file not found: {src_path}", file=sys.stderr)
                sys.exit(1)

            if src_path.suffix == ".o":
                # Already compiled - just use it
                object_files.append(src_path)
            elif src_path.suffix in (".c", ".cpp", ".cc", ".cxx"):
                # Compile it
                obj_path = tmpdir / (src_path.stem + ".o")

                cmd: list[str | Path] = [
                    compiler,
                    "-c",
                    "-fno-stack-protector",
                ]
                # Architecture-specific flags
                if args.arch == "aarch64":
                    # ARM64: -mcmodel=large without -fPIC (GCC doesn't support both together)
                    # aarch64-unknown-cosmo-cc wrapper handles -nostdinc and -isystem
                    cmd.append("-mcmodel=large")
                else:
                    # x86_64: both -fPIC and -mcmodel=large work together
                    cmd.extend(["-fPIC", "-mcmodel=large"])

                # User includes
                for inc in all_includes:
                    cmd.extend(["-I", inc])

                for define in args.define:
                    cmd.extend(["-D", define])

                cmd.extend(["-o", obj_path, src_path])

                if args.verbose:
                    print(f"Compiling {src_path.name}...")
                run_cmd(cmd, args.verbose)
                object_files.append(obj_path)
            else:
                print(f"Warning: Unknown file type, skipping: {src_path}", file=sys.stderr)

        # Compile shim if requested
        if args.shim:
            if not SHIM_SOURCE.exists():
                print(f"Error: Shim source not found: {SHIM_SOURCE}", file=sys.stderr)
                sys.exit(1)

            shim_obj = tmpdir / "cosmoext_shim.o"
            cmd = [
                compiler,
                "-c",
                "-fno-stack-protector",
            ]
            if args.arch == "aarch64":
                cmd.append("-mcmodel=large")
            else:
                cmd.extend(["-fPIC", "-mcmodel=large"])
            for inc in all_includes:
                cmd.extend(["-I", inc])
            cmd.extend(["-o", shim_obj, SHIM_SOURCE])

            if args.verbose:
                print("Compiling shim...")
            run_cmd(cmd, args.verbose)
            object_files.append(shim_obj)

        # Initial link to combine object files
        combined_obj = tmpdir / "combined.o"
        if len(object_files) > 1:
            cmd = [linker, "-r", "-o", combined_obj, *object_files]
            if args.verbose:
                print("Linking objects...")
            run_cmd(cmd, args.verbose)
        else:
            combined_obj = object_files[0]

        # Check if we need libc stubs (functions not exported from python.com)
        undefined = get_undefined_symbols(combined_obj)
        needs_stubs = bool(undefined & STUB_SYMBOLS)

        if needs_stubs and LIBC_STUBS.exists():
            if args.verbose:
                missing = undefined & STUB_SYMBOLS
                print(f"Adding libc stubs for: {missing}")

            # Compile the stubs
            stubs_obj = tmpdir / "libc_stubs.o"
            cmd = [
                compiler,
                "-c",
                "-fno-stack-protector",
            ]
            if args.arch == "aarch64":
                cmd.append("-mcmodel=large")
            else:
                cmd.extend(["-fPIC", "-mcmodel=large"])
            cmd.extend(["-o", stubs_obj, LIBC_STUBS])
            run_cmd(cmd, args.verbose)

            # Re-link with stubs
            new_combined = tmpdir / "combined_with_stubs.o"
            cmd = [linker, "-r", "-o", new_combined, combined_obj, stubs_obj]
            if args.verbose:
                print("Linking with libc stubs...")
            run_cmd(cmd, args.verbose)
            combined_obj = new_combined

        # Run relocate.py to create .cosmoext
        if not RELOCATE_PY.exists():
            print(f"Error: relocate.py not found: {RELOCATE_PY}", file=sys.stderr)
            sys.exit(1)

        cmd = [
            sys.executable,
            RELOCATE_PY,
            combined_obj,
            "--symtab",
            python_path,
            "--output",
            args.output,
            "--load-address",
            args.load_address,
        ]
        if args.verbose:
            cmd.append("--verbose")
            print("Creating .cosmoext...")

        # relocate.py needs pyelftools - try to run it
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # Maybe pyelftools not installed - try with uv
            if "pyelftools" in result.stderr or "No module named" in result.stderr:
                if args.verbose:
                    print("Retrying with uv run...")
                cmd = [
                    "uv",
                    "run",
                    "--with",
                    "pyelftools",
                    "python",
                    str(RELOCATE_PY),
                    str(combined_obj),
                    "--symtab",
                    str(python_path),
                    "--output",
                    args.output,
                    "--load-address",
                    args.load_address,
                ]
                if args.verbose:
                    cmd.append("--verbose")
                result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print("Error creating .cosmoext:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print(result.stdout)

        output_path = Path(args.output)
        if output_path.exists():
            size = output_path.stat().st_size
            print(f"Created {args.output} ({size:,} bytes)")
        else:
            print("Error: Output file not created", file=sys.stderr)
            sys.exit(1)

    finally:
        # Clean up temp directory
        import shutil

        if not args.verbose:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"Temp directory retained: {tmpdir}")


if __name__ == "__main__":
    main()
