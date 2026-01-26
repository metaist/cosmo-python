#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/mman.h>

/* Declare internal function for package context (defined in Python/import.c)
 * Only available in Python 3.12+ */
#if PY_VERSION_HEX >= 0x030C0000
extern const char *_PyImport_SwapPackageContext(const char *newcontext);
#endif
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include "third_party/zlib/zlib.h"

/* OS and architecture detection at runtime for Cosmopolitan */
#ifdef __COSMOPOLITAN__
#define _COSMO_SOURCE 1
#include "libc/dce.h"                      /* For IsXnu(), IsAarch64() runtime detection */
#include "libc/runtime/syslib.internal.h"  /* For __syslib JIT functions */
#include "libc/runtime/symbols.internal.h" /* For GetSymbolTable() */
#else
#define IsXnu()     0
#define IsAarch64() 0
#endif

#define COSMOEXT_MAGIC   0x54584543
#define COSMOEXT_VERSION 7 /* Fat format (x86_64 + aarch64) */

/* Fat format flags */
#define COSMOEXT_HAS_X86_64  0x1
#define COSMOEXT_HAS_AARCH64 0x2

/* Section flags in cosmoext format */
#define COSMOEXT_SECTION_EXEC  0x1
#define COSMOEXT_SECTION_WRITE 0x2
#define COSMOEXT_SECTION_TLS   0x4

/* TLS base offset for extension TLS variables */
#define COSMOEXT_TLS_BASE_OFFSET 0x1000

/* ARM64 relocation types */
#define R_AARCH64_ABS64               257
#define R_AARCH64_ADR_PREL_PG_HI21    275
#define R_AARCH64_ADD_ABS_LO12_NC     277
#define R_AARCH64_LDST8_ABS_LO12_NC   278
#define R_AARCH64_LDST16_ABS_LO12_NC  284
#define R_AARCH64_LDST32_ABS_LO12_NC  285
#define R_AARCH64_LDST64_ABS_LO12_NC  286
#define R_AARCH64_LDST128_ABS_LO12_NC 299
#define R_AARCH64_MOVW_UABS_G0_NC     264
#define R_AARCH64_MOVW_UABS_G1_NC     266
#define R_AARCH64_MOVW_UABS_G2_NC     268
#define R_AARCH64_MOVW_UABS_G3        269

/* x86_64 relocation types */
#define R_X86_64_64 1

/*
 * Format v7: Fat cosmoext with both architectures
 *
 * File layout:
 *   [FatHeader: 48 bytes]
 *   [x86_64 ArchPayload] (if present)
 *   [aarch64 ArchPayload] (if present)
 *
 * Each ArchPayload contains:
 *   [ArchHeader: 72 bytes]
 *   [Section descriptors]
 *   [Relocation table]
 *   [External symbol table]
 *   [String table]
 *   [Section data (code + data)]
 */

/* v7 fat header - selects architecture at runtime */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t flags;    /* COSMOEXT_HAS_X86_64 | COSMOEXT_HAS_AARCH64 */
    uint32_t reserved; /* Must be 0 */
    uint64_t x86_64_offset;
    uint64_t x86_64_size;
    uint64_t aarch64_offset;
    uint64_t aarch64_size;
} CosmoExtFatHeader;

/* Architecture-specific payload header (embedded in fat file) */
typedef struct {
    uint64_t load_address;
    uint64_t total_size;
    uint64_t init_offset;
    uint64_t header_size;
    uint64_t num_sections;
    uint64_t num_relocs;
    uint64_t num_external_symbols;
    uint64_t string_table_size;
    uint64_t get_def_offset;
} CosmoExtArchHeader;

typedef struct {
    uint64_t offset;
    uint64_t size;
    uint32_t flags;
    /* 4 bytes padding */
} CosmoExtSection;

/* Reloc format - includes relocation type for proper ARM64 support */
typedef struct {
    uint64_t blob_offset;
    uint32_t reloc_type; /* R_X86_64_*, R_AARCH64_* */
    uint32_t size;       /* 4 or 8 bytes */
    uint64_t target_offset;
} CosmoExtReloc;

typedef struct {
    uint64_t patch_offset;
    uint32_t name_offset;
    /* 4 bytes padding */
} CosmoExtExternalSym;

typedef void *(*CosmoExtInitFunc)(void);
typedef PyModuleDef *(*GetCapturedDefFunc)(void);

/* Symbol aliases for Cosmopolitan's mangled names */
static const char *get_symbol_alias(const char *name)
{
    if (strcmp(name, "memmove") == 0)
        return "__memmove.default";
    if (strcmp(name, "iscntrl") == 0)
        return "__iscntrl";
    if (strcmp(name, "ispunct") == 0)
        return "__ispunct";
    if (strcmp(name, "isspace") == 0)
        return "__isspace";
    return NULL;
}

/*
 * Simple symbol table extracted from APE ZIP.
 * Format matches Cosmopolitan's SymbolTable but we manage memory ourselves.
 */
typedef struct {
    uint64_t count;
    int64_t addr_base;
    uint32_t *names;     /* Array of offsets into name_base */
    char *name_base;     /* Concatenated null-terminated names */
    uint32_t *sym_addrs; /* Array of symbol start addresses (relative to addr_base) */
} SimpleSymbolTable;

static void free_simple_symtab(SimpleSymbolTable *st)
{
    if (st) {
        if (st->names)
            free(st->names);
        if (st->name_base)
            free(st->name_base);
        if (st->sym_addrs)
            free(st->sym_addrs);
        free(st);
    }
}

/* Decompress raw deflate data using zlib */
static unsigned char *inflate_data(const unsigned char *comp_data, size_t comp_size,
                                   size_t uncomp_size)
{
    unsigned char *output = malloc(uncomp_size);
    if (!output)
        return NULL;

    z_stream strm;
    memset(&strm, 0, sizeof(strm));
    strm.next_in = (Bytef *)comp_data;
    strm.avail_in = comp_size;
    strm.next_out = output;
    strm.avail_out = uncomp_size;

    /* -15 = raw deflate (no zlib header) */
    int ret = inflateInit2(&strm, -15);
    if (ret != Z_OK) {
        free(output);
        return NULL;
    }

    ret = inflate(&strm, Z_FINISH);
    inflateEnd(&strm);

    if (ret != Z_STREAM_END) {
        free(output);
        return NULL;
    }

    return output;
}

