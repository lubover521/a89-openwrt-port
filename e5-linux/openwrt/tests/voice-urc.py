#!/usr/bin/env python3
"""Exercise the production vendor URC regex with GLib; no modem or call I/O."""
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

source = (Path(sys.argv[1]) / 'plugins/unisoc/mm-broadband-modem-unisoc.c').read_text()
expression = re.search(r'vendor = g_regex_new \(("(?:[^"\\]|\\.)*")', source)[1]
fixture = r'''
#include <glib.h>
#include <string.h>
static void check(GRegex *r, const char *input, const char *expected) {
    GError *error = NULL;
    gchar *out = g_regex_replace_literal(r, input, -1, 0, "", 0, &error);
    g_assert_no_error(error);
    g_assert_cmpstr(out, ==, expected);
    g_free(out);
}
int main(void) {
    GRegex *r = g_regex_new(EXPRESSION, G_REGEX_RAW | G_REGEX_OPTIMIZE, 0, NULL);
    /* Captured E5 failure: ATD succeeded but an IMS PDN report polluted its reply. */
    check(r, "\r\n+SPIMSPDPINFO: 17,0,1,0\r\n\r\nOK\r\n", "\r\nOK\r\n");
    check(r, "\r\n+CDU: 1\r\n\r\n+SPIMSPDPINFO: 17,0,1,0\r\n\r\nOK\r\n", "\r\nOK\r\n");
    check(r, "\r\n+SPIMSPDPINFO: 17,0,1,0\r\n\r\nBUSY\r\n", "\r\nBUSY\r\n");
    check(r, "\r\n+SPIMSPDPINFO: 17,0,1,0\r\n\r\nNO CARRIER\r\n", "\r\nNO CARRIER\r\n");
    check(r, "\r\n+SPIMSPDPINFO: 17,0,1,0\r\n\r\n+CME ERROR: 30\r\n", "\r\n+CME ERROR: 30\r\n");
    check(r, "\r\n+CLCC: 1,0,2,0,0,\"10010\",129\r\n\r\nOK\r\n", "\r\n+CLCC: 1,0,2,0,0,\"10010\",129\r\n\r\nOK\r\n");
    check(r, "\r\n+CPIN: READY\r\n\r\nOK\r\n", "\r\n+CPIN: READY\r\n\r\nOK\r\n");
    /* No partial-line match: a split serial report must await its terminator. */
    check(r, "\r\n+SPIMSPDPINFO: 17,0", "\r\n+SPIMSPDPINFO: 17,0");
    check(r, "\r\n+UNKNOWN: 1\r\n", "\r\n+UNKNOWN: 1\r\n");
    g_regex_unref(r);
    return 0;
}
'''.replace('EXPRESSION', expression)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root/'test.c').write_text(fixture)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'glib-2.0'], text=True))
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(root/'test.c'), '-o', str(root/'test'), *flags], check=True)
    subprocess.run([str(root/'test')], check=True)
print('PASS: IMS dial report removed; errors, call lists and partial/unknown replies preserved (9 cases)')
