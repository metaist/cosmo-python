#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <sys/mman.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include "third_party/zlib/zlib.h"

/* OS and architecture detection at runtime for Cosmopolitan */
#ifdef __COSMOPOLITAN__
#define _COSMO_SOURCE 1
#include "libc/dce.h"  /* For IsXnu(), IsAarch64() runtime detection */
#include "libc/runtime/syslib.internal.h"  /* For __syslib JIT functions */
#include "libc/runtime/symbols.internal.h"  /* For GetSymbolTable() */
#else
#define IsXnu() 0
#define IsAarch64() 0
#endif

#define COSMOEXT_MAGIC 0x54584543
#define COSMOEXT_VERSION_3 3
#define COSMOEXT_VERSION_4 4

/* Format v3/v4/v5 header */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint64_t load_address;
    uint64_t total_size;
    uint64_t init_offset;
    uint64_t header_size;
    uint64_t num_sections;
    uint64_t num_relocs;
    /* v4 adds: */
    uint64_t num_external_symbols;
    uint64_t string_table_size;
    /* v5 adds: */
    uint64_t get_def_offset;  /* Offset from init to _cosmoext_get_captured_def, 0 if no shim */
} CosmoExtHeader;

typedef struct {
    uint64_t offset;
    uint64_t size;
    uint32_t flags;
    /* 4 bytes padding */
} CosmoExtSection;

typedef struct {
    uint64_t blob_offset;
    uint32_t size;
    /* 4 bytes padding */
    uint64_t target_offset;
} CosmoExtReloc;

typedef struct {
    uint64_t patch_offset;
    uint32_t name_offset;
    /* 4 bytes padding */
} CosmoExtExternalSym;

typedef void* (*CosmoExtInitFunc)(void);
typedef PyModuleDef* (*GetCapturedDefFunc)(void);

/* Symbol aliases for Cosmopolitan's mangled names */
static const char* get_symbol_alias(const char* name) {
    if (strcmp(name, "memmove") == 0) return "__memmove.default";
    if (strcmp(name, "iscntrl") == 0) return "__iscntrl";
    if (strcmp(name, "ispunct") == 0) return "__ispunct";
    if (strcmp(name, "isspace") == 0) return "__isspace";
    return NULL;
}

/*
 * Simple symbol table extracted from APE ZIP.
 * Format matches Cosmopolitan's SymbolTable but we manage memory ourselves.
 */
typedef struct {
    uint64_t count;
    int64_t addr_base;
    uint32_t *names;      /* Array of offsets into name_base */
    char *name_base;      /* Concatenated null-terminated names */
    uint32_t *sym_addrs;  /* Array of symbol start addresses (relative to addr_base) */
} SimpleSymbolTable;

static void free_simple_symtab(SimpleSymbolTable *st) {
    if (st) {
        if (st->names) free(st->names);
        if (st->name_base) free(st->name_base);
        if (st->sym_addrs) free(st->sym_addrs);
        free(st);
    }
}

