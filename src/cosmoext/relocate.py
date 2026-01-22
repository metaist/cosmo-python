#!/usr/bin/env python3
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

from elftools.elf.elffile import ELFFile  # type: ignore[import-untyped]
from elftools.elf.relocation import RelocationSection  # type: ignore[import-untyped]
from elftools.elf.sections import SymbolTableSection  # type: ignore[import-untyped]

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
R_AARCH64_LDST64_ABS_LO12_NC = 286  # S + A (low 12 bits for 64-bit load/store)
R_AARCH64_LDST32_ABS_LO12_NC = 285  # S + A (low 12 bits for 32-bit load/store)
R_AARCH64_LDST8_ABS_LO12_NC = 278  # S + A (low 12 bits for 8-bit load/store)
R_AARCH64_ADR_GOT_PAGE = 311  # Page(G(S)) - Page(P) (GOT page)
R_AARCH64_LD64_GOT_LO12_NC = 312  # G(S) (low 12 bits of GOT entry)
R_AARCH64_PREL32 = 261  # S + A - P (32-bit PC-relative)

RELOC_NAMES_X86_64 = {
    R_X86_64_NONE: "R_X86_64_NONE",
    R_X86_64_64: "R_X86_64_64",
    R_X86_64_PC32: "R_X86_64_PC32",
    R_X86_64_PLT32: "R_X86_64_PLT32",
    R_X86_64_32: "R_X86_64_32",
    R_X86_64_32S: "R_X86_64_32S",
}

