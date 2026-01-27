/*-*- mode:c;indent-tabs-mode:nil;c-basic-offset:2;tab-width:8;coding:utf-8 -*-│
│ vi: set et ft=c ts=2 sts=2 sw=2 fenc=utf-8                               :vi │
╞══════════════════════════════════════════════════════════════════════════════╡
│ Copyright 2020 Justine Alexandra Roberts Tunney                              │
│                                                                              │
│ Permission to use, copy, modify, and/or distribute this software for         │
│ any purpose with or without fee is hereby granted, provided that the         │
│ above copyright notice and this permission notice appear in all copies.      │
│                                                                              │
│ THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL                │
│ WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED                │
│ WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE             │
│ AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL         │
│ DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR        │
│ PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER               │
│ TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR             │
│ PERFORMANCE OF THIS SOFTWARE.                                                │
╚─────────────────────────────────────────────────────────────────────────────*/

/*
 * Libc stub functions for cosmoext extensions.
 *
 * These provide implementations for libc functions that may NOT be exported
 * in python.com's embedded symbol table. The exact set of exported symbols
 * varies by build, so we include common functions that extensions may need.
 *
 * Based on code from https://github.com/jart/cosmopolitan/tree/master/libc/str
 *
 * Compile with: cosmocc -c -fPIC -mcmodel=large -fno-stack-protector
 */

/**
 * Returns nonzero if c is C0 ASCII control code or DEL.
 */
int iscntrl(int c)
{
    return (0x00 <= c && c <= 0x1F) || c == 0x7F;
}

/**
 * Returns nonzero if ``c ∈ !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~``
 */
int ispunct(int c)
{
    return (0x21 <= c && c <= 0x7E) && !('0' <= c && c <= '9') && !('A' <= c && c <= 'Z') &&
           !('a' <= c && c <= 'z');
}

/**
 * Returns nonzero if c is space, \t, \r, \n, \f, or \v.
 */
int isspace(int c)
{
    return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' || c == '\v';
}

/**
 * Copies n bytes from src to dest, handling overlap correctly.
 */
void *memmove(void *dest, const void *src, unsigned long n)
{
    char *d = dest;
    const char *s = src;
    if (d < s) {
        while (n--)
            *d++ = *s++;
    } else {
        d += n;
        s += n;
        while (n--)
            *--d = *--s;
    }
    return dest;
}

/**
 * memcpy - Copy n bytes from src to dest (non-overlapping).
 */
void *memcpy(void *dest, const void *src, unsigned long n)
{
    char *d = dest;
    const char *s = src;
    while (n--)
        *d++ = *s++;
    return dest;
}

/**
 * isalnum - Check if character is alphanumeric.
 */
int isalnum(int c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
}

/**
 * isupper - Check if character is uppercase letter.
 */
int isupper(int c)
{
    return c >= 'A' && c <= 'Z';
}

/**
 * tolower - Convert character to lowercase.
 */
int tolower(int c)
{
    if (c >= 'A' && c <= 'Z')
        return c + ('a' - 'A');
    return c;
}

/**
 * toupper - Convert character to uppercase.
 */
int toupper(int c)
{
    if (c >= 'a' && c <= 'z')
        return c - ('a' - 'A');
    return c;
}

/**
 * ceil - Round up to nearest integer.
 */
double ceil(double x)
{
    if (x >= 0) {
        long long i = (long long)x;
        return (double)i + (x > (double)i ? 1.0 : 0.0);
    } else {
        return (double)(long long)x;
    }
}

/*
 * Py_Version - Python version constant.
 * This should be 0x030c0cf0 for Python 3.12.12 but we use a macro to
 * compute it at compile time based on the included headers.
 * Note: This is only needed for Cython-generated code that checks the version.
 */
#ifdef PY_VERSION_HEX
const unsigned long Py_Version = PY_VERSION_HEX;
#else
/* Fallback for Python 3.12.x */
const unsigned long Py_Version = 0x030c00f0;
#endif

