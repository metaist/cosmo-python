#!/usr/bin/env python3
"""Extract and parse symbol tables from Cosmopolitan APE binaries.

The symbol table is stored in the APE's zip directory as `.symtab.{arch}`.

Format (from cosmopolitan/libc/runtime/symbols.internal.h):

    struct SymbolTable {
        uint32_t magic;            // 0x544D5953 "SYMT"
        uint32_t abi;              // 1
        uint64_t count;            // number of symbols
        uint64_t size;             // file size
        uint64_t mapsize;          // of this object
        int64_t addr_base;         // IMAGE_BASE_VIRTUAL
        int64_t addr_end;          // _end - 1
        uint64_t names_ptr;        // (pointer, ignored in file)
        uint64_t name_base_ptr;    // (pointer, ignored in file)
        uint32_t names_offset;     // offset to name index array
        uint32_t name_base_offset; // offset to name strings
        struct Symbol symbols[];   // sorted, non-overlapping
    };

    struct Symbol {
        uint32_t x;  // start address (relative to addr_base)
        uint32_t y;  // end address inclusive (relative to addr_base)
    };

Usage:
    # As library
    from symtab import SymbolTable
    st = SymbolTable.from_ape("python.com", arch="amd64")
    addr = st.lookup("PyModule_Create2")

    # As CLI
    ./symtab.py python.com --filter PyModule --arch amd64
"""

from __future__ import annotations

import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

SYMBOLS_MAGIC = 0x544D5953  # "SYMT"
SYMBOLS_ABI = 1


@dataclass
class Symbol:
    """A symbol with name and address range."""

    name: str
    start: int  # Absolute address
    end: int  # Absolute address (inclusive)

    @property
    def size(self) -> int:
        return self.end - self.start + 1


@dataclass
class SymbolTable:
    """Parsed symbol table from a Cosmopolitan binary."""

    arch: str
    addr_base: int
    addr_end: int
    symbols: list[Symbol]
    _by_name: dict[str, Symbol] | None = None

    @property
    def by_name(self) -> dict[str, Symbol]:
        """Lazy-build name lookup dict."""
        if self._by_name is None:
            self._by_name = {s.name: s for s in self.symbols}
        return self._by_name

    def lookup(self, name: str) -> int | None:
        """Look up a symbol by name, return its start address or None."""
        sym = self.by_name.get(name)
        return sym.start if sym else None

    def lookup_fuzzy(self, pattern: str) -> list[Symbol]:
        """Find symbols containing pattern (case-insensitive)."""
        pattern = pattern.lower()
        return [s for s in self.symbols if pattern in s.name.lower()]

    @classmethod
    def from_ape(cls, path: str | Path, arch: str = "amd64") -> SymbolTable:
        """Extract and parse symbol table from an APE binary."""
        data = Path(path).read_bytes()
        symtab_data = _extract_symtab_from_ape(data, arch)
        if symtab_data is None:
            raise ValueError(f"No .symtab.{arch} found in {path}")
        return _parse_symtab(symtab_data, arch)

    @classmethod
    def from_bytes(cls, data: bytes, arch: str = "amd64") -> SymbolTable:
        """Parse symbol table from raw bytes."""
        return _parse_symtab(data, arch)


def _extract_symtab_from_ape(data: bytes, arch: str) -> bytes | None:
    """Extract .symtab.{arch} from APE zip directory."""
    # Search for ZIP local file headers containing .symtab
    pk_sig = b"PK\x03\x04"
    target_name = f".symtab.{arch}".encode()
    offset = 0

    while True:
        pos = data.find(pk_sig, offset)
        if pos == -1:
            break

        try:
            # Parse local file header
            header = data[pos + 4 : pos + 30]
            if len(header) < 26:
                offset = pos + 1
                continue

            (
                version,
                flags,
                compression,
                mtime,
                mdate,
                crc,
                comp_size,
                uncomp_size,
                name_len,
                extra_len,
            ) = struct.unpack("<HHHHHLLLHH", header)

            filename_start = pos + 30
            filename = data[filename_start : filename_start + name_len]

            if filename == target_name:
                data_start = filename_start + name_len + extra_len
                compressed_data = data[data_start : data_start + comp_size]

                if compression == 0:  # Stored
                    return compressed_data
                elif compression == 8:  # Deflate
                    return zlib.decompress(compressed_data, -zlib.MAX_WBITS)
                else:
                    raise ValueError(f"Unknown compression method: {compression}")

        except (struct.error, zlib.error):
            pass

        offset = pos + 1

    return None


