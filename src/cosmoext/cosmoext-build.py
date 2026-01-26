#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyelftools>=0.31"]
# ///
from __future__ import annotations

import argparse
import shutil
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
# Symbols that need stubs because they're NOT exported in python.com's symtab.
# Note: The exact set of exported symbols varies by python.com build. These are
# commonly needed libc functions that may or may not be exported.
STUB_SYMBOLS = {
    "iscntrl",
    "ispunct",
    "isspace",
    "memmove",
    "memcpy",
    "isalnum",
    "isupper",
    "tolower",
    "toupper",
    "ceil",
    "Py_Version",  # Needed by Cython-generated code
    # String conversion functions needed by libcxx
    "strtod",
    "strtol",
    "strtoll",
    "strtoull",
    "strtof",
    "strtold",
    # Wide character functions needed by libcxx
    "wcslen",
    "wcstol",
    "wcstoull",
    "wcstod",
    "wcstof",
    "wcstold",
    "swprintf",
    # C++ ABI functions
    "__cxa_call_terminate",
    "_ZNSt20bad_array_new_lengthC1Ev",
    "_ZNSt9bad_allocC1Ev",
    # C++ exception class stubs
    "_ZNSt12out_of_rangeD1Ev",
    "_ZNSt16invalid_argumentD1Ev",
    "_ZTISt12out_of_range",
    "_ZTISt16invalid_argument",
    "_ZTVSt12out_of_range",
    "_ZTVSt16invalid_argument",
    # Rust runtime stubs
    "bcmp",
    "posix_memalign",
    "__xpg_strerror_r",
    "dl_iterate_phdr",
    "_Unwind_Backtrace",
    "_Unwind_GetDataRelBase",
    "_Unwind_GetTextRelBase",
    "_Unwind_GetIP",
    "_Unwind_GetIPInfo",
    "_Unwind_GetLanguageSpecificData",
    "_Unwind_GetRegionStart",
    "_Unwind_SetGR",
    "_Unwind_SetIP",
}


def find_tool(name: str, search_paths: list[Path] | None = None) -> Path | None:
    """Find a tool by name in common locations."""
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