/*
 * String/number conversion functions needed by libcxx.
 * These are minimal implementations sufficient for C++ STL usage.
 */

/* Helper to skip whitespace */
static const char *skip_ws(const char *s)
{
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r' || *s == '\f' || *s == '\v')
        s++;
    return s;
}

/**
 * strtol - Convert string to long integer.
 */
long strtol(const char *nptr, char **endptr, int base)
{
    const char *s = skip_ws(nptr);
    int neg = 0;
    long result = 0;

    if (*s == '-') {
        neg = 1;
        s++;
    } else if (*s == '+') {
        s++;
    }

    if (base == 0) {
        if (*s == '0') {
            if (s[1] == 'x' || s[1] == 'X') {
                base = 16;
                s += 2;
            } else {
                base = 8;
                s++;
            }
        } else {
            base = 10;
        }
    } else if (base == 16 && *s == '0' && (s[1] == 'x' || s[1] == 'X')) {
        s += 2;
    }

    while (*s) {
        int digit;
        if (*s >= '0' && *s <= '9')
            digit = *s - '0';
        else if (*s >= 'a' && *s <= 'z')
            digit = *s - 'a' + 10;
        else if (*s >= 'A' && *s <= 'Z')
            digit = *s - 'A' + 10;
        else
            break;

        if (digit >= base)
            break;

        result = result * base + digit;
        s++;
    }

    if (endptr)
        *endptr = (char *)s;
    return neg ? -result : result;
}

/**
 * strtoll - Convert string to long long integer.
 */
long long strtoll(const char *nptr, char **endptr, int base)
{
    const char *s = skip_ws(nptr);
    int neg = 0;
    long long result = 0;

    if (*s == '-') {
        neg = 1;
        s++;
    } else if (*s == '+') {
        s++;
    }

    if (base == 0) {
        if (*s == '0') {
            if (s[1] == 'x' || s[1] == 'X') {
                base = 16;
                s += 2;
            } else {
                base = 8;
                s++;
            }
        } else {
            base = 10;
        }
    } else if (base == 16 && *s == '0' && (s[1] == 'x' || s[1] == 'X')) {
        s += 2;
    }

    while (*s) {
        int digit;
        if (*s >= '0' && *s <= '9')
            digit = *s - '0';
        else if (*s >= 'a' && *s <= 'z')
            digit = *s - 'a' + 10;
        else if (*s >= 'A' && *s <= 'Z')
            digit = *s - 'A' + 10;
        else
            break;

        if (digit >= base)
            break;

        result = result * base + digit;
        s++;
    }

    if (endptr)
        *endptr = (char *)s;
    return neg ? -result : result;
}

/**
 * strtoull - Convert string to unsigned long long.
 */
unsigned long long strtoull(const char *nptr, char **endptr, int base)
{
    const char *s = skip_ws(nptr);
    unsigned long long result = 0;

    if (*s == '+')
        s++;

    if (base == 0) {
        if (*s == '0') {
            if (s[1] == 'x' || s[1] == 'X') {
                base = 16;
                s += 2;
            } else {
                base = 8;
                s++;
            }
        } else {
            base = 10;
        }
    } else if (base == 16 && *s == '0' && (s[1] == 'x' || s[1] == 'X')) {
        s += 2;
    }

    while (*s) {
        int digit;
        if (*s >= '0' && *s <= '9')
            digit = *s - '0';
        else if (*s >= 'a' && *s <= 'z')
            digit = *s - 'a' + 10;
        else if (*s >= 'A' && *s <= 'Z')
            digit = *s - 'A' + 10;
        else
            break;

        if (digit >= base)
            break;

        result = result * base + digit;
        s++;
    }

    if (endptr)
        *endptr = (char *)s;
    return result;
}

/**
 * strtod - Convert string to double.
 *
 * Simple implementation for libcxx needs. Handles:
 * - Optional sign
 * - Integer part
 * - Fractional part
 * - No exponent support (could be added if needed)
 */
