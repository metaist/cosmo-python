#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyelftools>=0.31"]
# ///
"""Parse ELF relocations and apply them to create a loadable blob.

This is the core of the cosmoext build process:
1. Parse the object file's sections and relocations
2. Resolve external symbols against the target binary's symbol table
3. Apply relocations to produce position-dependent code
4. Output a blob that can be loaded at a known address

Usage:
    ./relocate.py testmod.o --symtab python.com --output testmod.cosmoext
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
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
class CosmoExtBlob:
    """The output blob ready for loading."""

    sections: list[LoadableSection]
    init_offset: int  # Offset of PyInit_* function
    total_size: int
    load_address: int  # Address where this was designed to load
    internal_relocs: list[InternalRelocation]  # Relocations to apply at load time

    def write(self, f: BinaryIO) -> None:
        """Write the blob to a file."""
        # Format version 3:
        # - 4 bytes: magic "CEXT"
        # - 4 bytes: version (3)
        # - 8 bytes: load_address (designed)
        # - 8 bytes: total_size
        # - 8 bytes: init_offset
        # - 8 bytes: header_size (where blob data starts)
        # - 8 bytes: num_sections
        # - 8 bytes: num_internal_relocs
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
        # - Padding to page boundary
        # - Raw section data concatenated

        # First calculate header size to include in header
        base_header_size = 56  # 4+4+8+8+8+8+8+8
        section_headers_size = len(self.sections) * 24
        reloc_data_size = len(self.internal_relocs) * 24
        header_total = base_header_size + section_headers_size + reloc_data_size
        # Round up to nearest 4096
        header_size = ((header_total + 4095) // 4096) * 4096

        header = struct.pack(
            "<4sIQQQQQQ",
            b"CEXT",
            3,  # version
            self.load_address,
            self.total_size,
            self.init_offset,
            header_size,
            len(self.sections),
            len(self.internal_relocs),
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

        # Pad to header_size
        actual_header = len(header) + len(section_headers) + len(reloc_data)
        padding = header_size - actual_header

        f.write(header)
        f.write(section_headers)
        f.write(reloc_data)
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
    external_symbols: dict[str, int],
    base_address: int,
    total_size: int,
) -> tuple[bytearray, dict[str, int]]:
    """Generate ARM64 trampolines for external function calls.

    Returns: (trampoline_data, symbol_to_trampoline_addr)
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

        # Check if target is within range
        target_sec = sections.get(reloc.section)
        if not target_sec:
            continue

        P = target_sec.vaddr + reloc.offset
        S = external_symbols.get(reloc.symbol, 0)
        if not S:
            continue

        offset = S + reloc.addend - P
        if not (-(ARM64_CALL_RANGE) <= offset < ARM64_CALL_RANGE):
            needs_trampoline.add(reloc.symbol)

    if not needs_trampoline:
        return bytearray(), {}

    # Generate trampolines
    # Place them right after the existing sections
    tramp_base = base_address + total_size
    # Align to 16 bytes
    tramp_base = (tramp_base + 15) & ~15

    tramp_data = bytearray()
    tramp_addrs: dict[str, int] = {}

    for sym in sorted(needs_trampoline):
        addr = external_symbols[sym]
        tramp_addr = tramp_base + len(tramp_data)
        tramp_addrs[sym] = tramp_addr

        # Build trampoline: ldr x16, #8; br x16; .quad addr
        tramp = bytearray(ARM64_TRAMPOLINE)
        struct.pack_into("<Q", tramp, ARM64_TRAMPOLINE_ADDR_OFFSET, addr)
        tramp_data.extend(tramp)

    return tramp_data, tramp_addrs