RELOC_NAMES_AARCH64 = {
    R_AARCH64_NONE: "R_AARCH64_NONE",
    R_AARCH64_ABS64: "R_AARCH64_ABS64",
    R_AARCH64_CALL26: "R_AARCH64_CALL26",
    R_AARCH64_JUMP26: "R_AARCH64_JUMP26",
    R_AARCH64_ADR_PREL_PG_HI21: "R_AARCH64_ADR_PREL_PG_HI21",
    R_AARCH64_ADD_ABS_LO12_NC: "R_AARCH64_ADD_ABS_LO12_NC",
    R_AARCH64_LDST64_ABS_LO12_NC: "R_AARCH64_LDST64_ABS_LO12_NC",
    R_AARCH64_LDST32_ABS_LO12_NC: "R_AARCH64_LDST32_ABS_LO12_NC",
    R_AARCH64_LDST8_ABS_LO12_NC: "R_AARCH64_LDST8_ABS_LO12_NC",
    R_AARCH64_PREL32: "R_AARCH64_PREL32",
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
    """A relocation that must be applied at load time."""

    section_offset: int  # Offset in the blob
    size: int  # 4 or 8 bytes
    target_offset: int  # Offset in the blob that this points to


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

    def write(self, f: BinaryIO) -> None:
        """Write the blob to a file in format version 4."""
        # Format version 4:
        # - 4 bytes: magic "CEXT"
        # - 4 bytes: version (4)
        # - 8 bytes: load_address (designed)
        # - 8 bytes: total_size
        # - 8 bytes: init_offset
        # - 8 bytes: header_size (where blob data starts)
        # - 8 bytes: num_sections
        # - 8 bytes: num_internal_relocs
        # - 8 bytes: num_external_symbols
        # - 8 bytes: string_table_size
        # - For each section:
        #   - 8 bytes: offset
        #   - 8 bytes: size
        #   - 4 bytes: flags (1=exec, 2=write)
        #   - 4 bytes: padding
        # - For each internal reloc:
        #   - 8 bytes: section_offset
        #   - 4 bytes: size (4 or 8)
        #   - 4 bytes: padding
        #   - 8 bytes: target_offset
        # - For each external symbol:
        #   - 8 bytes: patch_offset (where to write address in blob)
        #   - 4 bytes: name_offset (offset into string table)
        #   - 4 bytes: padding
        # - String table (null-terminated symbol names)
        # - Padding to page boundary
        # - Raw section data concatenated

        # Build string table
        string_table = bytearray()
        name_offsets: dict[str, int] = {}
        for ext_sym in self.external_symbols:
            if ext_sym.name not in name_offsets:
                name_offsets[ext_sym.name] = len(string_table)
                string_table.extend(ext_sym.name.encode("utf-8"))
                string_table.append(0)  # null terminator

        # Calculate header size
        base_header_size = 72  # 4+4+8*8 = 72 bytes
        section_headers_size = len(self.sections) * 24
        reloc_data_size = len(self.internal_relocs) * 24
        external_sym_size = len(self.external_symbols) * 16
        header_total = (
            base_header_size
            + section_headers_size
            + reloc_data_size
            + external_sym_size
            + len(string_table)
        )
        # Round up to nearest 4096
        header_size = ((header_total + 4095) // 4096) * 4096

        header = struct.pack(
            "<4sIQQQQQQQQ",
            b"CEXT",
            4,  # version
            self.load_address,
            self.total_size,
            self.init_offset,
            header_size,
            len(self.sections),
            len(self.internal_relocs),
            len(self.external_symbols),
            len(string_table),
        )

        section_headers = b""
        for sec in self.sections:
            flags = 0
            if sec.is_executable:
                flags |= 1
            if sec.is_writable:
                flags |= 2
            # C struct has 4 bytes padding after flags due to alignment
            section_headers += struct.pack("<QQIxxxx", sec.offset, sec.size, flags)

        reloc_data = b""
        for reloc in self.internal_relocs:
            # C struct has 4 bytes padding after size due to uint64_t alignment
            reloc_data += struct.pack(
                "<QIxxxxQ", reloc.section_offset, reloc.size, reloc.target_offset
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
) -> tuple[list[str], list[InternalRelocation], list[ExternalSymbol]]:
    """Apply relocations, returning (errors, internal_relocs, external_syms).

    Internal symbols are resolved. External symbols are recorded for runtime resolution.
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
                        )
                    )
                elif is_external:
                    # Record external symbol for runtime resolution
                    patch_off = target_sec.offset + reloc.offset
                    key = (reloc.symbol, patch_off)
                    if key not in seen_external:
                        seen_external.add(key)
                        external_syms_list.append(
                            ExternalSymbol(name=reloc.symbol, patch_offset=patch_off)
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
                        )
                    )
                elif is_external:
                    patch_off = target_sec.offset + reloc.offset
                    key = (reloc.symbol, patch_off)
                    if key not in seen_external:
                        seen_external.add(key)
                        external_syms_list.append(
                            ExternalSymbol(name=reloc.symbol, patch_offset=patch_off)
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

            elif reloc.type == R_AARCH64_ADD_ABS_LO12_NC:
                # ADD immediate: low 12 bits of S + A
                if is_external:
                    errors.append(f"ADD_ABS_LO12 for external symbol {reloc.symbol} not supported")
                    continue
                imm12 = (S + A) & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            elif reloc.type in (
                R_AARCH64_LDST64_ABS_LO12_NC,
                R_AARCH64_LDST32_ABS_LO12_NC,
                R_AARCH64_LDST8_ABS_LO12_NC,
            ):
                if is_external:
                    errors.append(f"LDST for external symbol {reloc.symbol} not supported")
                    continue
                addr = S + A
                if reloc.type == R_AARCH64_LDST64_ABS_LO12_NC:
                    imm12 = (addr >> 3) & 0x1FF
                elif reloc.type == R_AARCH64_LDST32_ABS_LO12_NC:
                    imm12 = (addr >> 2) & 0x3FF
                else:
                    imm12 = addr & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            elif reloc.type == R_AARCH64_PREL32:
                # 32-bit PC-relative
                if is_external:
                    errors.append(f"PREL32 for external symbol {reloc.symbol} not supported")
                    continue
                value = (S + A - P) & 0xFFFFFFFF
                struct.pack_into("<I", target_sec.data, reloc.offset, value)

            elif reloc.type == R_AARCH64_NONE:
                pass

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
    output_path: Path,
    load_address: int = 0x10000000,  # Default load address (256MB)
    arch: str | None = None,
    verbose: bool = False,
) -> bool:
    """Build a .cosmoext blob from an object file."""

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
    }

    # Identify external symbols and validate they exist
    external_symbols: set[str] = set()
    unresolved = []
    for reloc in relocations:
        if reloc.symbol and reloc.symbol not in local_symbols and not reloc.symbol.startswith("."):
            if reloc.symbol not in external_symbols:
                # Check if symbol exists (for validation)
                addr = st.lookup(reloc.symbol)
                if not addr and reloc.symbol in symbol_aliases:
                    addr = st.lookup(symbol_aliases[reloc.symbol])
                if addr:
                    external_symbols.add(reloc.symbol)
                else:
                    unresolved.append(reloc.symbol)

    if unresolved:
        print("\n  ERROR: Unresolved external symbols:")
        for sym in sorted(set(unresolved)):
            print(f"    - {sym}")
        return False

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
    )

    # Add trampoline patch offsets to external symbols list
    for sym, patch_off in trampoline_patch_offsets.items():
        external_syms.append(ExternalSymbol(name=sym, patch_offset=patch_off))

    if errors:
        print("\n  Relocation errors:")
        for err in errors:
            print(f"    - {err}")
        return False

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
        return False

    print(f"\n  Init function: {init_func[0]} at 0x{init_func[1]:x}")

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
    )

    print(f"\nWriting {output_path} (format v4)")
    with open(output_path, "wb") as f:
        blob.write(f)

    print(f"  Done! Size: {output_path.stat().st_size} bytes")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build cosmoext blob from object file")
    parser.add_argument("object_file", help="Input .o file")
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
        help="Target architecture (auto-detected from object file if not specified)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    success = build_cosmoext(
        Path(args.object_file),
        Path(args.symtab),
        Path(args.output),
        load_address=args.load_address,
        arch=args.arch,
        verbose=args.verbose,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