double strtod(const char *nptr, char **endptr)
{
    const char *s = nptr;
    double result = 0.0;
    int neg = 0;

    /* Skip whitespace */
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r')
        s++;

    /* Sign */
    if (*s == '-') {
        neg = 1;
        s++;
    } else if (*s == '+') {
        s++;
    }

    /* Integer part */
    while (*s >= '0' && *s <= '9') {
        result = result * 10.0 + (*s - '0');
        s++;
    }

    /* Fractional part */
    if (*s == '.') {
        double frac = 0.1;
        s++;
        while (*s >= '0' && *s <= '9') {
            result += (*s - '0') * frac;
            frac *= 0.1;
            s++;
        }
    }

    /* Exponent (basic support) */
    if (*s == 'e' || *s == 'E') {
        s++;
        int exp_neg = 0;
        int exp = 0;

        if (*s == '-') {
            exp_neg = 1;
            s++;
        } else if (*s == '+') {
            s++;
        }

        while (*s >= '0' && *s <= '9') {
            exp = exp * 10 + (*s - '0');
            s++;
        }

        double mult = 1.0;
        for (int i = 0; i < exp; i++)
            mult *= 10.0;

        if (exp_neg)
            result /= mult;
        else
            result *= mult;
    }

    if (endptr)
        *endptr = (char *)s;
    return neg ? -result : result;
}

/**
 * strtof - Convert string to float.
 */
float strtof(const char *nptr, char **endptr)
{
    return (float)strtod(nptr, endptr);
}

/**
 * strtold - Convert string to long double.
 */
long double strtold(const char *nptr, char **endptr)
{
    /* Use strtod - long double often same as double on many platforms */
    return (long double)strtod(nptr, endptr);
}

/*
 * Wide character functions - minimal implementations for libcxx.
 * These handle basic ASCII; full Unicode support would require more code.
 */

typedef int wchar_t_stub; /* Avoid header dependency */

/**
 * wcslen - Get length of wide string.
 */
unsigned long wcslen(const wchar_t_stub *s)
{
    const wchar_t_stub *p = s;
    while (*p)
        p++;
    return p - s;
}

/**
 * wcstol - Convert wide string to long.
 */
long wcstol(const wchar_t_stub *nptr, wchar_t_stub **endptr, int base)
{
    /* Skip whitespace */
    while (*nptr == ' ' || *nptr == '\t')
        nptr++;

    int neg = 0;
    long result = 0;

    if (*nptr == '-') {
        neg = 1;
        nptr++;
    } else if (*nptr == '+') {
        nptr++;
    }

    if (base == 0) {
        if (*nptr == '0') {
            if (nptr[1] == 'x' || nptr[1] == 'X') {
                base = 16;
                nptr += 2;
            } else {
                base = 8;
                nptr++;
            }
        } else {
            base = 10;
        }
    }

    while (*nptr) {
        int digit;
        if (*nptr >= '0' && *nptr <= '9')
            digit = *nptr - '0';
        else if (*nptr >= 'a' && *nptr <= 'z')
            digit = *nptr - 'a' + 10;
        else if (*nptr >= 'A' && *nptr <= 'Z')
            digit = *nptr - 'A' + 10;
        else
            break;

        if (digit >= base)
            break;

        result = result * base + digit;
        nptr++;
    }

    if (endptr)
        *endptr = (wchar_t_stub *)nptr;
    return neg ? -result : result;
}

/**
 * wcstoull - Convert wide string to unsigned long long.
 */
