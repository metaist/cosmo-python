# Relocations Primer

This document explains relocations—a key concept for understanding how cosmoext
works and why some extensions (like PyO3/Rust) require special handling.

## What are relocations?

When a compiler generates machine code, it doesn't know where the code will be
loaded in memory. Consider this C code:

```c
extern int global_var;
extern void some_function(void);

int my_function(void) {
    some_function();
    return global_var;
}
```

The compiler needs to:
1. Generate a `call` instruction to `some_function`
2. Generate a `mov` instruction to read `global_var`

But it doesn't know the addresses yet! So it generates placeholder code:

```asm
call <TBD>           ; address of some_function unknown
mov eax, [<TBD>]     ; address of global_var unknown
```

**Relocations** are metadata entries that say: "at offset X in this code,
fill in the address of symbol Y."

```
Relocation entry:
  Offset: 0x05        ; where the placeholder is
  Symbol: some_function
  Type:   R_X86_64_PLT32   ; how to compute the address
```

The linker (at build time) or loader (at runtime) processes these relocations
to fill in the actual addresses.

## x86_64 relocation types

Different relocation types encode addresses differently:

### Absolute relocations

| Type | Size | Range | Description |
|------|------|-------|-------------|
| `R_X86_64_64` | 64-bit | Full 64-bit address space | Store complete address |
| `R_X86_64_32` | 32-bit | 0 to 4GB | Store low 32 bits (assumes high bits are 0) |
| `R_X86_64_32S` | 32-bit | ±2GB around 0 | Sign-extended 32-bit |

**Example: `R_X86_64_64`**
```asm
; Large code model - works everywhere
movabs rax, 0x7f0012345678  ; full 64-bit immediate
```

**Example: `R_X86_64_32`**
```asm
; Small code model - only works in low 4GB
mov eax, 0x00401234         ; 32-bit immediate, zero-extended
```

### PC-relative relocations

These encode the *distance* from the current instruction to the target:

| Type | Size | Range | Description |
|------|------|-------|-------------|
| `R_X86_64_PC32` | 32-bit signed | ±2GB from PC | Relative offset |
| `R_X86_64_PLT32` | 32-bit signed | ±2GB from PC | Call via PLT |
| `R_X86_64_GOTPCREL` | 32-bit signed | ±2GB from PC | Load via GOT |

**Example: `R_X86_64_PLT32`**
```asm
; Current instruction at 0x7f0000001000
; Target function at    0x7f0000002000
call +0x1000            ; encoded as 32-bit offset
```

The advantage: position-independent code. The disadvantage: limited range.

## Code models

The **code model** tells the compiler what assumptions it can make about addresses:

### Small model (`-mcmodel=small`, default)

Assumes:
- All code and data fit in the low 2GB of address space
- Everything is within ±2GB of everything else

Generates:
- `R_X86_64_32` for global data
- `R_X86_64_PC32` / `R_X86_64_PLT32` for function calls

**Pros:** Smaller, faster code (32-bit operations are more compact)
**Cons:** Only works if code is loaded in low memory

### Large model (`-mcmodel=large`)

Assumes:
- Code and data can be anywhere in 64-bit address space
- Nothing about relative positions

Generates:
- `R_X86_64_64` for everything

**Pros:** Works regardless of where code is loaded
**Cons:** Larger code (64-bit immediates take more bytes)

```c
// Same C code, different code models:

// Small model:
call printf          ; 5 bytes: E8 xx xx xx xx (PC-relative)

// Large model:
movabs rax, printf   ; 10 bytes: 48 B8 xx xx xx xx xx xx xx xx
call rax             ; 2 bytes: FF D0
```

## Why cosmoext needs large model

cosmoext loads extensions at runtime using `mmap()`. The OS places them at
high addresses:

```
Memory layout:

0x00000000_00400000  ┌─────────────────────┐
                     │ python.com          │
                     │ (Python interpreter │
                     │  and C library)     │
0x00000000_01000000  └─────────────────────┘
                     │                     │
                     │  ~127 TB gap        │
                     │                     │
0x00007f00_00000000  ┌─────────────────────┐
                     │ mmap region         │
                     │ (where .cosmoext    │
                     │  files are loaded)  │
0x00007fff_ffffffff  └─────────────────────┘
```

If an extension uses `R_X86_64_PLT32` to call `PyLong_FromLong`:

```
Extension at:     0x7f0000001000
PyLong_FromLong:  0x0000004a2000
Distance:         0x7efffffef000 (~127 TB)
Max PC32 range:   0x000080000000 (±2 GB)

Result: OVERFLOW - the call instruction cannot encode this distance!
```

With `R_X86_64_64`:

```asm
movabs rax, 0x4a2000    ; load full 64-bit address
call rax                ; works from anywhere
```

## ARM64 relocations

ARM64 has similar constraints but different instruction encoding:

| Type | Range | Description |
|------|-------|-------------|
| `R_AARCH64_ADR_PREL_PG_HI21` | ±4GB | Page-relative (ADRP instruction) |
| `R_AARCH64_ADD_ABS_LO12_NC` | 12-bit | Low 12 bits of address |
| `R_AARCH64_CALL26` | ±128MB | Branch instruction |
| `R_AARCH64_ABS64` | Full 64-bit | Absolute address |

The ±128MB limit on `R_AARCH64_CALL26` is why cosmoext uses **trampolines**
on ARM64—small stubs that perform indirect jumps:

```asm
; Trampoline for far call:
trampoline_PyLong_FromLong:
    ldr x16, [pc, #8]           ; load address from nearby memory
    br x16                      ; indirect branch (unlimited range)
    .quad PyLong_FromLong       ; 64-bit address stored here
```

## Practical implications

### C extensions (work)

We compile with `cosmocc -mcmodel=large`:
```bash
cosmocc -mcmodel=large -c extension.c -o extension.o
```

All relocations are `R_X86_64_64` → works when loaded anywhere.

### Rust extensions (problematic)

Rust uses `-mcmodel=small` by default. The compiled code contains:
- `R_X86_64_32` (30,000+ occurrences in typical PyO3 extension)
- `R_X86_64_PC32` (4,000+)
- `R_X86_64_PLT32` (1,800+)

These **cannot be fixed at load time**—the instructions themselves are wrong.
The only solution is recompiling Rust with a custom target that uses
`-mcmodel=large`.

### Diagnosing relocation issues

Use `readelf` to inspect relocations:

```bash
# List all relocations in an object file
readelf -r extension.o

# Count by type
readelf -r extension.o | grep -oE 'R_X86_64_[A-Z0-9_]+' | sort | uniq -c

# For cosmoext compatibility, you want mostly R_X86_64_64
```

## Further reading

- [System V AMD64 ABI](https://refspecs.linuxbase.org/elf/x86_64-abi-0.99.pdf) - Official x86_64 relocation definitions
- [ARM64 ELF ABI](https://github.com/ARM-software/abi-aa/blob/main/aaelf64/aaelf64.rst) - ARM64 relocation definitions
- [Code Models in GCC](https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html) - `-mcmodel` documentation