/* Load symbol table from APE ZIP embedded .symtab.{arch} */
static SimpleSymbolTable *load_symtab_from_ape(const char *exe_path, int verbose)
{
    FILE *f = NULL;
    unsigned char *file_data = NULL;
    unsigned char *symtab_raw = NULL;
    SimpleSymbolTable *st = NULL;

    const char *arch_suffix;
#ifdef __COSMOPOLITAN__
    arch_suffix = IsAarch64() ? "arm64" : "amd64";
#else
    arch_suffix = "amd64";
#endif

    char target_name[32];
    snprintf(target_name, sizeof(target_name), ".symtab.%s", arch_suffix);
    size_t target_len = strlen(target_name);

    if (verbose) {
        fprintf(stderr, "[cosmoext] Looking for %s in %s\n", target_name, exe_path);
    }

    f = fopen(exe_path, "rb");
    if (!f)
        goto cleanup;

    /* Get file size */
    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);

    /* Read entire file (APE binaries are typically <100MB) */
    file_data = malloc(file_size);
    if (!file_data)
        goto cleanup;
    if (fread(file_data, 1, file_size, f) != (size_t)file_size)
        goto cleanup;
    fclose(f);
    f = NULL;

    /* Search for ZIP local file header with our target filename */
    const unsigned char pk_sig[4] = {0x50, 0x4B, 0x03, 0x04};
    size_t offset = 0;

    while (offset + 30 + target_len < (size_t)file_size) {
        /* Find next PK signature */
        unsigned char *pos = memmem(file_data + offset, file_size - offset, pk_sig, 4);
        if (!pos)
            break;

        size_t header_pos = pos - file_data;

        /* Parse ZIP local file header */
        if (header_pos + 30 > (size_t)file_size)
            break;

        uint16_t compression = *(uint16_t *)(pos + 8);
        uint32_t comp_size = *(uint32_t *)(pos + 18);
        uint32_t uncomp_size = *(uint32_t *)(pos + 22);
        uint16_t name_len = *(uint16_t *)(pos + 26);
        uint16_t extra_len = *(uint16_t *)(pos + 28);

        /* Check filename */
        if (name_len == target_len && header_pos + 30 + name_len <= (size_t)file_size &&
            memcmp(pos + 30, target_name, target_len) == 0) {
            size_t data_start = header_pos + 30 + name_len + extra_len;
            if (data_start + comp_size > (size_t)file_size)
                break;

            if (verbose) {
                fprintf(stderr, "[cosmoext] Found %s at offset 0x%zx, size=%u->%u\n", target_name,
                        header_pos, comp_size, uncomp_size);
            }

            /* Decompress */
            if (compression == 0) {
                /* Stored */
                symtab_raw = malloc(uncomp_size);
                if (symtab_raw)
                    memcpy(symtab_raw, file_data + data_start, uncomp_size);
            } else if (compression == 8) {
                /* Deflate */
                symtab_raw = inflate_data(file_data + data_start, comp_size, uncomp_size);
            }

            if (!symtab_raw) {
                if (verbose)
                    fprintf(stderr, "[cosmoext] Failed to decompress symtab\n");
                goto cleanup;
            }

            /* Parse symbol table header */
            /* Format from symbols.internal.h:
             * Offset  Size  Field
             * 0       4     magic (0x544D5953 "SYMT")
             * 4       4     abi (1)
             * 8       8     count
             * 16      8     size
             * 24      8     mapsize
             * 32      8     addr_base
             * 40      8     addr_end
             * 48      8     names_ptr (ignored in file)
             * 56      8     name_base_ptr (ignored in file)
             * 64      4     names_offset
             * 68      4     name_base_offset
             * 72      ...   symbols[] (each is 8 bytes: x(4) + y(4))
             */
            if (uncomp_size < 72)
                goto cleanup;

            uint32_t magic = *(uint32_t *)(symtab_raw);
            if (magic != 0x544D5953) { /* "SYMT" */
                if (verbose)
                    fprintf(stderr, "[cosmoext] Bad symtab magic: 0x%x\n", magic);
                goto cleanup;
            }

            st = calloc(1, sizeof(SimpleSymbolTable));
            if (!st)
                goto cleanup;

            st->count = *(uint64_t *)(symtab_raw + 8);
            st->addr_base = *(int64_t *)(symtab_raw + 32); /* Fixed: was 40, should be 32 */
            uint32_t names_offset = *(uint32_t *)(symtab_raw + 64);
            uint32_t name_base_offset = *(uint32_t *)(symtab_raw + 68);

            if (verbose) {
                fprintf(stderr, "[cosmoext] Symtab: %llu symbols, addr_base=0x%llx\n",
                        (unsigned long long)st->count, (unsigned long long)st->addr_base);
            }

            /* Copy symbol addresses (each symbol is 8 bytes: x(4) + y(4)) */
            size_t sym_array_offset = 72; /* After header */
            st->sym_addrs = malloc(st->count * sizeof(uint32_t));
            if (!st->sym_addrs) {
                free_simple_symtab(st);
                st = NULL;
                goto cleanup;
            }

            for (uint64_t i = 0; i < st->count; i++) {
                st->sym_addrs[i] = *(uint32_t *)(symtab_raw + sym_array_offset + i * 8);
            }

            /* Copy names array */
            st->names = malloc(st->count * sizeof(uint32_t));
            if (!st->names) {
                free_simple_symtab(st);
                st = NULL;
                goto cleanup;
            }
            memcpy(st->names, symtab_raw + names_offset, st->count * sizeof(uint32_t));

            /* Copy name strings */
            size_t name_base_size = uncomp_size - name_base_offset;
            st->name_base = malloc(name_base_size);
            if (!st->name_base) {
                free_simple_symtab(st);
                st = NULL;
                goto cleanup;
            }
            memcpy(st->name_base, symtab_raw + name_base_offset, name_base_size);

            break; /* Found and parsed */
        }

        offset = header_pos + 1;
    }

cleanup:
    if (f)
        fclose(f);
    if (file_data)
        free(file_data);
    if (symtab_raw)
        free(symtab_raw);
    return st;
}

/* Look up symbol in our simple table */
static uint64_t lookup_symbol_simple(SimpleSymbolTable *st, const char *target_name)
{
    if (!st)
        return 0;

    const char *names_to_try[2] = {target_name, get_symbol_alias(target_name)};

    for (int attempt = 0; attempt < 2; attempt++) {
        const char *search_name = names_to_try[attempt];
        if (!search_name)
            continue;

        for (uint64_t i = 0; i < st->count; i++) {
            const char *sym_name = st->name_base + st->names[i];
            if (strcmp(sym_name, search_name) == 0) {
                return st->addr_base + st->sym_addrs[i];
            }
        }
    }
    return 0;
}

/*
 * Internal loading function that accepts an optional spec.
 * When spec is provided, it's used for multi-phase init modules
 * to properly set __package__ before the module's exec runs.
 */