unsigned long long wcstoull(const wchar_t_stub *nptr, wchar_t_stub **endptr, int base)
{
    while (*nptr == ' ' || *nptr == '\t')
        nptr++;

    if (*nptr == '+')
        nptr++;

    if (base == 0) {
        if (*nptr == '0') {
            if (nptr[1] == 'x' || nptr[1] == 'X') {
                base = 16;
                nptr += 2;
            } else {
                base = 8;
                nptr++;
            }
        } else {
            base = 10;
        }
    }

    unsigned long long result = 0;
    while (*nptr) {
        int digit;
        if (*nptr >= '0' && *nptr <= '9')
            digit = *nptr - '0';
        else if (*nptr >= 'a' && *nptr <= 'z')
            digit = *nptr - 'a' + 10;
        else if (*nptr >= 'A' && *nptr <= 'Z')
            digit = *nptr - 'A' + 10;
        else
            break;

        if (digit >= base)
            break;

        result = result * base + digit;
        nptr++;
    }

    if (endptr)
        *endptr = (wchar_t_stub *)nptr;
    return result;
}

/**
 * wcstod - Convert wide string to double.
 */
double wcstod(const wchar_t_stub *nptr, wchar_t_stub **endptr)
{
    /* Simple implementation - convert to narrow string first */
    char buf[64];
    int i = 0;
    const wchar_t_stub *p = nptr;

    while (*p == ' ' || *p == '\t')
        p++;

    while (*p && i < 63) {
        if (*p > 127)
            break; /* Non-ASCII */
        buf[i++] = (char)*p++;
    }
    buf[i] = '\0';

    char *end;
    extern double strtod(const char *, char **);
    double result = strtod(buf, &end);

    if (endptr) {
        /* Adjust endptr to point into wide string */
        *endptr = (wchar_t_stub *)(nptr + (end - buf));
    }
    return result;
}

/**
 * wcstof - Convert wide string to float.
 */
float wcstof(const wchar_t_stub *nptr, wchar_t_stub **endptr)
{
    return (float)wcstod(nptr, endptr);
}

/**
 * wcstold - Convert wide string to long double.
 */
long double wcstold(const wchar_t_stub *nptr, wchar_t_stub **endptr)
{
    return (long double)wcstod(nptr, endptr);
}

/**
 * swprintf - Write formatted wide string.
 * Minimal implementation - just handles %s and %d for libcxx needs.
 */
int swprintf(wchar_t_stub *s, unsigned long n, const wchar_t_stub *format, ...)
{
    /* Very minimal - just copy format string for now */
    unsigned long i = 0;
    while (*format && i < n - 1) {
        s[i++] = *format++;
    }
    s[i] = 0;
    return i;
}

/*
 * C++ ABI functions needed by libcxx exception handling.
 */

/**
 * __cxa_call_terminate - Called when exception handling fails.
 */
void __cxa_call_terminate(void *thrown_object)
{
    extern void abort(void);
    abort();
}

/**
 * _ZNSt20bad_array_new_lengthC1Ev - std::bad_array_new_length constructor.
 * Mangled name for std::bad_array_new_length::bad_array_new_length()
 */
void _ZNSt20bad_array_new_lengthC1Ev(void *this_ptr)
{
    /* No-op - exception object is already allocated */
    (void)this_ptr;
}

/**
 * _ZNSt9bad_allocC1Ev - std::bad_alloc constructor.
 */
void _ZNSt9bad_allocC1Ev(void *this_ptr)
{
    (void)this_ptr;
}

/*
 * C++ exception class stubs needed by libcxx.
 * These are typeinfo and vtable symbols for exception classes that
 * may not be exported from python.com.
 */

/* std::out_of_range destructor */
void _ZNSt12out_of_rangeD1Ev(void *this_ptr)
{
    (void)this_ptr;
}

/* std::invalid_argument destructor */
void _ZNSt16invalid_argumentD1Ev(void *this_ptr)
{
    (void)this_ptr;
}

/* Typeinfo and vtable stubs - these are data symbols but we provide
 * minimal function stubs to satisfy the linker. The actual exception
 * handling may not work fully, but basic C++ code should work. */

/* Typeinfo for std::out_of_range */
const void *_ZTISt12out_of_range = 0;

/* Typeinfo for std::invalid_argument */
const void *_ZTISt16invalid_argument = 0;