def apply_relocations(
    sections: dict[str, LoadableSection],
    relocations: list[Relocation],
    local_symbols: dict[str, tuple[str, int]],
    external_symbols: dict[str, int],
    base_address: int,
    arch: str = "x86_64",
    trampolines: dict[str, int] | None = None,
) -> tuple[list[str], list[InternalRelocation]]:
    """Apply relocations, returning (errors, internal_relocs).

    External symbols are resolved to absolute addresses.
    Internal symbols are resolved, but we also return a list of internal
    relocations that need to be re-applied at load time if the actual
    load address differs from base_address.
    """

    errors = []
    internal_relocs = []

    for reloc in relocations:
        target_sec = sections.get(reloc.section)
        if not target_sec:
            continue

        # Resolve symbol
        is_internal = False
        if reloc.symbol in external_symbols:
            sym_addr = external_symbols[reloc.symbol]
        elif reloc.symbol in local_symbols:
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
        else:
            errors.append(f"Unresolved symbol: {reloc.symbol}")
            continue

        # Apply relocation
        P = target_sec.vaddr + reloc.offset  # Address of the relocation
        S = sym_addr  # Symbol address
        A = reloc.addend

        try:
            if reloc.type == R_X86_64_64:
                # 64-bit absolute: S + A
                value = S + A
                struct.pack_into("<Q", target_sec.data, reloc.offset, value)

                # Track internal relocations for load-time fixup
                if is_internal:
                    # Calculate target offset in blob
                    target_offset = (S + A) - base_address
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=8,
                            target_offset=target_offset,
                        )
                    )

            elif reloc.type in (R_X86_64_PC32, R_X86_64_PLT32):
                # 32-bit PC-relative: S + A - P
                # These are position-independent (relative), no fixup needed
                value = (S + A - P) & 0xFFFFFFFF
                # Check for overflow
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
                pass  # No action needed

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

            elif reloc.type in (R_AARCH64_CALL26, R_AARCH64_JUMP26):
                # 26-bit PC-relative call/jump
                # Range: ±128MB
                offset = S + A - P
                if -(ARM64_CALL_RANGE) <= offset < ARM64_CALL_RANGE:
                    # Within range - patch directly
                    # The offset is in bytes, instruction encodes offset/4
                    imm26 = (offset >> 2) & 0x03FFFFFF
                    # Read existing instruction and patch
                    insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                    insn = (insn & 0xFC000000) | imm26
                    struct.pack_into("<I", target_sec.data, reloc.offset, insn)
                elif trampolines and reloc.symbol in trampolines:
                    # Use trampoline
                    tramp_addr = trampolines[reloc.symbol]
                    offset = tramp_addr - P
                    if -(ARM64_CALL_RANGE) <= offset < ARM64_CALL_RANGE:
                        imm26 = (offset >> 2) & 0x03FFFFFF
                        insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                        insn = (insn & 0xFC000000) | imm26
                        struct.pack_into("<I", target_sec.data, reloc.offset, insn)
                    else:
                        errors.append(f"Trampoline for {reloc.symbol} still out of range")
                else:
                    errors.append(
                        f"CALL26/JUMP26 out of range for {reloc.symbol}: "
                        f"offset={offset}, range=±{ARM64_CALL_RANGE}"
                    )

            elif reloc.type == R_AARCH64_ADR_PREL_PG_HI21:
                # ADRP: Page(S + A) - Page(P)
                page_s = (S + A) & ~0xFFF
                page_p = P & ~0xFFF
                offset = page_s - page_p
                # Encode into ADRP instruction (immhi:immlo)
                imm = offset >> 12
                immlo = imm & 0x3
                immhi = (imm >> 2) & 0x7FFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0x9F00001F) | (immlo << 29) | (immhi << 5)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

                if is_internal:
                    # ADRP needs page-level fixup
                    internal_relocs.append(
                        InternalRelocation(
                            section_offset=target_sec.offset + reloc.offset,
                            size=4,  # instruction size
                            target_offset=(S + A) - base_address,
                        )
                    )

            elif reloc.type == R_AARCH64_ADD_ABS_LO12_NC:
                # ADD/SUB immediate: low 12 bits of S + A
                imm12 = (S + A) & 0xFFF
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            elif reloc.type in (
                R_AARCH64_LDST64_ABS_LO12_NC,
                R_AARCH64_LDST32_ABS_LO12_NC,
                R_AARCH64_LDST8_ABS_LO12_NC,
            ):
                # LDR/STR offset: low 12 bits, scaled by access size
                addr = S + A
                if reloc.type == R_AARCH64_LDST64_ABS_LO12_NC:
                    imm12 = (addr >> 3) & 0x1FF  # 64-bit scaled
                elif reloc.type == R_AARCH64_LDST32_ABS_LO12_NC:
                    imm12 = (addr >> 2) & 0x3FF  # 32-bit scaled
                else:
                    imm12 = addr & 0xFFF  # 8-bit, no scaling
                insn = struct.unpack_from("<I", target_sec.data, reloc.offset)[0]
                insn = (insn & 0xFFC003FF) | (imm12 << 10)
                struct.pack_into("<I", target_sec.data, reloc.offset, insn)

            elif reloc.type == R_AARCH64_PREL32:
                # 32-bit PC-relative
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

    return errors, internal_relocs


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

    # Load symbol table from target binary
    # Note: symtab uses amd64/arm64 naming, we use x86_64/aarch64 internally
    symtab_arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
    symtab_arch = symtab_arch_map.get(arch, arch)
    print(f"\nLoading symbol table from: {symtab_path}")
    st = SymbolTable.from_ape(symtab_path, arch=symtab_arch)
    print(f"  {len(st.symbols)} symbols available")

    # Symbol aliases for Cosmopolitan's mangled names
    symbol_aliases = {
        "memmove": "__memmove.default",
        "iscntrl": "__iscntrl",
        "ispunct": "__ispunct",
        "isspace": "__isspace",
    }

    # Build external symbol map
    external_symbols = {}
    unresolved = []
    for reloc in relocations:
        if reloc.symbol and reloc.symbol not in local_symbols and not reloc.symbol.startswith("."):
            if reloc.symbol not in external_symbols:
                addr = st.lookup(reloc.symbol)
                if not addr and reloc.symbol in symbol_aliases:
                    addr = st.lookup(symbol_aliases[reloc.symbol])
                if addr:
                    external_symbols[reloc.symbol] = addr
                else:
                    unresolved.append(reloc.symbol)

    if unresolved:
        print("\n  WARNING: Unresolved external symbols:")
        for sym in sorted(set(unresolved)):
            print(f"    - {sym}")

    print("\n  Resolved external symbols:")
    for name, addr in sorted(external_symbols.items()):
        print(f"    {name}: 0x{addr:x}")

    # Layout sections
    print(f"\nLaying out sections at base 0x{load_address:x}")
    total_size = layout_sections(sections, load_address)
    print(f"  Total size: {total_size} bytes")

    for sec in sections.values():
        print(f"    {sec.name}: offset={sec.offset}, vaddr=0x{sec.vaddr:x}, size={sec.size}")

    # Generate ARM64 trampolines if needed
    trampolines: dict[str, int] = {}
    trampoline_data = bytearray()
    trampoline_offset = 0
    if obj_arch == "aarch64":
        print("\nGenerating ARM64 trampolines...")
        trampoline_data, trampolines = generate_arm64_trampolines(
            relocations, sections, local_symbols, external_symbols, load_address, total_size
        )
        if trampolines:
            print(f"  Generated {len(trampolines)} trampolines ({len(trampoline_data)} bytes)")
            for sym, addr in sorted(trampolines.items()):
                print(f"    {sym}: 0x{addr:x}")
            # Calculate trampoline section offset (must match what generate_arm64_trampolines used)
            trampoline_offset = (total_size + 15) & ~15
            # Update total size to include trampolines
            total_size = trampoline_offset + len(trampoline_data)

    # Apply relocations
    print(f"\nApplying {len(relocations)} relocations...")
    errors, internal_relocs = apply_relocations(
        sections,
        relocations,
        local_symbols,
        external_symbols,
        load_address,
        arch=obj_arch,
        trampolines=trampolines if trampolines else None,
    )

    if errors:
        print("\n  Relocation errors:")
        for err in errors:
            print(f"    - {err}")
        return False

    print(f"  {len(internal_relocs)} internal relocations to apply at load time")

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
        # Use the offset calculated during trampoline generation
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
    )

    print(f"\nWriting {output_path}")
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
