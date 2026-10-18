#!/usr/bin/env python3
"""Exercise the generated charger C code with a fake register bus (Linux host).

Usage: python3 test_charger.py /path/to/generated/bq2560x-charger.c
The factory binary is not required or redistributed; reference arithmetic is
transcribed from its A6 setter/getter instructions. No real device is accessed.
"""
import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(sys.argv.pop(1)).read_text()


def function(name):
    match = re.search(r'static (?:int|u32)\s+' + name + r'\([^;{}]*\)\s*\{', SOURCE)
    if not match:
        raise AssertionError('Missing function ' + name)
    index = match.end()
    depth = 1
    while depth:
        depth += (SOURCE[index] == '{') - (SOURCE[index] == '}')
        index += 1
    return SOURCE[match.start():index]


class Charger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='t551m-charger-test-')
        root = Path(cls.tmp.name)
        prelude = r'''
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define min(a,b) ((a)<(b)?(a):(b))
#define clamp_val(v,a,b) ((v)<(a)?(a):min(v,b))
#define GENMASK(h,l) (((1U<<((h)-(l)+1))-1)<<(l))
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define dev_info(...) ((void)0)
#define dev_err(...) ((void)0)
struct bq2560x_charger_info { int input_limit_cur_lock; u32 last_limit_cur, actual_limit_cur; };
static struct bq2560x_charger_info info;
static u8 registers[12];
static int failure;
int reg_get(int r) { return registers[r]; }
void reg_set(int r, int v) { registers[r] = v; }
void io_fail(int v) { failure = v; }
static int bq2560x_read(struct bq2560x_charger_info *i, u8 r, u8 *v) {
    if (failure) return -EIO;
    *v = registers[r]; return 0;
}
static int bq2560x_update_bits(struct bq2560x_charger_info *i, u8 r, u8 mask, u8 v) {
    if (failure) return -EIO;
    registers[r] = (registers[r] & ~mask) | (v & mask); return 0;
}
'''
        defines = '\n'.join(line for line in SOURCE.splitlines()
                            if re.match(r'#define\s+BQ2560X_(REG_[024]|REG_ICHG_MASK|REG_TERMINAL_VOLTAGE_MASK|LIMIT_CURRENT_MAX|LIMIT_CURRENT_OFFSET|REG_IINLIM_BASE|REG_LIMIT_CURRENT_MASK)\s', line))
        names = ['get_limit_current', 'set_limit_current', 'set_current', 'get_current', 'set_termina_vol']
        code = prelude + defines + '\n' + '\n'.join(function('bq2560x_charger_' + n) for n in names)
        code += r'''
int charge_set(u32 v) { return bq2560x_charger_set_current(&info, v); }
int charge_get(void) { u32 v; int r = bq2560x_charger_get_current(&info, &v); return r ? r : (int)v; }
int input_set(u32 v) { return bq2560x_charger_set_limit_current(&info, v, false); }
int input_get(void) { u32 v; int r = bq2560x_charger_get_limit_current(&info, &v); return r ? r : (int)v; }
int input_refresh(void) { return bq2560x_charger_set_limit_current(&info, 0, true); }
int voltage_set(u32 v) { return bq2560x_charger_set_termina_vol(&info, v); }
'''
        (root / 'test.c').write_text(code)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Werror', '-Wno-unused-function',
                        str(root / 'test.c'), '-o', str(root / 'test.so')], check=True)
        cls.lib = ctypes.CDLL(str(root / 'test.so'))
        for name in ('charge_set', 'input_set', 'voltage_set'):
            getattr(cls.lib, name).argtypes = [ctypes.c_uint32]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.lib.io_fail(0)

    def test_input_range_does_not_wrap_and_preserves_control_bits(self):
        for requested in [*range(0, 5000001, 1000), 0xffffffff]:
            self.lib.reg_set(0, 0xe0)
            self.assertEqual(self.lib.input_set(requested), 0)
            expected = max(100000, min(requested, 3200000)) // 100000 * 100000
            self.assertEqual(self.lib.input_get(), expected)
            self.assertEqual(self.lib.reg_get(0) & 0xe0, 0xe0)

    def test_sdp_dcp_and_hardware_ceiling(self):
        for requested, code in [(500000, 4), (1500000, 14), (2000000, 19),
                                (3000000, 29), (3200000, 31), (4000000, 31)]:
            self.lib.input_set(requested)
            self.assertEqual(self.lib.reg_get(0) & 31, code)

    def test_watchdog_restores_last_input_setting(self):
        self.lib.input_set(2000000)
        self.lib.reg_set(0, 4)
        self.assertEqual(self.lib.input_refresh(), 0)
        self.assertEqual(self.lib.input_get(), 2000000)

    def test_charge_encoder_matches_factory_a6_instructions(self):
        for requested in [*range(0, 5000001, 1000), 0xffffffff]:
            ma = min((requested * 0x10624dd3) >> 38, 3047)
            if ma <= 1170:
                code = ((ma & 0xffff) * 0x2d83) >> 20
            else:
                x = ma - 805
                q = ((x & 0xffff) * 0x1f71) >> 16
                code = ((q + (((x - q) & 0xfffe) >> 1)) >> 5) + 14
            self.lib.reg_set(2, 0xc0)
            self.assertEqual(self.lib.charge_set(requested), 0)
            self.assertEqual(self.lib.reg_get(2), 0xc0 | code)

    def test_charge_decoder_covers_upper_range(self):
        for code, expected in [(0, 0), (5, 450000), (13, 1170000), (14, 805000),
                                (26, 1495000), (34, 1955000), (52, 2990000), (53, 3047000)]:
            self.lib.reg_set(2, code | 0xc0)
            self.assertEqual(self.lib.charge_get(), expected)

    def test_factory_voltage_and_thermal_reduction(self):
        for requested, expected in [(4400, 4400), (4100, 4080), (4500, 4400)]:
            self.lib.reg_set(4, 7)
            self.lib.voltage_set(requested)
            self.assertEqual((self.lib.reg_get(4) >> 3) * 32 + 3856, expected)
            self.assertEqual(self.lib.reg_get(4) & 7, 7)

    def test_bus_errors_propagate(self):
        self.lib.io_fail(1)
        for name in ('charge_get', 'input_get', 'input_refresh'):
            self.assertEqual(getattr(self.lib, name)(), -5)
        for name in ('charge_set', 'input_set', 'voltage_set'):
            self.assertEqual(getattr(self.lib, name)(2000000), -5)


if __name__ == '__main__':
    unittest.main()