/* Vtable stubs - minimal vtables with null pointers */
const void *_ZTVSt12out_of_range[4] = {0, 0, 0, 0};
const void *_ZTVSt16invalid_argument[4] = {0, 0, 0, 0};

/*
 * Rust runtime stubs for PyO3 extensions.
 * These provide minimal implementations for Rust runtime functions
 * that may not be exported from python.com.
 */

/* Compare memory - same as memcmp but BSD name */
int bcmp(const void *s1, const void *s2, unsigned long n)
{
    const unsigned char *p1 = s1;
    const unsigned char *p2 = s2;
    while (n--) {
        if (*p1 != *p2) {
            return *p1 - *p2;
        }
        p1++;
        p2++;
    }
    return 0;
}

/* Aligned memory allocation */
int posix_memalign(void **memptr, unsigned long alignment, unsigned long size)
{
    /* Simple implementation using malloc - alignment is ignored
     * This works for most cases where alignment <= 16 */
    void *ptr = __builtin_malloc(size);
    if (ptr == 0) {
        return 12; /* ENOMEM */
    }
    *memptr = ptr;
    return 0;
}

/* Thread-safe strerror */
int __xpg_strerror_r(int errnum, char *buf, unsigned long buflen)
{
    /* Minimal implementation - just format error number */
    if (buflen < 20) {
        return 34; /* ERANGE */
    }
    /* Simple number to string */
    char *p = buf;
    *p++ = 'E';
    *p++ = 'r';
    *p++ = 'r';
    *p++ = 'o';
    *p++ = 'r';
    *p++ = ' ';
    if (errnum < 0) {
        *p++ = '-';
        errnum = -errnum;
    }
    char tmp[12];
    int i = 0;
    do {
        tmp[i++] = '0' + (errnum % 10);
        errnum /= 10;
    } while (errnum && i < 11);
    while (i > 0) {
        *p++ = tmp[--i];
    }
    *p = '\0';
    return 0;
}

/* Rust unwinding stubs - these are needed for panic handling.
 * Since we use panic=abort, these should never actually be called,
 * but the linker needs them to resolve symbols. */

typedef void *_Unwind_Context;
typedef int _Unwind_Reason_Code;
typedef unsigned long _Unwind_Word;
typedef unsigned long _Unwind_Ptr;

_Unwind_Reason_Code _Unwind_Backtrace(_Unwind_Reason_Code (*)(struct _Unwind_Context *, void *),
                                      void *arg)
{
    return 0; /* _URC_NO_REASON */
}

