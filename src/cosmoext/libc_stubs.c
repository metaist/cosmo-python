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
 * Cosmopolitan libc ctype functions for cosmoext extensions.
 *
 * These are copied from https://github.com/jart/cosmopolitan/tree/master/libc/str
 * because the pre-built libcosmo.a wasn't compiled with -mcmodel=large,
 * which is required for position-independent extension loading.
 *
 * Compile with: cosmocc -c -fPIC -mcmodel=large -fno-stack-protector
 */

/**
 * Returns nonzero if c is C0 ASCII control code or DEL.
 */
int iscntrl(int c) {
  return (0x00 <= c && c <= 0x1F) || c == 0x7F;
}

/**
 * Returns nonzero if ``c ∈ !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~``
 */
int ispunct(int c) {
  return (0x21 <= c && c <= 0x7E) && !('0' <= c && c <= '9') &&
         !('A' <= c && c <= 'Z') && !('a' <= c && c <= 'z');
}

/**
 * Returns nonzero if c is space, \t, \r, \n, \f, or \v.
 * @see isblank()
 */
int isspace(int c) {
  return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f' ||
         c == '\v';
}

/**
 * Copies n bytes from src to dest, handling overlap correctly.
 */
void *memmove(void *dest, const void *src, unsigned long n) {
  char *d = dest;
  const char *s = src;
  if (d < s) {
    while (n--) *d++ = *s++;
  } else {
    d += n;
    s += n;
    while (n--) *--d = *--s;
  }
  return dest;
}
