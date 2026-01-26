#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyelftools>=0.31"]
# ///
"""Parse ELF relocations and apply them to create a loadable blob.

This is the core of the cosmoext build process:
1. Parse the object file's sections and relocations
2. Validate external symbols against the target binary's symbol table
3. Apply internal relocations to produce position-dependent code
4. Output a blob with external symbol names for runtime resolution

Usage:
    ./relocate.py testmod.o --symtab python.com --output testmod.cosmoext
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.sections import SymbolTableSection

# x86_64 relocation types we handle
R_X86_64_NONE = 0
R_X86_64_64 = 1  # S + A (64-bit absolute)
R_X86_64_PC32 = 2  # S + A - P (32-bit PC-relative)
R_X86_64_PLT32 = 4  # L + A - P (32-bit PLT-relative, same as PC32 for us)
R_X86_64_32 = 10  # S + A (32-bit absolute, zero-extended)
R_X86_64_32S = 11  # S + A (32-bit absolute, sign-extended)

# ARM64 (AArch64) relocation types
R_AARCH64_NONE = 0
R_AARCH64_ABS64 = 257  # S + A (64-bit absolute)
R_AARCH64_CALL26 = 283  # S + A - P (26-bit PC-relative call)
R_AARCH64_JUMP26 = 282  # S + A - P (26-bit PC-relative jump)
R_AARCH64_ADR_PREL_PG_HI21 = 275  # Page(S + A) - Page(P) (ADRP)
R_AARCH64_ADD_ABS_LO12_NC = 277  # S + A (low 12 bits, no check)
R_AARCH64_LDST8_ABS_LO12_NC = 278  # S + A (low 12 bits for 8-bit load/store)
R_AARCH64_LDST16_ABS_LO12_NC = 284  # S + A (low 12 bits for 16-bit load/store)
R_AARCH64_LDST32_ABS_LO12_NC = 285  # S + A (low 12 bits for 32-bit load/store)
R_AARCH64_LDST64_ABS_LO12_NC = 286  # S + A (low 12 bits for 64-bit load/store)
R_AARCH64_LDST128_ABS_LO12_NC = 299  # S + A (low 12 bits for 128-bit load/store, SIMD)
R_AARCH64_ADR_GOT_PAGE = 311  # Page(G(S)) - Page(P) (GOT page)

# MOVW absolute relocations for large code model (used by Rust with -C code-model=large)
R_AARCH64_MOVW_UABS_G0_NC = 264  # S + A, bits 0-15, no overflow check
R_AARCH64_MOVW_UABS_G1_NC = 266  # S + A, bits 16-31, no overflow check
R_AARCH64_MOVW_UABS_G2_NC = 268  # S + A, bits 32-47, no overflow check
R_AARCH64_MOVW_UABS_G3 = 269  # S + A, bits 48-63
R_AARCH64_LD64_GOT_LO12_NC = 312  # G(S) (low 12 bits of GOT entry)
R_AARCH64_PREL32 = 261  # S + A - P (32-bit PC-relative)

# TLS (Thread-Local Storage) relocation types - Local Exec model
# x86_64
R_X86_64_TPOFF32 = 23  # S + A (32-bit offset from thread pointer)

# ARM64 TLS Local Exec (TLSLE) - uses TP register directly
R_AARCH64_TLSLE_ADD_TPREL_HI12 = 549  # TP-relative, high 12 bits for ADD
R_AARCH64_TLSLE_ADD_TPREL_LO12_NC = 551  # TP-relative, low 12 bits for ADD (binutils uses 551)

RELOC_NAMES_X86_64 = {
    R_X86_64_NONE: "R_X86_64_NONE",
    R_X86_64_64: "R_X86_64_64",
    R_X86_64_PC32: "R_X86_64_PC32",
    R_X86_64_PLT32: "R_X86_64_PLT32",
    R_X86_64_32: "R_X86_64_32",
    R_X86_64_32S: "R_X86_64_32S",
    R_X86_64_TPOFF32: "R_X86_64_TPOFF32",
}

RELOC_NAMES_AARCH64 = {
    R_AARCH64_NONE: "R_AARCH64_NONE",
    R_AARCH64_ABS64: "R_AARCH64_ABS64",
    R_AARCH64_CALL26: "R_AARCH64_CALL26",
    R_AARCH64_JUMP26: "R_AARCH64_JUMP26",
    R_AARCH64_ADR_PREL_PG_HI21: "R_AARCH64_ADR_PREL_PG_HI21",
    R_AARCH64_ADD_ABS_LO12_NC: "R_AARCH64_ADD_ABS_LO12_NC",
    R_AARCH64_LDST8_ABS_LO12_NC: "R_AARCH64_LDST8_ABS_LO12_NC",
    R_AARCH64_LDST16_ABS_LO12_NC: "R_AARCH64_LDST16_ABS_LO12_NC",
    R_AARCH64_LDST32_ABS_LO12_NC: "R_AARCH64_LDST32_ABS_LO12_NC",
    R_AARCH64_LDST64_ABS_LO12_NC: "R_AARCH64_LDST64_ABS_LO12_NC",
    R_AARCH64_LDST128_ABS_LO12_NC: "R_AARCH64_LDST128_ABS_LO12_NC",
    R_AARCH64_PREL32: "R_AARCH64_PREL32",
    R_AARCH64_MOVW_UABS_G0_NC: "R_AARCH64_MOVW_UABS_G0_NC",
    R_AARCH64_MOVW_UABS_G1_NC: "R_AARCH64_MOVW_UABS_G1_NC",
    R_AARCH64_MOVW_UABS_G2_NC: "R_AARCH64_MOVW_UABS_G2_NC",
    R_AARCH64_MOVW_UABS_G3: "R_AARCH64_MOVW_UABS_G3",
    R_AARCH64_TLSLE_ADD_TPREL_HI12: "R_AARCH64_TLSLE_ADD_TPREL_HI12",
    R_AARCH64_TLSLE_ADD_TPREL_LO12_NC: "R_AARCH64_TLSLE_ADD_TPREL_LO12_NC",
}

# ARM64 trampoline: load address from literal pool and branch
# ldr x16, #8  (load from PC+8)
# br x16       (indirect branch)
# .quad 0      (64-bit address placeholder)
ARM64_TRAMPOLINE = bytes(
    [
        0x50,
        0x00,
        0x00,
        0x58,  # ldr x16, #8
        0x00,
        0x02,
        0x1F,
        0xD6,  # br x16
        0x00,
        0x00,
        0x00,
        0x00,  # address low 32 bits
        0x00,
        0x00,
        0x00,
        0x00,  # address high 32 bits
    ]
)
ARM64_TRAMPOLINE_SIZE = 16
ARM64_TRAMPOLINE_ADDR_OFFSET = 8  # offset to the 64-bit address

# ARM64 call/jump range: ±128MB (26 bits * 4 bytes)
ARM64_CALL_RANGE = (1 << 25) * 4


@dataclass
class LoadableSection:
    """A section that will be loaded into the final blob."""

    name: str
    data: bytearray
    offset: int  # Offset in the final blob
    vaddr: int  # Virtual address when loaded
    flags: int
    align: int

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def is_executable(self) -> bool:
        return bool(self.flags & 0x4)  # SHF_EXECINSTR

    @property
    def is_writable(self) -> bool:
        return bool(self.flags & 0x1)  # SHF_WRITE

    @property
    def is_tls(self) -> bool:
        return bool(self.flags & 0x400)  # SHF_TLS


@dataclass
class Relocation:
    """A relocation to apply."""

    offset: int  # Offset within the section
    type: int
    symbol: str
    addend: int
    section: str  # Section this relocation applies to


@dataclass
class InternalRelocation:
    """A relocation that must be applied at load time.

    reloc_type specifies the exact relocation type for architecture-specific
    patching (e.g., ARM64 ADRP/ADD_LO12).
    """

    section_offset: int  # Offset in the blob to patch
    size: int  # 4 or 8 bytes
    target_offset: int  # Target address (relative to load base)
    reloc_type: int = 0  # Relocation type: R_X86_64_*, R_AARCH64_*


@dataclass
class ExternalSymbol:
    """An external symbol that must be resolved at load time."""

    name: str  # Symbol name (e.g., "PyModule_Create2")
    patch_offset: int  # Offset in blob where to write the resolved address


@dataclass
class CosmoExtBlob:
    """The output blob ready for loading."""

    sections: list[LoadableSection]
    init_offset: int  # Offset of PyInit_* function
    total_size: int
    load_address: int  # Address where this was designed to load
    internal_relocs: list[InternalRelocation]  # Relocations to apply at load time
    external_symbols: list[ExternalSymbol] = field(default_factory=list)  # External symbols
    get_def_offset: int = 0  # Offset from init to _cosmoext_get_captured_def (0 if not using shim)

    def write_arch_payload(self, f: BinaryIO) -> None:
        """Write the arch-specific payload (for embedding in v7 fat format).

        Arch payload format (no magic/version - those are in fat header):
        - 8 bytes: load_address
        - 8 bytes: total_size
        - 8 bytes: init_offset
        - 8 bytes: header_size (where blob data starts, relative to payload start)
        - 8 bytes: num_sections
        - 8 bytes: num_internal_relocs
        - 8 bytes: num_external_symbols
        - 8 bytes: string_table_size
        - 8 bytes: get_def_offset
        - Section headers (24 bytes each)
        - Relocation table (24 bytes each)
        - External symbol table (16 bytes each)
        - String table
        - Padding to page boundary
        - Section data
        """
        # Build string table
        string_table = bytearray()
        name_offsets: dict[str, int] = {}
        for ext_sym in self.external_symbols:
            if ext_sym.name not in name_offsets:
                name_offsets[ext_sym.name] = len(string_table)
                string_table.extend(ext_sym.name.encode("utf-8"))
                string_table.append(0)  # null terminator

        # Calculate header size (arch header is 72 bytes: 9 * 8)
        arch_header_size = 72
        section_headers_size = len(self.sections) * 24
        reloc_data_size = len(self.internal_relocs) * 24
        external_sym_size = len(self.external_symbols) * 16
        header_total = (
            arch_header_size
            + section_headers_size
            + reloc_data_size
            + external_sym_size
            + len(string_table)
        )
        # Round up to nearest 4096
        header_size = ((header_total + 4095) // 4096) * 4096

        header = struct.pack(
            "<QQQQQQQQQ",  # spell-checker: disable-line
            self.load_address,
            self.total_size,
            self.init_offset,
            header_size,
            len(self.sections),
            len(self.internal_relocs),
            len(self.external_symbols),
            len(string_table),
            self.get_def_offset,
        )

        section_headers = b""
        for sec in self.sections:
            flags = 0
            if sec.is_executable:
                flags |= 1  # COSMOEXT_SECTION_EXEC
            if sec.is_writable:
                flags |= 2  # COSMOEXT_SECTION_WRITE
            if sec.is_tls:
                flags |= 4  # COSMOEXT_SECTION_TLS
            # C struct has 4 bytes padding after flags due to alignment
            section_headers += struct.pack("<QQIxxxx", sec.offset, sec.size, flags)

        reloc_data = b""
        for reloc in self.internal_relocs:
            # Reloc entry: section_offset(8) + reloc_type(4) + size(4) + target_offset(8) = 24 bytes
            reloc_data += struct.pack(
                "<QIIQ",  # spell-checker: disable-line
                reloc.section_offset,
                reloc.reloc_type,
                reloc.size,
                reloc.target_offset,
            )

        external_sym_data = b""
        for ext_sym in self.external_symbols:
            name_off = name_offsets[ext_sym.name]
            external_sym_data += struct.pack("<QIxxxx", ext_sym.patch_offset, name_off)

        # Pad to header_size
        actual_header = (
            len(header)
            + len(section_headers)
            + len(reloc_data)
            + len(external_sym_data)
            + len(string_table)
        )
        padding = header_size - actual_header

        f.write(header)
        f.write(section_headers)
        f.write(reloc_data)
        f.write(external_sym_data)
        f.write(bytes(string_table))
        f.write(b"\x00" * padding)

        # Write section data in offset order, with padding for alignment gaps
        current_offset = 0
        for sec in sorted(self.sections, key=lambda s: s.offset):
            # Add padding if there's a gap
            if sec.offset > current_offset:
                f.write(b"\x00" * (sec.offset - current_offset))
            f.write(bytes(sec.data))
            current_offset = sec.offset + sec.size

    def to_bytes(self) -> bytes:
        """Serialize the arch payload to bytes (for embedding in fat format)."""
        import io

        buf = io.BytesIO()
        self.write_arch_payload(buf)
        return buf.getvalue()


# Flag constants for v7 fat format
COSMOEXT_FAT_HAS_X86_64 = 0x1
COSMOEXT_FAT_HAS_AARCH64 = 0x2


@dataclass
class CosmoExtFatBlob:
    """A fat cosmoext blob containing both x86_64 and aarch64 code.

    Format v7:
    - 4 bytes: magic "CEXT"
    - 4 bytes: version (7)
    - 4 bytes: flags (0x1 = has x86_64, 0x2 = has aarch64)
    - 4 bytes: reserved (0)
    - 8 bytes: x86_64_offset (from start of file, 0 if none)
    - 8 bytes: x86_64_size
    - 8 bytes: aarch64_offset (from start of file, 0 if none)
    - 8 bytes: aarch64_size
    - x86_64 payload (arch-specific blob)
    - aarch64 payload (arch-specific blob)
    """

    x86_64_blob: CosmoExtBlob | None = None
    aarch64_blob: CosmoExtBlob | None = None

    def write(self, f: BinaryIO) -> None:
        """Write the fat blob to a file."""
        # Serialize each blob
        x86_64_data = self.x86_64_blob.to_bytes() if self.x86_64_blob else b""
        aarch64_data = self.aarch64_blob.to_bytes() if self.aarch64_blob else b""

        # Calculate offsets (header is 48 bytes)
        header_size = 48
        x86_64_offset = header_size if x86_64_data else 0
        x86_64_size = len(x86_64_data)
        aarch64_offset = (header_size + x86_64_size) if aarch64_data else 0
        aarch64_size = len(aarch64_data)

        # Build flags
        flags = 0
        if self.x86_64_blob:
            flags |= COSMOEXT_FAT_HAS_X86_64
        if self.aarch64_blob:
            flags |= COSMOEXT_FAT_HAS_AARCH64

        # Write header
        header = struct.pack(
            "<4sIIIQQQQ",  # spell-checker: disable-line
            b"CEXT",
            7,  # version
            flags,
            0,  # reserved
            x86_64_offset,
            x86_64_size,
            aarch64_offset,
            aarch64_size,
        )

        f.write(header)
        if x86_64_data:
            f.write(x86_64_data)
        if aarch64_data:
            f.write(aarch64_data)


def parse_object_file(
    path: Path,
) -> tuple[dict[str, LoadableSection], list[Relocation], dict[str, tuple[str, int]], str]:
    """Parse an ELF object file.

    Returns: (sections, relocations, local_symbols, arch)
    where arch is "x86_64" or "aarch64"
    """

    with open(path, "rb") as f:
        elf = ELFFile(f)

        machine_arch = elf.get_machine_arch()
        if machine_arch == "x64":
            arch = "x86_64"
        elif machine_arch == "AArch64":
            arch = "aarch64"
        else:
            raise ValueError(f"Unsupported architecture: {machine_arch}")

        sections: dict[str, LoadableSection] = {}
        relocations: list[Relocation] = []
        local_symbols: dict[str, tuple[str, int]] = {}  # symbol -> (section_name, offset)

        # First pass: collect sections
        for sec in elf.iter_sections():
            # We care about PROGBITS (code/data) and NOBITS (bss) sections
            if sec["sh_type"] in ("SHT_PROGBITS", "SHT_NOBITS"):
                name = sec.name
                # Skip debug/comment/metadata sections
                if (
                    name.startswith(".debug")
                    or name.startswith(".comment")
                    or name.startswith(".note")
                    or name.startswith("__patchable")
                    or name == ".eh_frame"
                ):
                    continue

                # For NOBITS (bss), create zero-filled data
                if sec["sh_type"] == "SHT_NOBITS":
                    data = bytearray(sec["sh_size"])
                else:
                    data = bytearray(sec.data())

                sections[name] = LoadableSection(
                    name=name,
                    data=data,
                    offset=0,  # Will be computed later
                    vaddr=0,  # Will be computed later
                    flags=sec["sh_flags"],
                    align=sec["sh_addralign"] or 1,
                )

        # Get symbol table
        symtab = elf.get_section_by_name(".symtab")
        if symtab and isinstance(symtab, SymbolTableSection):
            for sym in symtab.iter_symbols():
                if sym.name and sym["st_shndx"] != "SHN_UNDEF":
                    # Get the section this symbol is in
                    if isinstance(sym["st_shndx"], int):
                        sec_idx = sym["st_shndx"]
                        if sec_idx < elf.num_sections():
                            sec = elf.get_section(sec_idx)
                            local_symbols[sym.name] = (sec.name, sym["st_value"])

        # Second pass: collect relocations
        for sec in elf.iter_sections():
            if not isinstance(sec, RelocationSection):
                continue

            # Get the section these relocations apply to
            target_sec_idx = sec["sh_info"]
            target_sec = elf.get_section(target_sec_idx)
            target_name = target_sec.name

            # Skip relocations for sections we're not loading
            if target_name not in sections:
                continue

            # Get the symbol table for this relocation section
            symtab_idx = sec["sh_link"]
            symtab = elf.get_section(symtab_idx)

            for reloc in sec.iter_relocations():
                sym_idx = reloc["r_info_sym"]
                sym = symtab.get_symbol(sym_idx)
                sym_name = sym.name if sym else ""

                # Handle section symbols (empty name, valid st_shndx)
                # These reference a section directly
                if not sym_name and sym and isinstance(sym["st_shndx"], int):
                    sec_idx = sym["st_shndx"]
                    if sec_idx < elf.num_sections():
                        ref_sec = elf.get_section(sec_idx)
                        sym_name = ref_sec.name  # Use section name as symbol name

                relocations.append(
                    Relocation(
                        offset=reloc["r_offset"],
                        type=reloc["r_info_type"],
                        symbol=sym_name,
                        addend=reloc["r_addend"] if reloc.is_RELA() else 0,
                        section=target_name,
                    )
                )

        return sections, relocations, local_symbols, arch


def layout_sections(sections: dict[str, LoadableSection], base_address: int) -> int:
    """Assign offsets and virtual addresses to sections. Returns total size."""

    # Order: .text first (executable), then .rodata, then .data
    order = [".text", ".rodata.str1.1", ".rodata.str1.8", ".data"]
    ordered = []
    for name in order:
        if name in sections:
            ordered.append(sections[name])

    # Add any remaining sections
    for name, sec in sections.items():
        if sec not in ordered:
            ordered.append(sec)

    offset = 0
    for sec in ordered:
        # Align
        if sec.align > 1:
            offset = (offset + sec.align - 1) & ~(sec.align - 1)
        sec.offset = offset
        sec.vaddr = base_address + offset
        offset += sec.size

    return offset


def generate_arm64_trampolines(
    relocations: list[Relocation],
    sections: dict[str, LoadableSection],
    local_symbols: dict[str, tuple[str, int]],
    external_symbols: set[str],
    base_address: int,
    total_size: int,
) -> tuple[bytearray, dict[str, int], dict[str, int]]:
    """Generate ARM64 trampolines for external function calls.

    Returns: (trampoline_data, symbol_to_trampoline_vaddr, symbol_to_patch_offset)
    - symbol_to_trampoline_vaddr: maps symbol to trampoline virtual address
    - symbol_to_patch_offset: maps symbol to offset in blob where address should be patched
    """
    # Find external function calls that need trampolines
    needs_trampoline: set[str] = set()

    for reloc in relocations:
        if reloc.type not in (R_AARCH64_CALL26, R_AARCH64_JUMP26):
            continue
        if not reloc.symbol or reloc.symbol in local_symbols:
            continue
        if reloc.symbol.startswith("."):
            continue
        if reloc.symbol in external_symbols:
            # All external calls need trampolines on ARM64 since we don't know
            # the actual address at build time
            needs_trampoline.add(reloc.symbol)

    if not needs_trampoline:
        return bytearray(), {}, {}

    # Generate trampolines
    # Place them right after the existing sections
    tramp_base = base_address + total_size
    # Align to 16 bytes
    tramp_base = (tramp_base + 15) & ~15
    tramp_blob_offset = tramp_base - base_address

    tramp_data = bytearray()
    tramp_vaddrs: dict[str, int] = {}
    patch_offsets: dict[str, int] = {}

    for sym in sorted(needs_trampoline):
        tramp_vaddr = tramp_base + len(tramp_data)
        tramp_vaddrs[sym] = tramp_vaddr

        # The patch offset is where the 64-bit address lives in the trampoline
        patch_off = tramp_blob_offset + len(tramp_data) + ARM64_TRAMPOLINE_ADDR_OFFSET
        patch_offsets[sym] = patch_off

        # Build trampoline with placeholder address (will be patched at load time)
        tramp = bytearray(ARM64_TRAMPOLINE)
        # Leave address as 0 - loader will fill it in
        tramp_data.extend(tramp)

    return tramp_data, tramp_vaddrs, patch_offsets


def apply_relocations(
    sections: dict[str, LoadableSection],
    relocations: list[Relocation],
    local_symbols: dict[str, tuple[str, int]],
    external_symbols: set[str],
    base_address: int,
    arch: str = "x86_64",
    trampolines: dict[str, int] | None = None,
    symbol_name_map: dict[str, str] | None = None,
    tls_offsets: dict[str, int] | None = None,
) -> tuple[list[str], list[InternalRelocation], list[ExternalSymbol]]:
    """Apply relocations, returning (errors, internal_relocs, external_syms).

    Internal symbols are resolved. External symbols are recorded for runtime resolution.
    tls_offsets maps TLS section names to their offset within the TLS block.
    """

    errors = []
    internal_relocs = []
    external_syms_list: list[ExternalSymbol] = []
    seen_external: set[tuple[str, int]] = set()  # (name, offset) pairs we've recorded

    for reloc in relocations:
        target_sec = sections.get(reloc.section)
        if not target_sec:
            continue

        # Resolve symbol
        is_internal = False
        is_external = False
        sym_addr = 0

        if reloc.symbol in local_symbols:
            sec_name, sec_offset = local_symbols[reloc.symbol]
            if sec_name in sections:
                sym_addr = sections[sec_name].vaddr + sec_offset
                is_internal = True
            else:
                errors.append(f"Symbol {reloc.symbol} in unknown section {sec_name}")
                continue
        elif reloc.symbol.startswith("."):
            # Section reference (e.g., .rodata.str1.1)
            if reloc.symbol in sections:
                sym_addr = sections[reloc.symbol].vaddr
                is_internal = True
            else:
                errors.append(f"Unknown section symbol: {reloc.symbol}")
                continue
        elif not reloc.symbol:
            # Empty symbol name - use section base
            sym_addr = target_sec.vaddr
            is_internal = True
        elif reloc.symbol in external_symbols:
            is_external = True
            # For external symbols, we use 0 as placeholder
            # The actual address will be patched at load time
            sym_addr = 0
        else:
            errors.append(f"Unresolved symbol: {reloc.symbol}")
            continue

        # Apply relocation
        P = target_sec.vaddr + reloc.offset  # Address of the relocation
        S = sym_addr  # Symbol address (0 for external)
        A = reloc.addend

        try:
            if reloc.type == R_X86_64_64:
                # 64-bit absolute: S + A
                value = S + A
                struct.pack_into("<Q", target_sec.data, reloc.offset, value)

                if is_internal:
                    target_offset = (S + A) - base_address
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=8,
                            target_offset=target_offset,
                            reloc_type=R_X86_64_64,
                        )
                    )
                elif is_external:
                    # Record external symbol for runtime resolution
                    patch_off = target_sec.offset + reloc.offset
                    key = (reloc.symbol, patch_off)
                    if key not in seen_external:
                        seen_external.add(key)
                        # Use aliased name if available
                        resolved_name = reloc.symbol
                        if symbol_name_map and reloc.symbol in symbol_name_map:
                            resolved_name = symbol_name_map[reloc.symbol]
                        external_syms_list.append(
                            ExternalSymbol(name=resolved_name, patch_offset=patch_off)
                        )

            elif reloc.type in (R_X86_64_PC32, R_X86_64_PLT32):
                # 32-bit PC-relative: S + A - P
                if is_external:
                    errors.append(
                        f"PC32/PLT32 relocation for external symbol {reloc.symbol} not supported"
                    )
                    continue
                value = (S + A - P) & 0xFFFFFFFF
                signed = struct.unpack("<i", struct.pack("<I", value))[0]
                if signed < -(1 << 31) or signed >= (1 << 31):
                    errors.append(f"PC32 overflow for {reloc.symbol}: {signed}")
                    continue
                struct.pack_into("<I", target_sec.data, reloc.offset, value)

            elif reloc.type == R_X86_64_32:
                # 32-bit absolute (zero-extended): S + A
                value = S + A
                if value >= (1 << 32):
                    errors.append(f"32-bit overflow for {reloc.symbol}: 0x{value:x}")
                    continue
                struct.pack_into("<I", target_sec.data, reloc.offset, value)

                if is_internal:
                    target_offset = (S + A) - base_address
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=4,
                            target_offset=target_offset,
                        )
                    )

            elif reloc.type == R_X86_64_32S:
                # 32-bit absolute (sign-extended): S + A
                value = S + A
                if value >= (1 << 31) and value < (0xFFFFFFFF_00000000):
                    errors.append(f"32S overflow for {reloc.symbol}: 0x{value:x}")
                    continue
                struct.pack_into("<I", target_sec.data, reloc.offset, value & 0xFFFFFFFF)

                if is_internal:
                    target_offset = (S + A) - base_address
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=4,
                            target_offset=target_offset,
                        )
                    )

            elif reloc.type == R_X86_64_NONE:
                pass

            # ARM64 relocations
            elif reloc.type == R_AARCH64_ABS64:
                # 64-bit absolute: S + A
                value = S + A
                struct.pack_into("<Q", target_sec.data, reloc.offset, value)

                if is_internal:
                    target_offset = (S + A) - base_address
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=8,
                            target_offset=target_offset,
                            reloc_type=R_AARCH64_ABS64,
                        )
                    )
                elif is_external:
                    patch_off = target_sec.offset + reloc.offset
                    key = (reloc.symbol, patch_off)
                    if key not in seen_external:
                        seen_external.add(key)
                        # Use aliased name if available
                        resolved_name = reloc.symbol
                        if symbol_name_map and reloc.symbol in symbol_name_map:
                            resolved_name = symbol_name_map[reloc.symbol]
                        external_syms_list.append(
                            ExternalSymbol(name=resolved_name, patch_offset=patch_off)
                        )

            elif reloc.type in (R_AARCH64_CALL26, R_AARCH64_JUMP26):
                # 26-bit PC-relative call/jump
                if is_external:
                    # Use trampoline
                    if trampolines and reloc.symbol in trampolines:
                        tramp_addr = trampolines[reloc.symbol]
                        offset = tramp_addr - P
                        if -(ARM64_CALL_RANGE) <= offset < ARM64_CALL_RANGE:
                            imm26 = (offset >> 2) & 0x03FFFFFF
                            insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                            insn = (insn & 0xFC000000) | imm26
                            struct.pack_into("<I", target_sec.data, reloc.offset, insn)
                        else:
                            errors.append(f"Trampoline for {reloc.symbol} out of range")
                    else:
                        errors.append(f"No trampoline for external {reloc.symbol}")
                else:
                    # Internal call
                    offset = S + A - P
                    if -(ARM64_CALL_RANGE) <= offset < ARM64_CALL_RANGE:
                        imm26 = (offset >> 2) & 0x03FFFFFF
                        insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                        insn = (insn & 0xFC000000) | imm26
                        struct.pack_into("<I", target_sec.data, reloc.offset, insn)
                    else:
                        errors.append(
                            f"CALL26/JUMP26 out of range for {reloc.symbol}: offset={offset}"
                        )

            elif reloc.type == R_AARCH64_ADR_PREL_PG_HI21:
                # ADRP: Page(S + A) - Page(P)
                # This is PC-relative, so must be re-applied at load time
                if is_external:
                    errors.append(f"ADRP for external symbol {reloc.symbol} not supported")
                    continue
                page_s = (S + A) & ~0xFFF
                page_p = P & ~0xFFF
                offset = page_s - page_p
                imm = offset >> 12
                immlo = imm & 0x3
                immhi = (imm >> 2) & 0x7FFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0x9F00001F) | (immlo << 29) | (immhi << 5)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

                # Record for load-time patching
                target_offset = (S + A) - base_address
                internal_relocs.append(
                    InternalRelocation(
                        section_offset=target_sec.offset + reloc.offset,
                        size=4,
                        target_offset=target_offset,
                        reloc_type=R_AARCH64_ADR_PREL_PG_HI21,
                    )
                )

            elif reloc.type == R_AARCH64_ADD_ABS_LO12_NC:
                # ADD immediate: low 12 bits of S + A
                if is_external:
                    errors.append(f"ADD_ABS_LO12 for external symbol {reloc.symbol} not supported")
                    continue
                imm12 = (S + A) & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

                # Record for load-time patching
                target_offset = (S + A) - base_address
                internal_relocs.append(
                    InternalRelocation(
                        section_offset=target_sec.offset + reloc.offset,
                        size=4,
                        target_offset=target_offset,
                        reloc_type=R_AARCH64_ADD_ABS_LO12_NC,
                    )
                )

            elif reloc.type in (
                R_AARCH64_LDST128_ABS_LO12_NC,
                R_AARCH64_LDST64_ABS_LO12_NC,
                R_AARCH64_LDST32_ABS_LO12_NC,
                R_AARCH64_LDST16_ABS_LO12_NC,
                R_AARCH64_LDST8_ABS_LO12_NC,
            ):
                if is_external:
                    errors.append(f"LDST for external symbol {reloc.symbol} not supported")
                    continue
                addr = S + A
                # Extract low 12 bits, scaled by access size
                # The imm12 field encodes offset / access_size
                if reloc.type == R_AARCH64_LDST128_ABS_LO12_NC:
                    imm12 = (addr >> 4) & 0xFF  # 128-bit = 16 bytes, shift by 4
                elif reloc.type == R_AARCH64_LDST64_ABS_LO12_NC:
                    imm12 = (addr >> 3) & 0x1FF  # 64-bit = 8 bytes, shift by 3
                elif reloc.type == R_AARCH64_LDST32_ABS_LO12_NC:
                    imm12 = (addr >> 2) & 0x3FF  # 32-bit = 4 bytes, shift by 2
                elif reloc.type == R_AARCH64_LDST16_ABS_LO12_NC:
                    imm12 = (addr >> 1) & 0x7FF  # 16-bit = 2 bytes, shift by 1
                else:  # LDST8
                    imm12 = addr & 0xFFF  # 8-bit = 1 byte, no shift
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

                # Record for load-time patching
                target_offset = (S + A) - base_address
                internal_relocs.append(
                    InternalRelocation(
                        section_offset=target_sec.offset + reloc.offset,
                        size=4,
                        target_offset=target_offset,
                        reloc_type=reloc.type,
                    )
                )

            elif reloc.type == R_AARCH64_PREL32:
                # 32-bit PC-relative
                if is_external:
                    errors.append(f"PREL32 for external symbol {reloc.symbol} not supported")
                    continue
                value = (S + A - P) & 0xFFFFFFFF
                struct.pack_into("<I", target_sec.data, reloc.offset, value)

            elif reloc.type in (
                R_AARCH64_MOVW_UABS_G0_NC,
                R_AARCH64_MOVW_UABS_G1_NC,
                R_AARCH64_MOVW_UABS_G2_NC,
                R_AARCH64_MOVW_UABS_G3,
            ):
                # MOVW/MOVK with absolute address chunks (used by Rust large code model)
                # These instructions load 16-bit chunks of a 64-bit address
                if is_external:
                    errors.append(f"MOVW_UABS for external symbol {reloc.symbol} not supported")
                    continue

                addr = S + A
                # Extract the appropriate 16-bit chunk
                if reloc.type == R_AARCH64_MOVW_UABS_G0_NC:
                    imm16 = addr & 0xFFFF  # bits 0-15
                elif reloc.type == R_AARCH64_MOVW_UABS_G1_NC:
                    imm16 = (addr >> 16) & 0xFFFF  # bits 16-31
                elif reloc.type == R_AARCH64_MOVW_UABS_G2_NC:
                    imm16 = (addr >> 32) & 0xFFFF  # bits 32-47
                else:  # R_AARCH64_MOVW_UABS_G3
                    imm16 = (addr >> 48) & 0xFFFF  # bits 48-63

                # Patch the instruction: imm16 goes into bits 5-20
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFE0001F) | (imm16 << 5)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

                # Record for load-time patching
                target_offset = (S + A) - base_address
                internal_relocs.append(
                    InternalRelocation(
                        section_offset=target_sec.offset + reloc.offset,
                        size=4,
                        target_offset=target_offset,
                        reloc_type=reloc.type,
                    )
                )

            elif reloc.type == R_AARCH64_NONE:
                pass

            # TLS relocations - Local Exec model
            # These access thread-local variables via the thread pointer register
            elif reloc.type == R_X86_64_TPOFF32:
                # x86_64: 32-bit offset from thread pointer
                # The TLS variable is accessed as %fs:offset
                # Calculate TLS offset: base + section_offset + symbol_offset + addend
                tls_base_offset = 0x1000
                sym_sec_offset = 0
                if reloc.symbol in local_symbols and tls_offsets:
                    sec_name, sec_off = local_symbols[reloc.symbol]
                    if sec_name in tls_offsets:
                        sym_sec_offset = tls_offsets[sec_name] + sec_off
                tls_offset = tls_base_offset + sym_sec_offset + reloc.addend
                struct.pack_into("<i", target_sec.data, reloc.offset, tls_offset)
                # No internal reloc needed - offset is fixed at build time

            elif reloc.type == R_AARCH64_TLSLE_ADD_TPREL_HI12:
                # ARM64: High 12 bits of TP-relative offset (shifted left by 12)
                # Patches an ADD instruction: add xD, xN, #imm, lsl #12
                tls_base_offset = 0x1000
                sym_sec_offset = 0
                if reloc.symbol in local_symbols and tls_offsets:
                    sec_name, sec_off = local_symbols[reloc.symbol]
                    if sec_name in tls_offsets:
                        sym_sec_offset = tls_offsets[sec_name] + sec_off
                tls_offset = tls_base_offset + sym_sec_offset + reloc.addend
                imm = (tls_offset >> 12) & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                # ADD immediate format: imm12 is in bits 10-21
                insn = (insn & 0xFFC003FF) | (imm << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            elif reloc.type == R_AARCH64_TLSLE_ADD_TPREL_LO12_NC:
                # ARM64: Low 12 bits of TP-relative offset (no shift)
                # Patches an ADD instruction: add xD, xN, #imm
                tls_base_offset = 0x1000
                sym_sec_offset = 0
                if reloc.symbol in local_symbols and tls_offsets:
                    sec_name, sec_off = local_symbols[reloc.symbol]
                    if sec_name in tls_offsets:
                        sym_sec_offset = tls_offsets[sec_name] + sec_off
                tls_offset = tls_base_offset + sym_sec_offset + reloc.addend
                imm = tls_offset & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                # ADD immediate format: imm12 is in bits 10-21
                insn = (insn & 0xFFC003FF) | (imm << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            else:
                reloc_names = RELOC_NAMES_AARCH64 if arch == "aarch64" else RELOC_NAMES_X86_64
                errors.append(
                    f"Unsupported relocation type {reloc.type} ({reloc_names.get(reloc.type, '?')})"
                )

        except struct.error as e:
            errors.append(f"Relocation error at {reloc.offset}: {e}")

    return errors, internal_relocs, external_syms_list


def build_cosmoext(
    obj_path: Path,
    symtab_path: Path,
    load_address: int = 0x10000000,  # Default load address (256MB)
    arch: str | None = None,
    verbose: bool = False,
) -> CosmoExtBlob | None:
    """Build a CosmoExtBlob from an object file. Returns None on error."""

    # Import here to avoid circular dependency
    from symtab import SymbolTable

    print(f"Parsing object file: {obj_path}")
    sections, relocations, local_symbols, obj_arch = parse_object_file(obj_path)

    print(f"  Architecture: {obj_arch}")
    print(f"  Sections: {list(sections.keys())}")
    print(f"  Relocations: {len(relocations)}")
    print(f"  Local symbols: {len(local_symbols)}")

    # Normalize arch names (CLI uses amd64/arm64, internal uses x86_64/aarch64)
    arch_map = {"amd64": "x86_64", "arm64": "aarch64", "x86_64": "x86_64", "aarch64": "aarch64"}

    # Use object file architecture if not specified
    if arch is None:
        arch = obj_arch
    else:
        arch = arch_map.get(arch, arch)
        if arch != obj_arch:
            raise ValueError(f"Architecture mismatch: object is {obj_arch}, requested {arch}")

    # Load symbol table from target binary for validation
    symtab_arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
    symtab_arch = symtab_arch_map.get(arch, arch)
    print(f"\nLoading symbol table from: {symtab_path} (for validation)")
    st = SymbolTable.from_ape(symtab_path, arch=symtab_arch)
    print(f"  {len(st.symbols)} symbols available")

    # Symbol aliases for Cosmopolitan's mangled names
    symbol_aliases = {
        "memmove": "__memmove.default",
        "iscntrl": "__iscntrl",
        "ispunct": "__ispunct",
        "isspace": "__isspace",
        # Wide character function with .default suffix
        "wcslen": "wcslen.default",
        # C++ destructor variants (D1 = complete, D2 = base - often interchangeable)
        "_ZNSt12length_errorD1Ev": "_ZNSt12length_errorD2Ev",
        "_ZNSt12out_of_rangeD1Ev": "_ZNSt12out_of_rangeD2Ev",
        "_ZNSt13runtime_errorD1Ev": "_ZNSt13runtime_errorD2Ev",
        "_ZNSt16invalid_argumentD1Ev": "_ZNSt16invalid_argumentD2Ev",
        "_ZNSt9bad_allocD1Ev": "_ZNSt9bad_allocD2Ev",
        "_ZNSt9exceptionD2Ev": "_ZNSt9exceptionD1Ev",
        "_ZNSt20bad_array_new_lengthD1Ev": "_ZNSt20bad_array_new_lengthD2Ev",
    }

    # Identify external symbols and validate they exist
    # Also track which symbols need to be resolved using their aliased names
    external_symbols: set[str] = set()  # original symbol names
    symbol_name_map: dict[str, str] = {}  # original -> resolved name (may be aliased)
    unresolved = []
    for reloc in relocations:
        if reloc.symbol and reloc.symbol not in local_symbols and not reloc.symbol.startswith("."):
            if reloc.symbol not in external_symbols:
                # Check if symbol exists (for validation)
                addr = st.lookup(reloc.symbol)
                resolved_name = reloc.symbol
                if not addr and reloc.symbol in symbol_aliases:
                    addr = st.lookup(symbol_aliases[reloc.symbol])
                    if addr:
                        resolved_name = symbol_aliases[reloc.symbol]
                if addr:
                    external_symbols.add(reloc.symbol)  # Keep original for lookups
                    symbol_name_map[reloc.symbol] = resolved_name  # Map to resolved
                else:
                    unresolved.append(reloc.symbol)

    if unresolved:
        print("\n  ERROR: Unresolved external symbols:")
        for sym in sorted(set(unresolved)):
            print(f"    - {sym}")
        return None

    print(f"\n  External symbols (will be resolved at load time): {len(external_symbols)}")
    for name in sorted(external_symbols):
        print(f"    {name}")

    # Layout sections
    print(f"\nLaying out sections at base 0x{load_address:x}")
    total_size = layout_sections(sections, load_address)
    print(f"  Total size: {total_size} bytes")

    for sec in sections.values():
        print(f"    {sec.name}: offset={sec.offset}, vaddr=0x{sec.vaddr:x}, size={sec.size}")

    # Generate ARM64 trampolines if needed
    trampolines: dict[str, int] = {}
    trampoline_patch_offsets: dict[str, int] = {}
    trampoline_data = bytearray()
    trampoline_offset = 0

    if obj_arch == "aarch64":
        print("\nGenerating ARM64 trampolines...")
        trampoline_data, trampolines, trampoline_patch_offsets = generate_arm64_trampolines(
            relocations, sections, local_symbols, external_symbols, load_address, total_size
        )
        if trampolines:
            print(f"  Generated {len(trampolines)} trampolines ({len(trampoline_data)} bytes)")
            for sym, vaddr in sorted(trampolines.items()):
                patch_off = trampoline_patch_offsets[sym]
                print(f"    {sym}: vaddr=0x{vaddr:x}, patch_offset=0x{patch_off:x}")
            trampoline_offset = (total_size + 15) & ~15
            total_size = trampoline_offset + len(trampoline_data)

    # Calculate TLS section offsets within the TLS block
    # Order: .tbss first (uninitialized), then .tdata (initialized)
    tls_offsets: dict[str, int] = {}
    tls_offset_accum = 0
    for sec_name in [".tbss", ".tdata"]:
        if sec_name in sections and sections[sec_name].is_tls:
            tls_offsets[sec_name] = tls_offset_accum
            tls_offset_accum += sections[sec_name].size
    if tls_offsets:
        print("\n  TLS layout:")
        for sec_name, off in tls_offsets.items():
            print(f"    {sec_name}: TLS offset 0x{off:x}, size {sections[sec_name].size}")

    # Apply relocations
    print(f"\nApplying {len(relocations)} relocations...")
    errors, internal_relocs, external_syms = apply_relocations(
        sections,
        relocations,
        local_symbols,
        external_symbols,
        load_address,
        arch=obj_arch,
        trampolines=trampolines if trampolines else None,
        symbol_name_map=symbol_name_map,
        tls_offsets=tls_offsets if tls_offsets else None,
    )

    # Add trampoline patch offsets to external symbols list
    for sym, patch_off in trampoline_patch_offsets.items():
        # Use aliased name if available
        resolved_name = symbol_name_map.get(sym, sym) if symbol_name_map else sym
        external_syms.append(ExternalSymbol(name=resolved_name, patch_offset=patch_off))

    if errors:
        print("\n  Relocation errors:")
        for err in errors:
            print(f"    - {err}")
        return None

    print(f"  {len(internal_relocs)} internal relocations to apply at load time")
    print(f"  {len(external_syms)} external symbols to resolve at load time")

    # Find PyInit_* function
    init_func = None
    for name, (sec_name, offset) in local_symbols.items():
        if name.startswith("PyInit_"):
            if sec_name in sections:
                init_func = (name, sections[sec_name].vaddr + offset)
                break

    if not init_func:
        print("\nERROR: No PyInit_* function found")
        return None

    print(f"\n  Init function: {init_func[0]} at 0x{init_func[1]:x}")

    # Find _cosmoext_get_captured_def if present (for shim-based extensions)
    get_def_func = None
    for name, (sec_name, offset) in local_symbols.items():
        if name == "_cosmoext_get_captured_def":
            if sec_name in sections:
                get_def_func = (name, sections[sec_name].vaddr + offset)
                break

    # Calculate get_def_offset (offset from init to _cosmoext_get_captured_def)
    get_def_offset = 0
    if get_def_func:
        get_def_offset = get_def_func[1] - init_func[1]
        get_def_addr = get_def_func[1]
        print(
            f"  get_def function: {get_def_func[0]} at 0x{get_def_addr:x} "
            f"(offset: 0x{get_def_offset:x})"
        )

    # Add trampoline section if needed
    all_sections = list(sections.values())
    if trampoline_data:
        tramp_offset = trampoline_offset
        tramp_vaddr = load_address + tramp_offset
        tramp_section = LoadableSection(
            name=".trampolines",
            data=trampoline_data,
            offset=tramp_offset,
            vaddr=tramp_vaddr,
            flags=0x6,  # SHF_ALLOC | SHF_EXECINSTR
            align=16,
        )
        all_sections.append(tramp_section)
        print(f"  Trampolines section: offset={tramp_offset}, vaddr=0x{tramp_vaddr:x}")

    # Create blob
    blob = CosmoExtBlob(
        sections=all_sections,
        init_offset=init_func[1] - load_address,
        total_size=total_size,
        load_address=load_address,
        internal_relocs=internal_relocs,
        external_symbols=external_syms,
        get_def_offset=get_def_offset,
    )

    return blob


def build_fat_cosmoext(
    x86_64_obj: Path | None,
    aarch64_obj: Path | None,
    symtab_path: Path,
    output_path: Path,
    load_address: int = 0x10000000,
    verbose: bool = False,
) -> bool:
    """Build a fat .cosmoext with both architectures."""

    x86_64_blob = None
    aarch64_blob = None

    if x86_64_obj and x86_64_obj.exists():
        print("\n=== Building x86_64 payload ===")
        x86_64_blob = build_cosmoext(
            x86_64_obj, symtab_path, load_address=load_address, arch="x86_64", verbose=verbose
        )
        if not x86_64_blob:
            return False

    if aarch64_obj and aarch64_obj.exists():
        print("\n=== Building aarch64 payload ===")
        aarch64_blob = build_cosmoext(
            aarch64_obj, symtab_path, load_address=load_address, arch="aarch64", verbose=verbose
        )
        if not aarch64_blob:
            return False

    if not x86_64_blob and not aarch64_blob:
        print("Error: No architecture payloads built")
        return False

    # Create and write fat blob
    fat_blob = CosmoExtFatBlob(x86_64_blob=x86_64_blob, aarch64_blob=aarch64_blob)

    print(f"\nWriting {output_path} (format v7 fat)")
    with open(output_path, "wb") as f:
        fat_blob.write(f)

    print(f"  Done! Size: {output_path.stat().st_size} bytes")
    archs = []
    if x86_64_blob:
        archs.append("x86_64")
    if aarch64_blob:
        archs.append("aarch64")
    print(f"  Architectures: {', '.join(archs)}")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build fat cosmoext blob from object files")
    parser.add_argument("object_file", help="Input .o file (x86_64; aarch64 found in .aarch64/)")
    parser.add_argument("--symtab", required=True, help="Path to python.com for symbol table")
    parser.add_argument("--output", "-o", required=True, help="Output .cosmoext file")
    parser.add_argument(
        "--load-address",
        type=lambda x: int(x, 0),
        default=0x10000000,
        help="Load address (default: 0x10000000)",
    )
    parser.add_argument(
        "--arch",
        default=None,
        choices=["amd64", "arm64", "x86_64", "aarch64"],
        help="Build single arch only (for debugging); default builds both if available",
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    obj_path = Path(args.object_file)

    # If --arch specified, build single architecture
    if args.arch:
        arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(args.arch, args.arch)
        if arch == "aarch64":
            aarch64_obj = obj_path.parent / ".aarch64" / obj_path.name
            if not aarch64_obj.exists():
                aarch64_obj = obj_path  # Maybe it's already the aarch64 file
            x86_64_obj = None
        else:
            x86_64_obj = obj_path
            aarch64_obj = None
    else:
        # Build both architectures if available
        x86_64_obj = obj_path
        aarch64_obj = obj_path.parent / ".aarch64" / obj_path.name
        if not aarch64_obj.exists():
            aarch64_obj = None
            print(f"Note: No aarch64 object found at {aarch64_obj}, building x86_64 only")

    success = build_fat_cosmoext(
        x86_64_obj,
        aarch64_obj,
        Path(args.symtab),
        Path(args.output),
        load_address=args.load_address,
        verbose=args.verbose,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