def _parse_symtab(data: bytes, arch: str) -> SymbolTable:
    """Parse binary symbol table data."""
    if len(data) < 72:
        raise ValueError(f"Symbol table too small: {len(data)} bytes")

    # Parse header
    header_fmt = "<II QQQ qq QQ II"
    header_size = struct.calcsize(header_fmt)

    (
        magic,
        abi,
        count,
        size,
        mapsize,
        addr_base,
        addr_end,
        names_ptr,
        name_base_ptr,
        names_offset,
        name_base_offset,
    ) = struct.unpack(header_fmt, data[:header_size])

    if magic != SYMBOLS_MAGIC:
        raise ValueError(f"Bad magic: 0x{magic:08X} (expected 0x{SYMBOLS_MAGIC:08X})")

    if abi != SYMBOLS_ABI:
        raise ValueError(f"Unsupported ABI: {abi} (expected {SYMBOLS_ABI})")

    # Parse symbols
    symbols = []
    symbol_fmt = "<II"
    symbol_size = struct.calcsize(symbol_fmt)

    for i in range(count):
        # Get address range
        sym_off = header_size + i * symbol_size
        x, y = struct.unpack(symbol_fmt, data[sym_off : sym_off + symbol_size])

        # Get name
        name_idx_off = names_offset + i * 4
        name_off = struct.unpack("<I", data[name_idx_off : name_idx_off + 4])[0]

        name_start = name_base_offset + name_off
        name_end = data.find(b"\x00", name_start)
        if name_end == -1:
            name_end = len(data)
        name = data[name_start:name_end].decode("utf-8", errors="replace")

        symbols.append(
            Symbol(
                name=name,
                start=addr_base + x,
                end=addr_base + y,
            )
        )

    return SymbolTable(
        arch=arch,
        addr_base=addr_base,
        addr_end=addr_end,
        symbols=symbols,
    )


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract symbols from APE binary")
    parser.add_argument("ape_file", help="Path to python.com or other APE binary")
    parser.add_argument(
        "--arch",
        default="amd64",
        choices=["amd64", "arm64"],
        help="Architecture (default: amd64)",
    )
    parser.add_argument("--filter", help="Filter symbols by pattern (case-insensitive)")
    parser.add_argument(
        "--stats", action="store_true", help="Show statistics instead of symbol list"
    )
    parser.add_argument("--limit", type=int, default=100, help="Max symbols to show")

    args = parser.parse_args()

    try:
        st = SymbolTable.from_ape(args.ape_file, args.arch)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Symbol table: {args.ape_file} ({args.arch})")
    print(f"  Base address: 0x{st.addr_base:012x}")
    print(f"  End address:  0x{st.addr_end:012x}")
    print(f"  Total symbols: {len(st.symbols)}")

    if args.stats:
        # Count by category
        py_public = sum(1 for s in st.symbols if s.name.startswith("Py"))
        py_private = sum(1 for s in st.symbols if s.name.startswith("_Py"))
        print(f"\n  Python public (Py*):  {py_public}")
        print(f"  Python private (_Py*): {py_private}")
        return 0

    # Filter and display
    symbols = st.symbols
    if args.filter:
        symbols = st.lookup_fuzzy(args.filter)
        print(f"\n  Matching '{args.filter}': {len(symbols)}")

    print()
    for s in symbols[: args.limit]:
        print(f"  0x{s.start:012x}  {s.name}")

    if len(symbols) > args.limit:
        print(f"  ... and {len(symbols) - args.limit} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