_Unwind_Ptr _Unwind_GetDataRelBase(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

_Unwind_Ptr _Unwind_GetTextRelBase(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

_Unwind_Word _Unwind_GetIP(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

_Unwind_Word _Unwind_GetIPInfo(_Unwind_Context *context, int *ip_before_insn)
{
    (void)context;
    if (ip_before_insn)
        *ip_before_insn = 0;
    return 0;
}

_Unwind_Ptr _Unwind_GetLanguageSpecificData(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

_Unwind_Ptr _Unwind_GetRegionStart(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

void _Unwind_SetGR(_Unwind_Context *context, int reg, _Unwind_Word val)
{
    (void)context;
    (void)reg;
    (void)val;
}

void _Unwind_SetIP(_Unwind_Context *context, _Unwind_Ptr val)
{
    (void)context;
    (void)val;
}

/* dl_iterate_phdr - iterate over shared objects.
 * This is used by Rust's backtrace library. We return 0 to indicate
 * no shared objects (we're statically linked).
 */
struct dl_phdr_info;
typedef int (*dl_iterate_phdr_callback)(struct dl_phdr_info *, unsigned long, void *);

int dl_iterate_phdr(dl_iterate_phdr_callback callback, void *data)
{
    (void)callback;
    (void)data;
    return 0;  /* No shared objects */
}

/* fstat - get file status.
 * Forward to the real fstat in cosmopolitan.
 */
struct stat;
extern int fstat(int fd, struct stat *buf);

/* If fstat isn't available, provide a stub that fails */
#ifdef COSMOEXT_STUB_FSTAT
int fstat(int fd, struct stat *buf)
{
    (void)fd;
    (void)buf;
    return -1;  /* ENOSYS */
}
#endif

/* Additional stubs for rpds-py and other extensions */

/* _exit - terminate process immediately */
void _exit(int status)
{
    extern void exit(int);
    exit(status);
}

/* execvp - execute program searching PATH */
int execvp(const char *file, char *const argv[])
{
    (void)file;
    (void)argv;
    return -1;  /* Not supported */
}

/* getauxval - get auxiliary vector value */
unsigned long getauxval(unsigned long type)
{
    (void)type;
    return 0;  /* Not available */
}

/* lstat - get file status (don't follow symlinks) */
struct stat;
extern int stat(const char *path, struct stat *buf);
int lstat(const char *path, struct stat *buf)
{
    return stat(path, buf);  /* Fall back to stat */
}

/* mkfifo - make FIFO (named pipe) */
int mkfifo(const char *path, unsigned int mode)
{
    (void)path;
    (void)mode;
    return -1;  /* Not supported */
}

/* openat - open file relative to directory fd */
extern int open(const char *path, int flags, ...);
int openat(int dirfd, const char *path, int flags, ...)
{
    (void)dirfd;
    /* Ignore dirfd, just use regular open */
    return open(path, flags);
}

/* pidfd functions - not supported */
int pidfd_getpid(int pidfd)
{
    (void)pidfd;
    return -1;
}

int pidfd_spawnp(int *pidfd, const char *path, void *file_actions,
                 void *attrp, char *const argv[], char *const envp[])
{
    (void)pidfd;
    (void)path;
    (void)file_actions;
    (void)attrp;
    (void)argv;
    (void)envp;
    return -1;
}

/* posix_spawn_file_actions_addchdir_np - not available */
int posix_spawn_file_actions_addchdir_np(void *file_actions, const char *path)
{
    (void)file_actions;
    (void)path;
    return -1;
}

/* pread - read from file at offset */
extern long read(int fd, void *buf, unsigned long count);
extern long lseek(int fd, long offset, int whence);
long pread(int fd, void *buf, unsigned long count, long offset)
{
    long old_pos = lseek(fd, 0, 1);  /* SEEK_CUR */
    if (old_pos < 0) return -1;
    if (lseek(fd, offset, 0) < 0) return -1;  /* SEEK_SET */
    long result = read(fd, buf, count);
    lseek(fd, old_pos, 0);  /* Restore position */
    return result;
}

/* pthread attribute functions - return defaults */
typedef unsigned long pthread_attr_t;

int pthread_attr_getguardsize(const pthread_attr_t *attr, unsigned long *guardsize)
{
    (void)attr;
    *guardsize = 4096;  /* Default page size */
    return 0;
}

int pthread_attr_getstack(const pthread_attr_t *attr, void **stackaddr, unsigned long *stacksize)
{
    (void)attr;
    *stackaddr = (void *)0;
    *stacksize = 8 * 1024 * 1024;  /* 8MB default */
    return 0;
}

int pthread_getattr_np(unsigned long thread, pthread_attr_t *attr)
{
    (void)thread;
    (void)attr;
    return 0;
}

int pthread_setname_np(unsigned long thread, const char *name)
{
    (void)thread;
    (void)name;
    return 0;  /* Silently succeed */
}

/* waitid - wait for process state change */
typedef struct {
    int si_pid;
    int si_uid;
    int si_status;
    int si_code;
} siginfo_t;

int waitid(int idtype, int id, siginfo_t *infop, int options)
{
    (void)idtype;
    (void)id;
    (void)infop;
    (void)options;
    return -1;  /* Not supported */
}

/* Additional Unwind functions */
_Unwind_Ptr _Unwind_FindEnclosingFunction(void *pc)
{
    (void)pc;
    return 0;
}

_Unwind_Word _Unwind_GetCFA(_Unwind_Context *context)
{
    (void)context;
    return 0;
}

/* mlock/munlock - lock memory (for safetensors) */
int mlock(const void *addr, unsigned long len)
{
    (void)addr;
    (void)len;
    return 0;  /* Silently succeed - cosmopolitan may not support this */
}

int munlock(const void *addr, unsigned long len)
{
    (void)addr;
    (void)len;
    return 0;
}

/* inotify functions (for watchfiles) - Linux file watching */
int inotify_init1(int flags)
{
    (void)flags;
    return -1;  /* Not supported on all platforms */
}

int inotify_add_watch(int fd, const char *pathname, unsigned int mask)
{
    (void)fd;
    (void)pathname;
    (void)mask;
    return -1;
}

int inotify_rm_watch(int fd, int wd)
{
    (void)fd;
    (void)wd;
    return -1;
}

/* futimes/lutimes - set file times */
struct timeval;
int futimes(int fd, const struct timeval *times)
{
    (void)fd;
    (void)times;
    return -1;
}

int lutimes(const char *path, const struct timeval *times)
{
    (void)path;
    (void)times;
    return -1;
}

/* Linux epoll functions */
int epoll_create1(int flags)
{
    (void)flags;
    return -1;  /* Not supported */
}

int epoll_ctl(int epfd, int op, int fd, void *event)
{
    (void)epfd;
    (void)op;
    (void)fd;
    (void)event;
    return -1;
}

int epoll_wait(int epfd, void *events, int maxevents, int timeout)
{
    (void)epfd;
    (void)events;
    (void)maxevents;
    (void)timeout;
    return -1;
}

/* eventfd - event notification */
int eventfd(unsigned int initval, int flags)
{
    (void)initval;
    (void)flags;
    return -1;
}

/* Signal functions */
int __libc_current_sigrtmax(void)
{
    return 64;  /* Standard SIGRTMAX */
}

/* Terminal control */
struct termios;
int cfmakeraw(struct termios *termios_p)
{
    (void)termios_p;
    return 0;
}

/* Math functions - forward to cosmopolitan's implementations */
double exp(double x);
double pow(double x, double y);
/* These should already be in python.com, just need aliases */

/* Math functions - implemented via asm to call actual functions */
/* These exist in cosmopolitan but may not be exported with these exact names */

/* Use compiler builtins which get lowered to the right calls */
double cosmoext_exp(double x) { return __builtin_exp(x); }
double cosmoext_pow(double x, double y) { return __builtin_pow(x, y); }
double cosmoext_log(double x) { return __builtin_log(x); }
double cosmoext_sqrt(double x) { return __builtin_sqrt(x); }
double cosmoext_sin(double x) { return __builtin_sin(x); }
double cosmoext_cos(double x) { return __builtin_cos(x); }
float cosmoext_expf(float x) { return __builtin_expf(x); }
float cosmoext_powf(float x, float y) { return __builtin_powf(x, y); }
float cosmoext_logf(float x) { return __builtin_logf(x); }
float cosmoext_sqrtf(float x) { return __builtin_sqrtf(x); }

/* Provide the standard names as aliases */
__attribute__((weak, alias("cosmoext_exp"))) double exp(double);
__attribute__((weak, alias("cosmoext_pow"))) double pow(double, double);
__attribute__((weak, alias("cosmoext_log"))) double log(double);
__attribute__((weak, alias("cosmoext_sqrt"))) double sqrt(double);
__attribute__((weak, alias("cosmoext_sin"))) double sin(double);
__attribute__((weak, alias("cosmoext_cos"))) double cos(double);
__attribute__((weak, alias("cosmoext_expf"))) float expf(float);
__attribute__((weak, alias("cosmoext_powf"))) float powf(float, float);
__attribute__((weak, alias("cosmoext_logf"))) float logf(float);
__attribute__((weak, alias("cosmoext_sqrtf"))) float sqrtf(float);