static PyObject *cosmoext_load_internal(const char *path, PyObject *spec)
{
    FILE *f = NULL;
    void *blob = NULL;
    void *mapped = NULL;
    size_t map_size = 0;
    CosmoExtReloc *relocs = NULL;
    CosmoExtExternalSym *ext_syms = NULL;
    char *string_table = NULL;
    int verbose = 1; /* Set to 1 for debug output */

    f = fopen(path, "rb");
    if (!f) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        goto error;
    }

    /* Read fat header */
    CosmoExtFatHeader fat_header = {0};
    if (fread(&fat_header, sizeof(fat_header), 1, f) != 1) {
        PyErr_SetString(PyExc_ValueError, "Failed to read header");
        goto error;
    }

    if (fat_header.magic != COSMOEXT_MAGIC) {
        PyErr_SetString(PyExc_ValueError, "Invalid magic");
        goto error;
    }

    if (fat_header.version != COSMOEXT_VERSION) {
        PyErr_Format(PyExc_ValueError, "Unsupported cosmoext version: %u (expected %d)",
                     fat_header.version, COSMOEXT_VERSION);
        goto error;
    }

    /* Select architecture-specific payload */
    uint64_t payload_offset;
    uint64_t payload_size;
    const char *arch_name;

    if (IsAarch64()) {
        if (!(fat_header.flags & COSMOEXT_HAS_AARCH64)) {
            PyErr_SetString(PyExc_ValueError, "cosmoext file does not contain aarch64 code");
            goto error;
        }
        payload_offset = fat_header.aarch64_offset;
        payload_size = fat_header.aarch64_size;
        arch_name = "aarch64";
    } else {
        if (!(fat_header.flags & COSMOEXT_HAS_X86_64)) {
            PyErr_SetString(PyExc_ValueError, "cosmoext file does not contain x86_64 code");
            goto error;
        }
        payload_offset = fat_header.x86_64_offset;
        payload_size = fat_header.x86_64_size;
        arch_name = "x86_64";
    }

    if (verbose) {
        fprintf(stderr, "[cosmoext] Loading %s payload at offset %llu, size %llu\n", arch_name,
                (unsigned long long)payload_offset, (unsigned long long)payload_size);
    }

    /* Seek to architecture payload */
    if (fseek(f, payload_offset, SEEK_SET) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        goto error;
    }

    /* Read arch-specific header */
    CosmoExtArchHeader header = {0};
    if (fread(&header, sizeof(header), 1, f) != 1) {
        PyErr_SetString(PyExc_ValueError, "Failed to read arch header");
        goto error;
    }

    if (verbose) {
        fprintf(stderr, "[cosmoext] Total size: %llu bytes\n",
                (unsigned long long)header.total_size);
        fprintf(stderr, "[cosmoext] Sections: %llu, Internal relocs: %llu\n",
                (unsigned long long)header.num_sections, (unsigned long long)header.num_relocs);
        fprintf(stderr, "[cosmoext] External symbols: %llu, String table: %llu bytes\n",
                (unsigned long long)header.num_external_symbols,
                (unsigned long long)header.string_table_size);
        if (header.get_def_offset > 0) {
            fprintf(stderr, "[cosmoext] get_def_offset: 0x%llx\n",
                    (unsigned long long)header.get_def_offset);
        }
    }

    /* Calculate offsets within this payload (relative to payload_offset) */
    size_t arch_header_size = sizeof(CosmoExtArchHeader);
    size_t section_headers_offset = payload_offset + arch_header_size;
    size_t reloc_offset = section_headers_offset + header.num_sections * 24;
    size_t ext_sym_offset = reloc_offset + header.num_relocs * 24;
    (void)ext_sym_offset; /* suppress unused warning */

    /* Skip section headers (we don't need them for loading) */
    if (fseek(f, reloc_offset, SEEK_SET) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        goto error;
    }

    /* Read internal relocations */
    if (header.num_relocs > 0) {
        relocs = PyMem_Malloc(header.num_relocs * sizeof(CosmoExtReloc));
        if (!relocs) {
            PyErr_NoMemory();
            goto error;
        }
        if (fread(relocs, 24, header.num_relocs, f) != header.num_relocs) {
            PyErr_SetString(PyExc_ValueError, "Failed to read relocations");
            goto error;
        }
    }

    /* Read external symbols */
    if (header.num_external_symbols > 0) {
        ext_syms = PyMem_Malloc(header.num_external_symbols * sizeof(CosmoExtExternalSym));
        if (!ext_syms) {
            PyErr_NoMemory();
            goto error;
        }
        if (fread(ext_syms, 16, header.num_external_symbols, f) != header.num_external_symbols) {
            PyErr_SetString(PyExc_ValueError, "Failed to read external symbols");
            goto error;
        }

        /* Read string table */
        if (header.string_table_size > 0) {
            string_table = PyMem_Malloc(header.string_table_size);
            if (!string_table) {
                PyErr_NoMemory();
                goto error;
            }
            if (fread(string_table, 1, header.string_table_size, f) != header.string_table_size) {
                PyErr_SetString(PyExc_ValueError, "Failed to read string table");
                goto error;
            }
        }
    }

    /* Seek to blob data (header_size is relative to start of this payload) */
    if (fseek(f, payload_offset + header.header_size, SEEK_SET) != 0) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        goto error;
    }

    /* Read blob */
    blob = PyMem_Malloc(header.total_size);
    if (!blob) {
        PyErr_NoMemory();
        goto error;
    }

    if (fread(blob, 1, header.total_size, f) != header.total_size) {
        PyErr_SetString(PyExc_ValueError, "Failed to read blob");
        goto error;
    }

    fclose(f);
    f = NULL;

    /* Load symbol table for external symbol resolution */
    SimpleSymbolTable *symtab = NULL;

    if (header.num_external_symbols > 0) {
        /* Get path to current executable */
        const char *exe_path = NULL;
#ifdef __COSMOPOLITAN__
        extern char *GetProgramExecutableName(void);
        exe_path = GetProgramExecutableName();
#endif
        if (!exe_path) {
            exe_path = "/proc/self/exe"; /* Linux fallback */
        }

        symtab = load_symtab_from_ape(exe_path, verbose);

        if (!symtab) {
            PyErr_SetString(PyExc_RuntimeError,
                            "Failed to load symbol table from python.com. "
                            "Make sure the binary contains .symtab.{arch} in its ZIP directory.");
            goto error;
        }
    }

    /* Map executable memory */
    size_t page_size = 4096;
    map_size = ((header.total_size + page_size - 1) / page_size) * page_size;

    int map_flags = MAP_PRIVATE | MAP_ANONYMOUS;
    int use_mprotect = 0;
    int use_jit_protect = 0;

    if (verbose) {
        fprintf(stderr, "[cosmoext] IsXnu=%d IsAarch64=%d\n", IsXnu(), IsAarch64());
    }

#ifdef __COSMOPOLITAN__
    if (IsXnu() && IsAarch64() && __syslib && __syslib->__pthread_jit_write_protect_np) {
        int jit_flags = map_flags | MAP_JIT;
        mapped = mmap(NULL, map_size, PROT_READ | PROT_WRITE | PROT_EXEC, jit_flags, -1, 0);
        if (mapped != MAP_FAILED) {
            use_jit_protect = 1;
            __syslib->__pthread_jit_write_protect_np(0);
        }
    }

    if (mapped == MAP_FAILED && IsXnu())
#else
    if (IsXnu())
