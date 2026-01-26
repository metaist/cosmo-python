#!/usr/bin/env python3
"""Combine x86_64 and aarch64 .cosmoext files into a fat binary.

Usage:
    combine-fat.py --x86_64 foo-x86.cosmoext --aarch64 foo-arm.cosmoext -o foo.cosmoext
    combine-fat.py --x86_64 foo-x86.cosmoext -o foo.cosmoext  # x86_64 only is fine

This reads the architecture-specific payloads from existing .cosmoext files
and combines them into a single fat binary.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

COSMOEXT_MAGIC = b"CEXT"
COSMOEXT_VERSION = 7
COSMOEXT_FAT_HAS_X86_64 = 0x1
COSMOEXT_FAT_HAS_AARCH64 = 0x2
FAT_HEADER_FMT = "<4sIIIQQQQ"  # spell-checker: disable-line


def read_fat_header(data: bytes) -> dict:
    """Read and parse a fat header."""
    if len(data) < 48:
        raise ValueError("File too small for fat header")

    magic, version, flags, reserved, x86_64_offset, x86_64_size, aarch64_offset, aarch64_size = struct.unpack(
        FAT_HEADER_FMT, data[:48]
    )

    if magic != COSMOEXT_MAGIC:
        raise ValueError(f"Invalid magic: {magic}")
    if version != COSMOEXT_VERSION:
        raise ValueError(f"Unsupported version: {version}")

    return {
        "flags": flags,
        "x86_64_offset": x86_64_offset,
        "x86_64_size": x86_64_size,
        "aarch64_offset": aarch64_offset,
        "aarch64_size": aarch64_size,
    }


def extract_payload(data: bytes, offset: int, size: int) -> bytes:
    """Extract a payload from a fat binary."""
    if offset == 0 or size == 0:
        return b""
    return data[offset : offset + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Combine .cosmoext files into a fat binary")
    parser.add_argument("--x86_64", "-x", type=Path, help="x86_64 .cosmoext file")
    parser.add_argument("--aarch64", "-a", type=Path, help="aarch64 .cosmoext file")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output fat .cosmoext file")
    args = parser.parse_args()

    if not args.x86_64 and not args.aarch64:
        parser.error("At least one of --x86_64 or --aarch64 is required")

    x86_64_payload = b""
    aarch64_payload = b""

    # Read x86_64 payload
    if args.x86_64:
        if not args.x86_64.exists():
            print(f"Error: {args.x86_64} not found", file=sys.stderr)
            return 1
        data = args.x86_64.read_bytes()
        header = read_fat_header(data)
        if header["flags"] & COSMOEXT_FAT_HAS_X86_64:
            x86_64_payload = extract_payload(data, header["x86_64_offset"], header["x86_64_size"])
            print(f"x86_64: {len(x86_64_payload)} bytes from {args.x86_64}")
        else:
            print(f"Warning: {args.x86_64} does not contain x86_64 payload", file=sys.stderr)

    # Read aarch64 payload
    if args.aarch64:
        if not args.aarch64.exists():
            print(f"Error: {args.aarch64} not found", file=sys.stderr)
            return 1
        data = args.aarch64.read_bytes()
        header = read_fat_header(data)
        if header["flags"] & COSMOEXT_FAT_HAS_AARCH64:
            aarch64_payload = extract_payload(data, header["aarch64_offset"], header["aarch64_size"])
            print(f"aarch64: {len(aarch64_payload)} bytes from {args.aarch64}")
        else:
            print(f"Warning: {args.aarch64} does not contain aarch64 payload", file=sys.stderr)

    if not x86_64_payload and not aarch64_payload:
        print("Error: No valid payloads found", file=sys.stderr)
        return 1

    # Build fat header
    header_size = 48
    x86_64_offset = header_size if x86_64_payload else 0
    x86_64_size = len(x86_64_payload)
    aarch64_offset = (header_size + x86_64_size) if aarch64_payload else 0
    aarch64_size = len(aarch64_payload)

    flags = 0
    if x86_64_payload:
        flags |= COSMOEXT_FAT_HAS_X86_64
    if aarch64_payload:
        flags |= COSMOEXT_FAT_HAS_AARCH64

    header = struct.pack(
        FAT_HEADER_FMT,
        COSMOEXT_MAGIC,
        COSMOEXT_VERSION,
        flags,
        0,  # reserved
        x86_64_offset,
        x86_64_size,
        aarch64_offset,
        aarch64_size,
    )

    # Write output
    with open(args.output, "wb") as f:
        f.write(header)
        if x86_64_payload:
            f.write(x86_64_payload)
        if aarch64_payload:
            f.write(aarch64_payload)

    total_size = header_size + x86_64_size + aarch64_size
    print(f"Output: {args.output} ({total_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