def find_libcxx_large(arch: str = "x86_64", auto_build: bool = True) -> Path | None:
    """Find our custom libcxx-large.a built with -mcmodel=large.

    These are required for C++ extensions because the standard libcxx.a
    uses PC32/PLT32 relocations that aren't compatible with our loader.

    Args:
        arch: Target architecture (x86_64 or aarch64)
        auto_build: If True and archives don't exist, try to build them

    Returns:
        Path to libcxx-large archive, or None if not found/buildable
    """
    # Look in src/cosmoext/lib/ relative to this script
    script_dir = Path(__file__).parent
    libcxx = script_dir / "lib" / f"libcxx-large-{arch}.a"
    if libcxx.exists():
        return libcxx

    if not auto_build:
        return None

    # Try to build the archives using scripts/libcxx-large.sh
    # Find the scripts directory (../../scripts from src/cosmoext/)
    repo_root = script_dir.parent.parent
    build_script = repo_root / "scripts" / "libcxx-large.sh"

    if not build_script.exists():
        print(
            "  Warning: libcxx-large archives not found and build script missing",
            file=sys.stderr,
        )
        print(f"  Expected: {libcxx}", file=sys.stderr)
        print("  Build with: ./scripts/libcxx-large.sh", file=sys.stderr)
        return None

    print("  Building libcxx-large archives (this may take a few minutes)...")
    result = subprocess.run(
        [str(build_script)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("  Failed to build libcxx-large archives:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return None

    # Check if it exists now
    if libcxx.exists():
        print(f"  Built: {libcxx}")
        return libcxx

    return None


def find_libcxx(cosmo_root: Path, arch: str = "x86_64") -> Path | None:
    """Find libcxx.a for the given architecture.

    Prefers our custom libcxx-large.a if available.
    """
    # First try our custom -mcmodel=large version
    libcxx_large = find_libcxx_large(arch)
    if libcxx_large:
        return libcxx_large

    # Fall back to standard libcxx.a (won't work for most C++ code)
    triple = f"{arch}-linux-cosmo"
    libcxx = cosmo_root / triple / "lib" / "libcxx.a"
    if libcxx.exists():
        return libcxx
    return None


def has_cpp_symbols(obj_path: Path, nm_path: Path | None = None) -> bool:
    """Check if an object file has C++ mangled symbols (needs libcxx)."""
    nm = nm_path or find_tool("nm")
    if not nm:
        return False

    result = run_cmd([nm, "-u", obj_path], check=False, capture=True)
    if result.returncode != 0:
        return False

    # Look for C++ mangled symbols (start with _Z) that are from libcxx
    # These include things like std::sort, std::string methods, etc.
    for line in result.stdout.strip().split("\n"):
        parts = line.split()
        if len(parts) >= 1:
            sym = parts[-1]
            # C++ mangled names start with _Z (Itanium ABI) or _ZN (namespace)
            # Specifically look for std:: symbols (_ZNSt or _ZSt)
            if sym.startswith("_ZNSt") or sym.startswith("_ZSt"):
                return True
            # Also check for operator new/delete variants we might need
            if sym.startswith("_Znw") or sym.startswith("_Zna"):  # new
                return True
            if sym.startswith("_Zdl") or sym.startswith("_Zda"):  # delete
                return True
    return False


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
        default=None,
        choices=["x86_64", "aarch64"],
        help="Build single arch only (for debugging); default builds both if available",
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
    # Always use cosmocc/cosmoc++ which produces fat binaries (both x86_64 and aarch64)
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

    # Find linkers - for fat builds we need both x86_64 and aarch64
    linker_x86_64 = find_linker(cosmo_root, "x86_64")
    linker_aarch64 = find_linker(cosmo_root, "aarch64")

    if args.arch == "aarch64":
        linker = linker_aarch64
        if not linker:
            print("Error: Could not find linker for aarch64", file=sys.stderr)
            sys.exit(1)
    else:
        linker = linker_x86_64
        if not linker:
            print("Error: Could not find linker for x86_64", file=sys.stderr)
            sys.exit(1)

    assert linker is not None  # verified above

    # For fat builds, we need both linkers
    build_fat = args.arch is None and linker_aarch64 is not None

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
                # Already compiled - use as-is (relocate.py will find .aarch64/ version)
                object_files.append(src_path)
            elif src_path.suffix in (".c", ".cpp", ".cc", ".cxx"):
                # Compile it
                obj_path = tmpdir / (src_path.stem + ".o")

                cmd: list[str | Path] = [
                    compiler,
                    "-c",
                    "-fno-stack-protector",
                    "-fPIC",
                    "-mcmodel=large",
                ]

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

            # Compile the stubs (always use C compiler, not C++)
            stubs_obj = tmpdir / "libc_stubs.o"
            c_compiler = find_tool("cosmocc")
            if not c_compiler:
                print("Error: cosmocc not found for compiling libc stubs", file=sys.stderr)
                sys.exit(1)
            assert c_compiler is not None  # for type checker
            stubs_cmd: list[str | Path] = [
                c_compiler,
                "-c",
                "-fno-stack-protector",
            ]
            if args.arch == "aarch64":
                stubs_cmd.append("-mcmodel=large")
            else:
                stubs_cmd.extend(["-fPIC", "-mcmodel=large"])
            stubs_cmd.extend(["-o", stubs_obj, LIBC_STUBS])
            run_cmd(stubs_cmd, args.verbose)

            # Re-link with stubs
            # cosmocc creates both x86_64 (main) and aarch64 (.aarch64/) versions
            # Use the appropriate one for the target architecture
            if args.arch == "aarch64":
                stubs_obj_for_link = tmpdir / ".aarch64" / "libc_stubs.o"
            else:
                stubs_obj_for_link = stubs_obj
            new_combined = tmpdir / "combined_with_stubs.o"
            cmd = [linker, "-r", "-o", new_combined, combined_obj, stubs_obj_for_link]
            if args.verbose:
                print("Linking with libc stubs...")
            run_cmd(cmd, args.verbose)
            combined_obj = new_combined

        # Check if we need libcxx (C++ standard library)
        # This is needed for C++ extensions that use STL templates
        needs_libcxx = args.cxx and has_cpp_symbols(combined_obj)
        if needs_libcxx:
            arch = args.arch or "x86_64"
            libcxx = find_libcxx(cosmo_root, arch)
            if libcxx:
                if args.verbose:
                    print("Linking with libcxx.a for C++ STL support...")

                # Link against libcxx.a to resolve C++ standard library symbols
                # Don't use --whole-archive; let linker pull only what's needed
                new_combined = tmpdir / "combined_with_libcxx.o"
                cmd = [
                    linker,
                    "-r",
                    "-o",
                    new_combined,
                    combined_obj,
                    libcxx,
                ]
                run_cmd(cmd, args.verbose)
                combined_obj = new_combined
            else:
                if args.verbose:
                    print(f"Warning: libcxx.a not found for {arch}, C++ STL may not work")

        # For fat builds, also link aarch64 objects
        if build_fat:
            assert linker_aarch64 is not None  # build_fat implies linker_aarch64 exists
            aarch64_dir = tmpdir / ".aarch64"
            aarch64_dir.mkdir(exist_ok=True)

            # Find aarch64 versions of all object files
            aarch64_objects: list[Path] = []
            for obj in object_files:
                if obj.parent == tmpdir:
                    # Objects we compiled - aarch64 version is in .aarch64/ subdir
                    aarch64_obj = tmpdir / ".aarch64" / obj.name
                else:
                    # External objects - look in .aarch64/ relative to the object
                    aarch64_obj = obj.parent / ".aarch64" / obj.name
                if aarch64_obj.exists():
                    aarch64_objects.append(aarch64_obj)

            if aarch64_objects:
                if args.verbose:
                    print(f"Linking aarch64 objects ({len(aarch64_objects)} files)...")

                # Link aarch64 objects
                aarch64_combined = aarch64_dir / "combined.o"
                if len(aarch64_objects) > 1:
                    cmd = [linker_aarch64, "-r", "-o", aarch64_combined, *aarch64_objects]
                    run_cmd(cmd, args.verbose)
                else:
                    aarch64_combined = aarch64_objects[0]

                # Add stubs if needed (stubs were already compiled for both archs by cosmocc)
                aarch64_stubs = aarch64_dir / "libc_stubs.o"
                aarch64_final = aarch64_combined
                if needs_stubs and aarch64_stubs.exists():
                    aarch64_with_stubs = aarch64_dir / "combined_with_stubs.o"
                    cmd = [
                        linker_aarch64,
                        "-r",
                        "-o",
                        aarch64_with_stubs,
                        aarch64_combined,
                        aarch64_stubs,
                    ]
                    if args.verbose:
                        print("Linking aarch64 with libc stubs...")
                    run_cmd(cmd, args.verbose)
                    aarch64_final = aarch64_with_stubs

                # Add libcxx if needed for C++ STL support
                if needs_libcxx:
                    libcxx_aarch64 = find_libcxx(cosmo_root, "aarch64")
                    if libcxx_aarch64:
                        if args.verbose:
                            print("Linking aarch64 with libcxx.a...")
                        aarch64_with_libcxx = aarch64_dir / "combined_with_libcxx.o"
                        cmd = [
                            linker_aarch64,
                            "-r",
                            "-o",
                            aarch64_with_libcxx,
                            aarch64_final,
                            libcxx_aarch64,
                        ]
                        run_cmd(cmd, args.verbose)
                        aarch64_final = aarch64_with_libcxx

                # Ensure final object is at expected location for relocate.py
                expected_path = aarch64_dir / "combined_with_stubs.o"
                if aarch64_final != expected_path:
                    shutil.copy(aarch64_final, expected_path)
            else:
                if args.verbose:
                    print("Note: No aarch64 objects found, building x86_64 only")

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
        if args.arch:
            cmd.extend(["--arch", args.arch])
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
                if args.arch:
                    cmd.extend(["--arch", args.arch])
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
        if not args.verbose:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"Temp directory retained: {tmpdir}")


if __name__ == "__main__":
    main()