#endif
    {
        mapped = mmap(NULL, map_size, PROT_READ | PROT_WRITE, map_flags, -1, 0);
        use_mprotect = 1;
    }

    if (mapped == MAP_FAILED || mapped == NULL) {
        if (verbose) {
            fprintf(stderr, "[cosmoext] Trying mmap RWX\n");
        }
        mapped = mmap(NULL, map_size, PROT_READ | PROT_WRITE | PROT_EXEC, map_flags, -1, 0);
        if (verbose) {
            fprintf(stderr, "[cosmoext] mmap RWX result: %p, errno=%d\n", mapped, errno);
        }
        if (mapped == MAP_FAILED) {
            if (verbose) {
                fprintf(stderr, "[cosmoext] Trying mmap RW\n");
            }
            mapped = mmap(NULL, map_size, PROT_READ | PROT_WRITE, map_flags, -1, 0);
            if (verbose) {
                fprintf(stderr, "[cosmoext] mmap RW result: %p, errno=%d\n", mapped, errno);
            }
            use_mprotect = 1;
        }
    }

    if (mapped == MAP_FAILED) {
        PyErr_SetFromErrno(PyExc_OSError);
        goto error;
    }

    if (verbose) {
        fprintf(stderr,
                "[cosmoext] Final mapped at %p (%zu bytes), use_mprotect=%d, use_jit_protect=%d\n",
                mapped, map_size, use_mprotect, use_jit_protect);
    }

    /* Apply internal relocations */
    uintptr_t actual_addr = (uintptr_t)mapped;
    (void)header.load_address; /* Original load address - for debugging only */

    if (verbose && header.num_relocs > 0) {
        fprintf(stderr, "[cosmoext] Applying %llu internal relocations\n",
                (unsigned long long)header.num_relocs);
    }

    for (uint64_t i = 0; i < header.num_relocs; i++) {
        CosmoExtReloc *r = &relocs[i];
        uintptr_t target = actual_addr + r->target_offset;
        uintptr_t patch_addr = actual_addr + r->blob_offset; /* Where this instruction will be */

        /* Dispatch based on relocation type */
        switch (r->reloc_type) {
            case R_X86_64_64:
            case R_AARCH64_ABS64:
                /* 64-bit absolute */
                memcpy((char *)blob + r->blob_offset, &target, 8);
                break;

            case R_AARCH64_ADR_PREL_PG_HI21: {
                /* ADRP: Page(S + A) - Page(P) */
                uint64_t page_s = target & ~0xFFFULL;
                uint64_t page_p = patch_addr & ~0xFFFULL;
                int64_t page_offset = (int64_t)(page_s - page_p);
                int64_t imm = page_offset >> 12;
                uint32_t immlo = imm & 0x3;
                uint32_t immhi = (imm >> 2) & 0x7FFFF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0x9F00001F) | (immlo << 29) | (immhi << 5);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_ADD_ABS_LO12_NC: {
                /* ADD immediate: low 12 bits of target */
                uint32_t imm12 = target & 0xFFF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_LDST64_ABS_LO12_NC: {
                /* LDR/STR 64-bit: low 12 bits scaled by 8 */
                uint32_t imm12 = (target >> 3) & 0x1FF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_LDST32_ABS_LO12_NC: {
                /* LDR/STR 32-bit: low 12 bits scaled by 4 */
                uint32_t imm12 = (target >> 2) & 0x3FF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_LDST16_ABS_LO12_NC: {
                /* LDR/STR 16-bit: low 12 bits scaled by 2 */
                uint32_t imm12 = (target >> 1) & 0x7FF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_LDST8_ABS_LO12_NC: {
                /* LDR/STR 8-bit: low 12 bits, no scaling */
                uint32_t imm12 = target & 0xFFF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_LDST128_ABS_LO12_NC: {
                /* LDR/STR 128-bit: low 12 bits scaled by 16 */
                uint32_t imm12 = (target >> 4) & 0xFF;
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                insn = (insn & 0xFFC003FF) | (imm12 << 10);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            case R_AARCH64_MOVW_UABS_G0_NC:
            case R_AARCH64_MOVW_UABS_G1_NC:
            case R_AARCH64_MOVW_UABS_G2_NC:
            case R_AARCH64_MOVW_UABS_G3: {
                /* MOVZ/MOVK with 16-bit immediate chunks of 64-bit address */
                uint32_t insn;
                memcpy(&insn, (char *)blob + r->blob_offset, 4);
                uint32_t imm16;
                switch (r->reloc_type) {
                    case R_AARCH64_MOVW_UABS_G0_NC:
                        imm16 = target & 0xFFFF; /* bits 0-15 */
                        break;
                    case R_AARCH64_MOVW_UABS_G1_NC:
                        imm16 = (target >> 16) & 0xFFFF; /* bits 16-31 */
                        break;
                    case R_AARCH64_MOVW_UABS_G2_NC:
                        imm16 = (target >> 32) & 0xFFFF; /* bits 32-47 */
                        break;
                    case R_AARCH64_MOVW_UABS_G3:
                        imm16 = (target >> 48) & 0xFFFF; /* bits 48-63 */
                        break;
                    default:
                        imm16 = 0;
                        break;
                }
                /* imm16 goes into bits 5-20 of the instruction */
                insn = (insn & 0xFFE0001F) | (imm16 << 5);
                memcpy((char *)blob + r->blob_offset, &insn, 4);
                break;
            }

            default:
                /* Fallback for unknown types: use size field */
                if (r->size == 8) {
                    memcpy((char *)blob + r->blob_offset, &target, 8);
                } else if (r->size == 4) {
                    uint32_t val32 = (uint32_t)target;
                    memcpy((char *)blob + r->blob_offset, &val32, 4);
                }
                break;
        }
    }

    /* Resolve and apply external symbols */
    if (header.num_external_symbols > 0) {
        if (verbose) {
            fprintf(stderr, "[cosmoext] Resolving %llu external symbols\n",
                    (unsigned long long)header.num_external_symbols);
        }

        /*
         * On macOS ARM64, ASLR means the binary isn't loaded at addr_base.
         * Calculate the slide by comparing a known symbol's table address
         * to its actual runtime address.
         */
        int64_t slide = 0;
        if (verbose) {
            fprintf(stderr, "[cosmoext] DEBUG: Checking ASLR slide...\n");
        }
#ifdef __COSMOPOLITAN__
        if (verbose) {
            fprintf(stderr, "[cosmoext] DEBUG: In __COSMOPOLITAN__ block, IsXnu=%d, IsAarch64=%d\n",
                    IsXnu(), IsAarch64());
        }
        if (IsXnu() && IsAarch64()) {
            /* Use PyModule_Create2 as reference - we have it linked in */
            uint64_t table_addr = lookup_symbol_simple(symtab, "PyModule_Create2");
            if (table_addr != 0) {
                /* Get actual runtime address - PyModule_Create2 is a Python C API function */
                /* Note: We need the ACTUAL runtime address, not the link-time address */
                /* The & operator gives us the link-time address which is rebased at runtime */
                void *func_ptr = (void *)PyModule_Create2;
                uint64_t actual_addr = (uint64_t)func_ptr;

                if (verbose) {
                    fprintf(stderr, "[cosmoext] DEBUG: &PyModule_Create2 = %p\n",
                            (void *)&PyModule_Create2);
                    fprintf(stderr, "[cosmoext] DEBUG: (void*)PyModule_Create2 = %p\n", func_ptr);
                    fprintf(stderr, "[cosmoext] DEBUG: symtab addr_base = 0x%llx\n",
                            (unsigned long long)symtab->addr_base);
                }

                slide = (int64_t)actual_addr - (int64_t)table_addr;
                if (verbose) {
                    fprintf(stderr, "[cosmoext] ASLR slide: 0x%llx (table=0x%llx, actual=0x%llx)\n",
                            (unsigned long long)slide, (unsigned long long)table_addr,
                            (unsigned long long)actual_addr);
                }
            } else if (verbose) {
                fprintf(stderr, "[cosmoext] WARNING: PyModule_Create2 not in symbol table\n");
            }
        }
#endif

        for (uint64_t i = 0; i < header.num_external_symbols; i++) {
            CosmoExtExternalSym *es = &ext_syms[i];
            const char *sym_name = string_table + es->name_offset;

            uint64_t addr = lookup_symbol_simple(symtab, sym_name);
            if (addr == 0) {
                PyErr_Format(PyExc_RuntimeError, "Failed to resolve symbol: %s", sym_name);
                goto error;
            }

            /* Apply ASLR slide */
            addr = (uint64_t)((int64_t)addr + slide);

            if (verbose) {
                fprintf(stderr, "[cosmoext]   %s -> 0x%llx (patch at 0x%llx)\n", sym_name,
                        (unsigned long long)addr, (unsigned long long)es->patch_offset);
            }

            /* Patch the address into the blob */
            memcpy((char *)blob + es->patch_offset, &addr, 8);
        }
    }

    /* Copy to mapped memory */
    memcpy(mapped, blob, header.total_size);
    PyMem_Free(blob);
    blob = NULL;

    /*
     * On macOS ARM64 with MAP_JIT, the entire region becomes non-writable
     * after pthread_jit_write_protect_np(1). We need to copy writable data
     * (module def, method tables, strings) to regular heap memory.
     */
    void *heap_data = NULL;
    size_t heap_data_size = 0;

#ifdef __COSMOPOLITAN__
    if (use_jit_protect && IsAarch64()) {
        /* Read section headers to find writable sections */
        /* Sections are at offset 72 (after arch header), each is 24 bytes */
        FILE *sf = fopen(path, "rb");
        if (!sf) {
            PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
            goto error;
        }

/* Find writable sections and store their ranges */
#define MAX_WRITABLE_SECTIONS 8
#define MAX_TLS_SECTIONS      4
        struct {
            size_t start;
            size_t end;
        } writable_ranges[MAX_WRITABLE_SECTIONS];
        struct {
            size_t offset;
            size_t size;
        } tls_sections[MAX_TLS_SECTIONS];
        int num_writable = 0;
        int num_tls = 0;
        size_t tls_total_size = 0;
        size_t data_start = header.total_size; /* Overall start (high) */
        size_t data_end = 0;                   /* Overall end (low) */

        fseek(sf, section_headers_offset, SEEK_SET); /* Section headers start after arch header */
        for (uint64_t i = 0; i < header.num_sections; i++) {
            uint64_t sec_offset, sec_size;
            uint32_t sec_flags;
            if (fread(&sec_offset, 8, 1, sf) != 1 || fread(&sec_size, 8, 1, sf) != 1 ||
                fread(&sec_flags, 4, 1, sf) != 1) {
                fclose(sf);
                PyErr_SetString(PyExc_ValueError, "Failed to read section header");
                goto error;
            }
            fseek(sf, 4, SEEK_CUR); /* Skip padding */

            /* Check if TLS section (flags & 4) */
            if ((sec_flags & COSMOEXT_SECTION_TLS) && sec_size > 0) {
                if (num_tls < MAX_TLS_SECTIONS) {
                    tls_sections[num_tls].offset = sec_offset;
                    tls_sections[num_tls].size = sec_size;
                    num_tls++;
                    tls_total_size += sec_size;
                }
                if (verbose) {
                    fprintf(stderr, "[cosmoext] TLS section %llu: offset=0x%llx, size=%llu\n",
                            (unsigned long long)i, (unsigned long long)sec_offset,
                            (unsigned long long)sec_size);
                }
            }

            /* Check if writable (flags & 2) and not executable (flags & 1) */
            if ((sec_flags & COSMOEXT_SECTION_WRITE) && !(sec_flags & COSMOEXT_SECTION_EXEC) &&
                sec_size > 0) {
                if (num_writable < MAX_WRITABLE_SECTIONS) {
                    writable_ranges[num_writable].start = sec_offset;
                    writable_ranges[num_writable].end = sec_offset + sec_size;
                    num_writable++;
                }
                if (sec_offset < data_start)
                    data_start = sec_offset;
                if (sec_offset + sec_size > data_end)
                    data_end = sec_offset + sec_size;
                if (verbose) {
                    fprintf(stderr, "[cosmoext] Writable section %llu: offset=0x%llx, size=%llu\n",
                            (unsigned long long)i, (unsigned long long)sec_offset,
                            (unsigned long long)sec_size);
                }
            }
        }
        fclose(sf);

        /* Initialize TLS data: copy .tdata content to TLS region */
        if (num_tls > 0) {
#ifdef __COSMOPOLITAN__
            /* Get thread pointer */
            uintptr_t tp;
#ifdef __aarch64__
            __asm__ volatile("mov %0, x28" : "=r"(tp));
#else
            __asm__ volatile("mov %%fs:0, %0" : "=r"(tp));
#endif
            char *tls_dest = (char *)tp + COSMOEXT_TLS_BASE_OFFSET;
            size_t tls_offset = 0;

            if (verbose) {
                fprintf(stderr,
                        "[cosmoext] Initializing TLS: %d sections, %zu total bytes at TP+0x%x\n",
                        num_tls, tls_total_size, COSMOEXT_TLS_BASE_OFFSET);
            }

            for (int i = 0; i < num_tls; i++) {
                /* Copy TLS data from blob to TLS region */
                memcpy(tls_dest + tls_offset, (char *)mapped + tls_sections[i].offset,
                       tls_sections[i].size);
                if (verbose) {
                    fprintf(stderr,
                            "[cosmoext]   Copied TLS section %d: %zu bytes from blob+0x%zx to "
                            "TP+0x%zx\n",
                            i, tls_sections[i].size, tls_sections[i].offset,
                            COSMOEXT_TLS_BASE_OFFSET + tls_offset);
                }
                tls_offset += tls_sections[i].size;
            }
#endif
        }

/* Helper to check if offset is in a writable section */
#define IS_WRITABLE(off)                                                                 \
    ({                                                                                   \
        int _w = 0;                                                                      \
        for (int _i = 0; _i < num_writable; _i++) {                                      \
            if ((off) >= writable_ranges[_i].start && (off) < writable_ranges[_i].end) { \
                _w = 1;                                                                  \
                break;                                                                   \
            }                                                                            \
        }                                                                                \
        _w;                                                                              \
    })

        if (data_end > data_start) {
            heap_data_size = data_end - data_start;
            heap_data = PyMem_Malloc(heap_data_size);
            if (!heap_data) {
                PyErr_NoMemory();
                goto error;
            }

            /* Copy data to heap */
            memcpy(heap_data, (char *)mapped + data_start, heap_data_size);

            if (verbose) {
                fprintf(stderr, "[cosmoext] Copied %zu bytes of data (0x%zx-0x%zx) to heap at %p\n",
                        heap_data_size, data_start, data_end, heap_data);
                /* Debug: print function pointers in METHODS array */
                /* METHODS is at MODULE_DEF + 88, and ml_meth is at PyMethodDef + 8 */
                size_t methods_off = 88; /* Offset from data section start to METHODS */
                size_t first_ml_meth = methods_off + 8; /* First ml_meth */
                size_t second_ml_meth =
                    methods_off + 32 + 8; /* Second ml_meth (each PyMethodDef is 32 bytes) */
                if (first_ml_meth + 8 <= heap_data_size) {
                    uint64_t fp1, fp2;
                    memcpy(&fp1, (char *)heap_data + first_ml_meth, 8);
                    memcpy(&fp2, (char *)heap_data + second_ml_meth, 8);
                    fprintf(stderr,
                            "[cosmoext] DEBUG heap METHODS[0].ml_meth at heap+0x%zx = 0x%llx\n",
                            first_ml_meth, (unsigned long long)fp1);
                    fprintf(stderr,
                            "[cosmoext] DEBUG heap METHODS[1].ml_meth at heap+0x%zx = 0x%llx\n",
                            second_ml_meth, (unsigned long long)fp2);
                    fprintf(stderr, "[cosmoext] DEBUG expected code base = %p\n", mapped);
                }
            }

            /* Update internal pointers to point to heap copy instead of JIT region */
            uintptr_t heap_data_base = (uintptr_t)heap_data;

            for (uint64_t i = 0; i < header.num_relocs; i++) {
                CosmoExtReloc *r = &relocs[i];
                /* Only process relocations that target writable sections */
                if (!IS_WRITABLE(r->target_offset))
                    continue;

                /* This relocation points into a writable section - update to heap */
                uintptr_t old_value = (uintptr_t)mapped + r->target_offset;
                uintptr_t new_value = heap_data_base + (r->target_offset - data_start);

                /* Update pointer in JIT region (code references to data) */
                if (!IS_WRITABLE(r->blob_offset)) {
                    /* Must handle instruction-embedded relocations specially */
                    switch (r->reloc_type) {
                        case R_AARCH64_ABS64:
                            /* 64-bit absolute - direct value */
                            memcpy((char *)mapped + r->blob_offset, &new_value, 8);
                            break;

                        case R_AARCH64_MOVW_UABS_G0_NC:
                        case R_AARCH64_MOVW_UABS_G1_NC:
                        case R_AARCH64_MOVW_UABS_G2_NC:
                        case R_AARCH64_MOVW_UABS_G3: {
                            /* MOVZ/MOVK: re-encode imm16 into instruction */
                            uint32_t insn;
                            memcpy(&insn, (char *)mapped + r->blob_offset, 4);
                            uint32_t imm16;
                            switch (r->reloc_type) {
                                case R_AARCH64_MOVW_UABS_G0_NC:
                                    imm16 = new_value & 0xFFFF;
                                    break;
                                case R_AARCH64_MOVW_UABS_G1_NC:
                                    imm16 = (new_value >> 16) & 0xFFFF;
                                    break;
                                case R_AARCH64_MOVW_UABS_G2_NC:
                                    imm16 = (new_value >> 32) & 0xFFFF;
                                    break;
                                case R_AARCH64_MOVW_UABS_G3:
                                    imm16 = (new_value >> 48) & 0xFFFF;
                                    break;
                                default:
                                    imm16 = 0;
                                    break;
                            }
                            insn = (insn & 0xFFE0001F) | (imm16 << 5);
                            memcpy((char *)mapped + r->blob_offset, &insn, 4);
                            break;
                        }

                        case R_AARCH64_ADR_PREL_PG_HI21: {
                            /* ADRP - must recalculate with new target */
                            uintptr_t patch_addr = (uintptr_t)mapped + r->blob_offset;
                            uint64_t page_s = new_value & ~0xFFFULL;
                            uint64_t page_p = patch_addr & ~0xFFFULL;
                            int64_t page_offset = (int64_t)(page_s - page_p);
                            int64_t imm = page_offset >> 12;
                            uint32_t immlo = imm & 0x3;
                            uint32_t immhi = (imm >> 2) & 0x7FFFF;
                            uint32_t insn;
                            memcpy(&insn, (char *)mapped + r->blob_offset, 4);
                            insn = (insn & 0x9F00001F) | (immlo << 29) | (immhi << 5);
                            memcpy((char *)mapped + r->blob_offset, &insn, 4);
                            break;
                        }

                        case R_AARCH64_ADD_ABS_LO12_NC: {
                            /* ADD imm12: low 12 bits of target */
                            uint32_t imm12 = new_value & 0xFFF;
                            uint32_t insn;
                            memcpy(&insn, (char *)mapped + r->blob_offset, 4);
                            insn = (insn & 0xFFC003FF) | (imm12 << 10);
                            memcpy((char *)mapped + r->blob_offset, &insn, 4);
                            break;
                        }

                        case R_AARCH64_LDST64_ABS_LO12_NC: {
                            uint32_t imm12 = (new_value >> 3) & 0x1FF;
                            uint32_t insn;
                            memcpy(&insn, (char *)mapped + r->blob_offset, 4);
                            insn = (insn & 0xFFC003FF) | (imm12 << 10);
                            memcpy((char *)mapped + r->blob_offset, &insn, 4);
                            break;
                        }

                        default:
                            /* Fallback for other types: use size field */
                            if (r->size == 8) {
                                memcpy((char *)mapped + r->blob_offset, &new_value, 8);
                            } else if (r->size == 4) {
                                uint32_t val32 = (uint32_t)new_value;
                                memcpy((char *)mapped + r->blob_offset, &val32, 4);
                            }
                            break;
                    }
                    if (verbose) {
                        fprintf(
                            stderr,
                            "[cosmoext]   Redirected reloc type %u at 0x%llx: 0x%llx -> 0x%llx\n",
                            r->reloc_type, (unsigned long long)r->blob_offset,
                            (unsigned long long)old_value, (unsigned long long)new_value);
                    }
                }

                /* Also update pointer in heap copy (data references to other data) */
                if (IS_WRITABLE(r->blob_offset)) {
                    size_t heap_offset = r->blob_offset - data_start;
                    if (r->size == 8) {
                        memcpy((char *)heap_data + heap_offset, &new_value, 8);
                    } else if (r->size == 4) {
                        uint32_t val32 = (uint32_t)new_value;
                        memcpy((char *)heap_data + heap_offset, &val32, 4);
                    }
                    if (verbose) {
                        fprintf(stderr,
                                "[cosmoext]   Updated heap reloc at heap+0x%zx: -> 0x%llx\n",
                                heap_offset, (unsigned long long)new_value);
                    }
                }
            }

#undef IS_WRITABLE
#undef MAX_WRITABLE_SECTIONS
#undef MAX_TLS_SECTIONS
        }
    }
#endif

    /* Free relocation data now that we're done with it */
    if (relocs) {
        PyMem_Free(relocs);
        relocs = NULL;
    }
    if (ext_syms) {
        PyMem_Free(ext_syms);
        ext_syms = NULL;
    }
    if (string_table) {
        PyMem_Free(string_table);
        string_table = NULL;
    }
    if (symtab) {
        free_simple_symtab(symtab);
        symtab = NULL;
    }

    /* Change to executable mode */
    if (use_jit_protect) {
#ifdef __COSMOPOLITAN__
        if (verbose) {
            fprintf(stderr,
                    "[cosmoext] Switching JIT to executable (pthread_jit_write_protect_np(1))\n");
        }
        __syslib->__pthread_jit_write_protect_np(1);
        if (__syslib->__sys_icache_invalidate) {
            __syslib->__sys_icache_invalidate(mapped, map_size);
            if (verbose) {
                fprintf(stderr, "[cosmoext] Instruction cache invalidated\n");
            }
        }
#endif
    } else if (use_mprotect) {
        if (verbose) {
            fprintf(stderr, "[cosmoext] Calling mprotect for RX\n");
        }
        if (mprotect(mapped, map_size, PROT_READ | PROT_EXEC) != 0) {
            PyErr_SetFromErrno(PyExc_OSError);
            goto error;
        }
    } else {
        if (verbose) {
            fprintf(stderr, "[cosmoext] No protection change needed (RWX already set)\n");
        }
    }

    if (verbose) {
        fprintf(stderr, "[cosmoext] Calling init function at offset 0x%llx\n",
                (unsigned long long)header.init_offset);

        /* Debug: dump first 32 bytes of init function */
        unsigned char *init_bytes = (unsigned char *)mapped + header.init_offset;
        fprintf(stderr, "[cosmoext] DEBUG: Init function at %p, bytes:\n", (void *)init_bytes);
        for (int row = 0; row < 2; row++) {
            fprintf(stderr,
                    "[cosmoext]   %04llx:", (unsigned long long)(header.init_offset + row * 16));
            for (int col = 0; col < 16; col++) {
                fprintf(stderr, " %02x", init_bytes[row * 16 + col]);
            }
            fprintf(stderr, "\n");
        }

        fflush(stderr);
    }

    /* Call the init function */
    CosmoExtInitFunc init_func = (CosmoExtInitFunc)((char *)mapped + header.init_offset);

    if (verbose) {
        fprintf(stderr, "[cosmoext] About to call init at %p\n", (void *)init_func);

        /* Dump trampoline contents if they exist within mapped region */
        /* Note: trampoline offset varies by extension - only dump if within bounds */
        if (header.total_size > 0x1f70) { /* Check if trampolines might exist */
            /* Find first trampoline by looking for external symbols with patch offsets */
            fprintf(stderr, "[cosmoext] DEBUG: Trampolines (if any) are within blob\n");
        }

        /* Test read from mapped memory to verify it's accessible */
        fprintf(stderr, "[cosmoext] DEBUG: Testing read from mapped memory...\n");
        volatile uint64_t test_val = *(volatile uint64_t *)mapped;
        fprintf(stderr, "[cosmoext] DEBUG: Read from base succeeded: 0x%llx\n",
                (unsigned long long)test_val);

        /* Test read from 0x18f0 offset (where markupsafe's init LDRs from) */
        if (header.total_size > 0x18f0) {
            volatile uint64_t test_val2 = *(volatile uint64_t *)((char *)mapped + 0x18f0);
            fprintf(stderr, "[cosmoext] DEBUG: Read from 0x18f0 succeeded: 0x%llx\n",
                    (unsigned long long)test_val2);
        }

        fflush(stderr);
    }

    /* Test: Can we even read the first instruction? */
    if (verbose) {
        uint32_t first_insn;
        memcpy(&first_insn, (void *)init_func, 4);
        fprintf(stderr, "[cosmoext] DEBUG: First instruction = 0x%08x\n", first_insn);
        fflush(stderr);
    }

    void *init_result = init_func();
    if (verbose) {
        fprintf(stderr, "[cosmoext] Init returned: %p\n", init_result);
        fflush(stderr);
    }

    if (verbose) {
        fprintf(stderr, "[cosmoext] Init returned: %p\n", init_result);
        fflush(stderr);
    }

    /* Check for errors */
    if (PyErr_Occurred()) {
        munmap(mapped, map_size);
        return NULL;
    }

    if (!init_result) {
        PyErr_SetString(PyExc_RuntimeError, "Extension init returned NULL");
        munmap(mapped, map_size);
        return NULL;
    }

    /* Handle different return types */
    if (init_result == (void *)1) {
        /* Shim intercepted PyModuleDef_Init (multi-phase) */
        /* _cosmoext_get_captured_def offset from init is stored in header.
         * If not present (0), use architecture-specific default values.
         */
        size_t get_def_offset = header.get_def_offset;
        if (get_def_offset == 0) {
            /* Default offsets when not specified in header */
#if defined(__aarch64__)
            get_def_offset = 0xE8; /* ARM64: larger due to ADRP/ADD sequences */
#else
            get_def_offset = 0x98; /* x86_64: smaller code */
#endif
        }
        GetCapturedDefFunc get_def = (GetCapturedDefFunc)((char *)init_func + get_def_offset);

        if (verbose) {
            fprintf(stderr, "[cosmoext] Calling get_def at %p (init+0x%zx)\n", (void *)get_def,
                    get_def_offset);
            fflush(stderr);
        }

        PyModuleDef *def = get_def();

        if (verbose) {
            fprintf(stderr, "[cosmoext] get_def returned: %p\n", (void *)def);
            fflush(stderr);
        }

        if (!def) {
            PyErr_SetString(PyExc_RuntimeError, "Shim captured NULL def");
            munmap(mapped, map_size);
            return NULL;
        }

        /* Use provided spec if available (for proper __package__), else create dummy */
        PyObject *use_spec = spec;
        int spec_is_temp = 0;
        if (!use_spec) {
            use_spec = PyObject_CallMethod(PyImport_ImportModule("importlib.machinery"),
                                           "ModuleSpec", "sO", def->m_name, Py_None);
            if (!use_spec) {
                munmap(mapped, map_size);
                return NULL;
            }
            spec_is_temp = 1;
        }

        PyObject *module = PyModule_FromDefAndSpec(def, use_spec);
        if (spec_is_temp)
            Py_DECREF(use_spec);

        if (!module) {
            munmap(mapped, map_size);
            return NULL;
        }

        if (PyModule_ExecDef(module, def) < 0) {
            Py_DECREF(module);
            munmap(mapped, map_size);
            return NULL;
        }

        return module;
    }

    if (PyModule_Check(init_result)) {
        /* Single-phase init returned a module directly.
         * Check if we need to register with PyState_AddModule.
         * Some extensions already do this themselves (e.g., ujson). */
        PyObject *module = (PyObject *)init_result;
        PyModuleDef *def = PyModule_GetDef(module);
        if (def != NULL && def->m_slots == NULL) {
            /* Only for single-phase init (no slots) */
            /* Check if already registered by seeing if FindModule returns this module */
            PyObject *found = PyState_FindModule(def);
            if (found != module) {
                if (PyState_AddModule(module, def) < 0) {
                    /* Not fatal - just means PyState_FindModule won't work */
                    PyErr_Clear();
                }
            }
        }
        return module;
    }

    /* Assume it's a PyModuleDef* */
    PyModuleDef *def = (PyModuleDef *)init_result;

    PyObject *module;
    if (def->m_slots != NULL) {
        /* Use provided spec if available (for proper __package__), else create dummy */
        PyObject *use_spec = spec;
        int spec_is_temp = 0;
        if (!use_spec) {
            use_spec = PyObject_CallMethod(PyImport_ImportModule("importlib.machinery"),
                                           "ModuleSpec", "sO", def->m_name, Py_None);
            if (!use_spec) {
                munmap(mapped, map_size);
                return NULL;
            }
            spec_is_temp = 1;
        }

        module = PyModule_FromDefAndSpec(def, use_spec);
        if (spec_is_temp)
            Py_DECREF(use_spec);

        if (!module) {
            munmap(mapped, map_size);
            return NULL;
        }

        if (PyModule_ExecDef(module, def) < 0) {
            Py_DECREF(module);
            munmap(mapped, map_size);
            return NULL;
        }
    } else {
        module = PyModule_Create2(def, PYTHON_API_VERSION);
        if (!module) {
            munmap(mapped, map_size);
            return NULL;
        }
        /* Register single-phase init module so PyState_FindModule works.
         * Note: We created this module ourselves, so it's definitely not registered. */
        if (PyState_AddModule(module, def) < 0) {
            /* Not fatal - just means PyState_FindModule won't work */
            PyErr_Clear();
        }
    }

    return module;

error:
    if (f)
        fclose(f);
    if (blob)
        PyMem_Free(blob);
    if (relocs)
        PyMem_Free(relocs);
    if (ext_syms)
        PyMem_Free(ext_syms);
    if (string_table)
        PyMem_Free(string_table);
    if (symtab)
        free_simple_symtab(symtab);
    if (mapped && mapped != MAP_FAILED)
        munmap(mapped, map_size);
    return NULL;
}

/*
 * Public API: Load a .cosmoext file by path.
 * For simple use cases where you don't need to control the module spec.
 */
static PyObject *cosmoext_load(PyObject *Py_UNUSED(self), PyObject *args)
{
    const char *path;
    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;
    return cosmoext_load_internal(path, NULL);
}

/*
 * create_dynamic(spec) - Load a .cosmoext extension using a ModuleSpec
 *
 * This mirrors _imp.create_dynamic() but for .cosmoext files.
 * Key differences from load():
 * 1. Sets package context before calling init (enables relative imports)
 * 2. Uses the provided spec for PyModule_FromDefAndSpec (multi-phase init)
 *    This allows Cython's __pyx_pymod_create to set __package__ from spec.parent
 */
static PyObject *cosmoext_create_dynamic(PyObject *Py_UNUSED(self), PyObject *args)
{
    PyObject *spec;
    PyObject *name_obj = NULL;
    PyObject *path_obj = NULL;
    const char *name = NULL;
    const char *path = NULL;
#if PY_VERSION_HEX >= 0x030C0000
    const char *oldcontext = NULL;
#endif
    PyObject *result = NULL;

    if (!PyArg_ParseTuple(args, "O", &spec))
        return NULL;

    /* Extract name and origin (path) from spec */
    name_obj = PyObject_GetAttrString(spec, "name");
    if (!name_obj) {
        PyErr_SetString(PyExc_TypeError, "spec must have 'name' attribute");
        goto cleanup;
    }
    name = PyUnicode_AsUTF8(name_obj);
    if (!name)
        goto cleanup;

    path_obj = PyObject_GetAttrString(spec, "origin");
    if (!path_obj) {
        PyErr_SetString(PyExc_TypeError, "spec must have 'origin' attribute");
        goto cleanup;
    }
    path = PyUnicode_AsUTF8(path_obj);
    if (!path) {
        goto cleanup;
    }

    /* Set package context before loading (enables relative imports in init).
     * Note: _PyImport_SwapPackageContext only exists in Python 3.12+. */
#if PY_VERSION_HEX >= 0x030C0000
    oldcontext = _PyImport_SwapPackageContext(name);
#endif

    /* Call the internal load function with our spec.
     * The spec is used for multi-phase init modules so that
     * PyModule_FromDefAndSpec gets the correct parent for __package__.
     */
    result = cosmoext_load_internal(path, spec);

    /* Restore package context */
#if PY_VERSION_HEX >= 0x030C0000
    _PyImport_SwapPackageContext(oldcontext);
#endif

    if (result && PyModule_Check(result)) {
        /* Set/override module attributes from our spec */
        PyObject_SetAttrString(result, "__name__", name_obj);
        PyObject_SetAttrString(result, "__file__", path_obj);
        PyObject_SetAttrString(result, "__loader__", Py_None); /* Will be set by caller */
        PyObject_SetAttrString(result, "__spec__", spec);

        /* Set __package__ from spec.parent (may already be set by multi-phase init) */
        PyObject *parent = PyObject_GetAttrString(spec, "parent");
        if (parent) {
            PyObject_SetAttrString(result, "__package__", parent);
            Py_DECREF(parent);
        } else {
            PyErr_Clear();
            /* Fallback: derive from name */
            if (strchr(name, '.')) {
                char *pkg = strdup(name);
                char *dot = strrchr(pkg, '.');
                if (dot)
                    *dot = '\0';
                PyObject *pkg_obj = PyUnicode_FromString(pkg);
                PyObject_SetAttrString(result, "__package__", pkg_obj);
                Py_DECREF(pkg_obj);
                free(pkg);
            } else {
                PyObject_SetAttrString(result, "__package__", name_obj);
            }
        }
    }

cleanup:
    Py_XDECREF(name_obj);
    Py_XDECREF(path_obj);
    return result;
}

static PyMethodDef cosmoext_methods[] = {
    {"load", cosmoext_load, METH_VARARGS, "Load a .cosmoext file by path"},
    {"create_dynamic", cosmoext_create_dynamic, METH_VARARGS,
     "Load a .cosmoext file using a ModuleSpec (like _imp.create_dynamic)"},
    {NULL, NULL, 0, NULL}};

static struct PyModuleDef cosmoextmodule = {
    PyModuleDef_HEAD_INIT,
    "_cosmoext",
    "Native loader for .cosmoext extension blobs",
    -1,
    cosmoext_methods,
    NULL, /* m_slots */
    NULL, /* m_traverse */
    NULL, /* m_clear */
    NULL  /* m_free */
};

PyMODINIT_FUNC PyInit__cosmoext(void)
{
    return PyModule_Create(&cosmoextmodule);
}