/* Decompress raw deflate data using zlib */
static unsigned char* inflate_data(const unsigned char *comp_data, size_t comp_size, 
                                    size_t uncomp_size) {
    unsigned char *output = malloc(uncomp_size);
    if (!output) return NULL;
    
    z_stream strm;
    memset(&strm, 0, sizeof(strm));
    strm.next_in = (Bytef*)comp_data;
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
static SimpleSymbolTable* load_symtab_from_ape(const char *exe_path, int verbose) {
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
    if (!f) goto cleanup;
    
    /* Get file size */
    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    /* Read entire file (APE binaries are typically <100MB) */
    file_data = malloc(file_size);
    if (!file_data) goto cleanup;
    if (fread(file_data, 1, file_size, f) != (size_t)file_size) goto cleanup;
    fclose(f);
    f = NULL;
    
    /* Search for ZIP local file header with our target filename */
    const unsigned char pk_sig[4] = {0x50, 0x4B, 0x03, 0x04};
    size_t offset = 0;
    
    while (offset + 30 + target_len < (size_t)file_size) {
        /* Find next PK signature */
        unsigned char *pos = memmem(file_data + offset, file_size - offset, pk_sig, 4);
        if (!pos) break;
        
        size_t header_pos = pos - file_data;
        
        /* Parse ZIP local file header */
        if (header_pos + 30 > (size_t)file_size) break;
        
        uint16_t compression = *(uint16_t*)(pos + 8);
        uint32_t comp_size = *(uint32_t*)(pos + 18);
        uint32_t uncomp_size = *(uint32_t*)(pos + 22);
        uint16_t name_len = *(uint16_t*)(pos + 26);
        uint16_t extra_len = *(uint16_t*)(pos + 28);
        
        /* Check filename */
        if (name_len == target_len && 
            header_pos + 30 + name_len <= (size_t)file_size &&
            memcmp(pos + 30, target_name, target_len) == 0) {
            
            size_t data_start = header_pos + 30 + name_len + extra_len;
            if (data_start + comp_size > (size_t)file_size) break;
            
            if (verbose) {
                fprintf(stderr, "[cosmoext] Found %s at offset 0x%zx, size=%u->%u\n",
                        target_name, header_pos, comp_size, uncomp_size);
            }
            
            /* Decompress */
            if (compression == 0) {
                /* Stored */
                symtab_raw = malloc(uncomp_size);
                if (symtab_raw) memcpy(symtab_raw, file_data + data_start, uncomp_size);
            } else if (compression == 8) {
                /* Deflate */
                symtab_raw = inflate_data(file_data + data_start, comp_size, uncomp_size);
            }
            
            if (!symtab_raw) {
                if (verbose) fprintf(stderr, "[cosmoext] Failed to decompress symtab\n");
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
            if (uncomp_size < 72) goto cleanup;
            
            uint32_t magic = *(uint32_t*)(symtab_raw);
            if (magic != 0x544D5953) {  /* "SYMT" */
                if (verbose) fprintf(stderr, "[cosmoext] Bad symtab magic: 0x%x\n", magic);
                goto cleanup;
            }
            
            st = calloc(1, sizeof(SimpleSymbolTable));
            if (!st) goto cleanup;
            
            st->count = *(uint64_t*)(symtab_raw + 8);
            st->addr_base = *(int64_t*)(symtab_raw + 32);  /* Fixed: was 40, should be 32 */
            uint32_t names_offset = *(uint32_t*)(symtab_raw + 64);
            uint32_t name_base_offset = *(uint32_t*)(symtab_raw + 68);
            
            if (verbose) {
                fprintf(stderr, "[cosmoext] Symtab: %llu symbols, addr_base=0x%llx\n",
                        (unsigned long long)st->count, (unsigned long long)st->addr_base);
            }
            
            /* Copy symbol addresses (each symbol is 8 bytes: x(4) + y(4)) */
            size_t sym_array_offset = 72;  /* After header */
            st->sym_addrs = malloc(st->count * sizeof(uint32_t));
            if (!st->sym_addrs) { free_simple_symtab(st); st = NULL; goto cleanup; }
            
            for (uint64_t i = 0; i < st->count; i++) {
                st->sym_addrs[i] = *(uint32_t*)(symtab_raw + sym_array_offset + i * 8);
            }
            
            /* Copy names array */
            st->names = malloc(st->count * sizeof(uint32_t));
            if (!st->names) { free_simple_symtab(st); st = NULL; goto cleanup; }
            memcpy(st->names, symtab_raw + names_offset, st->count * sizeof(uint32_t));
            
            /* Copy name strings */
            size_t name_base_size = uncomp_size - name_base_offset;
            st->name_base = malloc(name_base_size);
            if (!st->name_base) { free_simple_symtab(st); st = NULL; goto cleanup; }
            memcpy(st->name_base, symtab_raw + name_base_offset, name_base_size);
            
            break;  /* Found and parsed */
        }
        
        offset = header_pos + 1;
    }
    
cleanup:
    if (f) fclose(f);
    if (file_data) free(file_data);
    if (symtab_raw) free(symtab_raw);
    return st;
}

/* Look up symbol in our simple table */
static uint64_t lookup_symbol_simple(SimpleSymbolTable *st, const char *target_name) {
    if (!st) return 0;
    
    const char *names_to_try[2] = {target_name, get_symbol_alias(target_name)};
    
    for (int attempt = 0; attempt < 2; attempt++) {
        const char *search_name = names_to_try[attempt];
        if (!search_name) continue;
        
        for (uint64_t i = 0; i < st->count; i++) {
            const char *sym_name = st->name_base + st->names[i];
            if (strcmp(sym_name, search_name) == 0) {
                return st->addr_base + st->sym_addrs[i];
            }
        }
    }
    return 0;
}



static PyObject*
cosmoext_load(PyObject *self, PyObject *args)
{
    const char *path;
    FILE *f = NULL;
    void *blob = NULL;
    void *mapped = NULL;
    size_t map_size = 0;
    CosmoExtReloc *relocs = NULL;
    CosmoExtExternalSym *ext_syms = NULL;
    char *string_table = NULL;
    int verbose = 0;  /* Set to 1 for debug */: Enable debug output */
    
    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;
    
    f = fopen(path, "rb");
    if (!f) {
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        goto error;
    }
    
    /* Read header - first read v3 size to check version */
    CosmoExtHeader header = {0};
    size_t v3_header_size = 56;  /* v3 header without external symbol fields */
    
    if (fread(&header, 1, v3_header_size, f) != v3_header_size) {
        PyErr_SetString(PyExc_ValueError, "Failed to read header");
        goto error;
    }
    
    if (header.magic != COSMOEXT_MAGIC) {
        PyErr_SetString(PyExc_ValueError, "Invalid magic");
        goto error;
    }
    
    int format_version = 0;
    if (header.version == 5) {
        format_version = 5;
        /* Read remaining v5 fields (v4 fields + get_def_offset) */
        if (fread(&header.num_external_symbols, 1, 24, f) != 24) {
            PyErr_SetString(PyExc_ValueError, "Failed to read v5 header");
            goto error;
        }
    } else if (header.version == COSMOEXT_VERSION_4) {
        format_version = 4;
        /* Read remaining v4 fields */
        if (fread(&header.num_external_symbols, 1, 16, f) != 16) {
            PyErr_SetString(PyExc_ValueError, "Failed to read v4 header");
            goto error;
        }
        header.get_def_offset = 0;  /* v4 doesn't have this, will use hardcoded fallback */
    } else if (header.version != COSMOEXT_VERSION_3) {
        PyErr_Format(PyExc_ValueError, "Unsupported version: %u", header.version);
        goto error;
    } else {
        format_version = 3;
        header.get_def_offset = 0;
    }
    
    if (verbose) {
        fprintf(stderr, "[cosmoext] Format version: %u\n", header.version);
        fprintf(stderr, "[cosmoext] Total size: %llu bytes\n", (unsigned long long)header.total_size);
        fprintf(stderr, "[cosmoext] Sections: %llu, Internal relocs: %llu\n",
                (unsigned long long)header.num_sections, (unsigned long long)header.num_relocs);
        if (format_version >= 4) {
            fprintf(stderr, "[cosmoext] External symbols: %llu, String table: %llu bytes\n",
                    (unsigned long long)header.num_external_symbols,
                    (unsigned long long)header.string_table_size);
        }
        if (format_version >= 5 && header.get_def_offset > 0) {
            fprintf(stderr, "[cosmoext] get_def_offset: 0x%llx\n",
                    (unsigned long long)header.get_def_offset);
        }
    }
    
    /* Calculate offsets for different parts of the header */
    size_t actual_header_size = format_version >= 5 ? 80 : (format_version >= 4 ? 72 : 56);
    size_t section_headers_offset = actual_header_size;
    size_t reloc_offset = section_headers_offset + header.num_sections * 24;
    size_t ext_sym_offset = reloc_offset + header.num_relocs * 24;
    size_t string_table_offset = ext_sym_offset + (format_version >= 4 ? header.num_external_symbols * 16 : 0);
    
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
    
    /* Read external symbols (v4 only) */
    if (format_version >= 4 && header.num_external_symbols > 0) {
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
    
    /* Seek to blob data */
    if (fseek(f, header.header_size, SEEK_SET) != 0) {
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
    
    /* Load symbol table for external symbol resolution (v4) */
    SimpleSymbolTable *symtab = NULL;
    
    if (format_version >= 4 && header.num_external_symbols > 0) {
        /* Get path to current executable */
        const char *exe_path = NULL;
#ifdef __COSMOPOLITAN__
        extern char *GetProgramExecutableName(void);
        exe_path = GetProgramExecutableName();
#endif
        if (!exe_path) {
            exe_path = "/proc/self/exe";  /* Linux fallback */
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
        mapped = mmap(NULL, map_size, 
                      PROT_READ | PROT_WRITE | PROT_EXEC,
                      jit_flags, -1, 0);
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
        mapped = mmap(NULL, map_size, 
                      PROT_READ | PROT_WRITE,
                      map_flags, -1, 0);
        use_mprotect = 1;
    }
    
    if (mapped == MAP_FAILED || mapped == NULL) {
        if (verbose) {
            fprintf(stderr, "[cosmoext] Trying mmap RWX\n");
        }
        mapped = mmap(NULL, map_size, 
                      PROT_READ | PROT_WRITE | PROT_EXEC,
                      map_flags, -1, 0);
        if (verbose) {
            fprintf(stderr, "[cosmoext] mmap RWX result: %p, errno=%d\n", mapped, errno);
        }
        if (mapped == MAP_FAILED) {
            if (verbose) {
                fprintf(stderr, "[cosmoext] Trying mmap RW\n");
            }
            mapped = mmap(NULL, map_size, 
                          PROT_READ | PROT_WRITE,
                          map_flags, -1, 0);
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
        fprintf(stderr, "[cosmoext] Final mapped at %p (%zu bytes), use_mprotect=%d, use_jit_protect=%d\n", 
                mapped, map_size, use_mprotect, use_jit_protect);
    }
    
    /* Apply internal relocations */
    uintptr_t actual_addr = (uintptr_t)mapped;
    
    if (verbose && header.num_relocs > 0) {
        fprintf(stderr, "[cosmoext] Applying %llu internal relocations\n",
                (unsigned long long)header.num_relocs);
    }
    
    for (uint64_t i = 0; i < header.num_relocs; i++) {
        CosmoExtReloc *r = &relocs[i];
        uintptr_t new_value = actual_addr + r->target_offset;
        
        if (r->size == 8) {
            memcpy((char*)blob + r->blob_offset, &new_value, 8);
        } else if (r->size == 4) {
            uint32_t val32 = (uint32_t)new_value;
            memcpy((char*)blob + r->blob_offset, &val32, 4);
        }
    }
    
    /* Resolve and apply external symbols (v4 only) */
    if (format_version >= 4 && header.num_external_symbols > 0) {
        if (verbose) {
            fprintf(stderr, "[cosmoext] Resolving %llu external symbols\n",
                    (unsigned long long)header.num_external_symbols);
        }
        
        for (uint64_t i = 0; i < header.num_external_symbols; i++) {
            CosmoExtExternalSym *es = &ext_syms[i];
            const char *sym_name = string_table + es->name_offset;
            
            uint64_t addr = lookup_symbol_simple(symtab, sym_name);
            if (addr == 0) {
                PyErr_Format(PyExc_RuntimeError, "Failed to resolve symbol: %s", sym_name);
                goto error;
            }
            
            if (verbose) {
                fprintf(stderr, "[cosmoext]   %s -> 0x%llx (patch at 0x%llx)\n",
                        sym_name, (unsigned long long)addr, (unsigned long long)es->patch_offset);
            }
            
            /* Patch the address into the blob */
            memcpy((char*)blob + es->patch_offset, &addr, 8);
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
        /* Sections are at offset 72 (after v4 header), each is 24 bytes */
        FILE *sf = fopen(path, "rb");
        if (!sf) {
            PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
            goto error;
        }
        
        /* Find writable sections and store their ranges */
        #define MAX_WRITABLE_SECTIONS 8
        struct { size_t start; size_t end; } writable_ranges[MAX_WRITABLE_SECTIONS];
        int num_writable = 0;
        size_t data_start = header.total_size;  /* Overall start (high) */
        size_t data_end = 0;                     /* Overall end (low) */
        
        fseek(sf, 72, SEEK_SET);  /* Section headers start at byte 72 */
        for (uint64_t i = 0; i < header.num_sections; i++) {
            uint64_t sec_offset, sec_size;
            uint32_t sec_flags;
            if (fread(&sec_offset, 8, 1, sf) != 1 ||
                fread(&sec_size, 8, 1, sf) != 1 ||
                fread(&sec_flags, 4, 1, sf) != 1) {
                fclose(sf);
                PyErr_SetString(PyExc_ValueError, "Failed to read section header");
                goto error;
            }
            fseek(sf, 4, SEEK_CUR);  /* Skip padding */
            
            /* Check if writable (flags & 2) and not executable (flags & 1) */
            if ((sec_flags & 2) && !(sec_flags & 1) && sec_size > 0) {
                if (num_writable < MAX_WRITABLE_SECTIONS) {
                    writable_ranges[num_writable].start = sec_offset;
                    writable_ranges[num_writable].end = sec_offset + sec_size;
                    num_writable++;
                }
                if (sec_offset < data_start) data_start = sec_offset;
                if (sec_offset + sec_size > data_end) data_end = sec_offset + sec_size;
                if (verbose) {
                    fprintf(stderr, "[cosmoext] Writable section %llu: offset=0x%llx, size=%llu\n",
                            (unsigned long long)i, (unsigned long long)sec_offset, 
                            (unsigned long long)sec_size);
                }
            }
        }
        fclose(sf);
        
        /* Helper to check if offset is in a writable section */
        #define IS_WRITABLE(off) ({ \
            int _w = 0; \
            for (int _i = 0; _i < num_writable; _i++) { \
                if ((off) >= writable_ranges[_i].start && (off) < writable_ranges[_i].end) { \
                    _w = 1; break; \
                } \
            } \
            _w; \
        })
        
        if (data_end > data_start) {
            heap_data_size = data_end - data_start;
            heap_data = PyMem_Malloc(heap_data_size);
            if (!heap_data) {
                PyErr_NoMemory();
                goto error;
            }
            
            /* Copy data to heap */
            memcpy(heap_data, (char*)mapped + data_start, heap_data_size);
            
            if (verbose) {
                fprintf(stderr, "[cosmoext] Copied %zu bytes of data (0x%zx-0x%zx) to heap at %p\n", 
                        heap_data_size, data_start, data_end, heap_data);
            }
            
            /* Update internal pointers to point to heap copy instead of JIT region */
            uintptr_t heap_data_base = (uintptr_t)heap_data;
            
            for (uint64_t i = 0; i < header.num_relocs; i++) {
                CosmoExtReloc *r = &relocs[i];
                /* Only process relocations that target writable sections */
                if (!IS_WRITABLE(r->target_offset)) continue;
                
                /* This relocation points into a writable section - update to heap */
                uintptr_t old_value = (uintptr_t)mapped + r->target_offset;
                uintptr_t new_value = heap_data_base + (r->target_offset - data_start);
                
                /* Update pointer in JIT region (code references to data) */
                if (!IS_WRITABLE(r->blob_offset)) {
                    if (r->size == 8) {
                        memcpy((char*)mapped + r->blob_offset, &new_value, 8);
                    } else if (r->size == 4) {
                        uint32_t val32 = (uint32_t)new_value;
                        memcpy((char*)mapped + r->blob_offset, &val32, 4);
                    }
                    if (verbose) {
                        fprintf(stderr, "[cosmoext]   Redirected reloc at 0x%llx: 0x%llx -> 0x%llx\n",
                                (unsigned long long)r->blob_offset,
                                (unsigned long long)old_value,
                                (unsigned long long)new_value);
                    }
                }
                
                /* Also update pointer in heap copy (data references to other data) */
                if (IS_WRITABLE(r->blob_offset)) {
                    size_t heap_offset = r->blob_offset - data_start;
                    if (r->size == 8) {
                        memcpy((char*)heap_data + heap_offset, &new_value, 8);
                    } else if (r->size == 4) {
                        uint32_t val32 = (uint32_t)new_value;
                        memcpy((char*)heap_data + heap_offset, &val32, 4);
                    }
                    if (verbose) {
                        fprintf(stderr, "[cosmoext]   Updated heap reloc at heap+0x%zx: -> 0x%llx\n",
                                heap_offset, (unsigned long long)new_value);
                    }
                }
            }
            
            #undef IS_WRITABLE
            #undef MAX_WRITABLE_SECTIONS
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
            fprintf(stderr, "[cosmoext] Switching JIT to executable (pthread_jit_write_protect_np(1))\n");
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
        unsigned char *init_bytes = (unsigned char*)mapped + header.init_offset;
        fprintf(stderr, "[cosmoext] DEBUG: Init function at %p, bytes:\n", 
                (void*)init_bytes);
        for (int row = 0; row < 2; row++) {
            fprintf(stderr, "[cosmoext]   %04llx:", 
                    (unsigned long long)(header.init_offset + row * 16));
            for (int col = 0; col < 16; col++) {
                fprintf(stderr, " %02x", init_bytes[row * 16 + col]);
            }
            fprintf(stderr, "\n");
        }
        
        fflush(stderr);
    }
    
    /* Call the init function */
    CosmoExtInitFunc init_func = (CosmoExtInitFunc)((char*)mapped + header.init_offset);
    
    if (verbose) {
        fprintf(stderr, "[cosmoext] About to call init at %p\n", (void*)init_func);
        fflush(stderr);
    }
    void *init_result = init_func();
    
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
    if (init_result == (void*)1) {
        /* Shim intercepted PyModuleDef_Init (multi-phase) */
        /* _cosmoext_get_captured_def offset from init is stored in header (v5+).
         * For older formats, fall back to architecture-specific hardcoded values.
         */
        size_t get_def_offset = header.get_def_offset;
        if (get_def_offset == 0) {
            /* Fallback for v3/v4 formats without get_def_offset */
#if defined(__aarch64__)
            get_def_offset = 0xE8;  /* ARM64: larger due to ADRP/ADD sequences */
#else
            get_def_offset = 0x98;  /* x86_64: smaller code */
#endif
        }
        GetCapturedDefFunc get_def = (GetCapturedDefFunc)((char*)init_func + get_def_offset);
        
        if (verbose) {
            fprintf(stderr, "[cosmoext] Calling get_def at %p (init+0x%zx)\n", (void*)get_def, get_def_offset);
            fflush(stderr);
        }
        
        PyModuleDef *def = get_def();
        
        if (verbose) {
            fprintf(stderr, "[cosmoext] get_def returned: %p\n", (void*)def);
            fflush(stderr);
        }
        
        if (!def) {
            PyErr_SetString(PyExc_RuntimeError, "Shim captured NULL def");
            munmap(mapped, map_size);
            return NULL;
        }
        
        PyObject *spec = PyObject_CallMethod(
            PyImport_ImportModule("importlib.machinery"),
            "ModuleSpec", "sO", def->m_name, Py_None
        );
        if (!spec) {
            munmap(mapped, map_size);
            return NULL;
        }
        
        PyObject *module = PyModule_FromDefAndSpec(def, spec);
        Py_DECREF(spec);
        
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
        return (PyObject*)init_result;
    }
    
    /* Assume it's a PyModuleDef* */
    PyModuleDef *def = (PyModuleDef*)init_result;
    
    PyObject *module;
    if (def->m_slots != NULL) {
        PyObject *spec = PyObject_CallMethod(
            PyImport_ImportModule("importlib.machinery"),
            "ModuleSpec", "sO", def->m_name, Py_None
        );
        if (!spec) {
            munmap(mapped, map_size);
            return NULL;
        }
        
        module = PyModule_FromDefAndSpec(def, spec);
        Py_DECREF(spec);
        
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
    }
    
    return module;

error:
    if (f) fclose(f);
    if (blob) PyMem_Free(blob);
    if (relocs) PyMem_Free(relocs);
    if (ext_syms) PyMem_Free(ext_syms);
    if (string_table) PyMem_Free(string_table);
    if (symtab) free_simple_symtab(symtab);
    if (mapped && mapped != MAP_FAILED) munmap(mapped, map_size);
    return NULL;
}

static PyMethodDef cosmoext_methods[] = {
    {"load", cosmoext_load, METH_VARARGS, "Load a .cosmoext file"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cosmoextmodule = {
    PyModuleDef_HEAD_INIT,
    "_cosmoext",
    "Native loader for .cosmoext extension blobs (v3/v4 format)",
    -1,
    cosmoext_methods
};

PyMODINIT_FUNC
PyInit__cosmoext(void)
{
    return PyModule_Create(&cosmoextmodule);
}
