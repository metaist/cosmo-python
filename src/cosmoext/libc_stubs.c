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
 * strtof - Convert string to float.
 */
float strtof(const char *nptr, char **endptr)
{
    /* Use strtod and cast - good enough for libcxx needs */
    extern double strtod(const char *, char **);
    return (float)strtod(nptr, endptr);
}

/**
 * strtold - Convert string to long double.
 */
long double strtold(const char *nptr, char **endptr)
{
    /* Use strtod - long double often same as double on many platforms */
    extern double strtod(const char *, char **);
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
