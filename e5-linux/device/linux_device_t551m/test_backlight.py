#!/usr/bin/env python3
"""Compile the actual backlight update against a GPIO pulse-counter model.

Run on Linux with a C compiler. Covers every lit-to-lit transition, blanking,
initialization and rejected levels without needing a connected device.
"""
from pathlib import Path
import subprocess
import tempfile

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint16_t u16;
struct gpio_desc { int unused; };
struct sprd_backlight { struct gpio_desc *step_gpio; int step_level; };
struct backlight_device { struct sprd_backlight *bl; u16 level; bool blank; };
static int line, counter, edges, sleeps, locked;
static unsigned int low_us, longest_low_us, elapsed_us;
static struct sprd_backlight *bl_get_data(struct backlight_device *b) { return b->bl; }
static bool backlight_is_blank(struct backlight_device *b) { return b->blank; }
static void sprd_backlight_normalize_map(struct backlight_device *b, u16 *v) { *v = b->level; }
static void gpiod_set_value(struct gpio_desc *g, int value)
{
    (void)g;
    if (!line && value) {
        assert(locked);
        counter++;
        if (counter > 16) counter = 1;
        edges++;
    }
    if (line && !value) low_us = 0;
    line = value;
}
static void delay(unsigned int us)
{
    elapsed_us += us;
    if (!line) {
        low_us += us;
        if (low_us > longest_low_us) longest_low_us = low_us;
        if (low_us >= 50000) counter = 0;
    }
}
static void udelay(unsigned int us) { assert(locked); delay(us); }
static void msleep(unsigned int ms) { assert(!locked); sleeps++; delay(ms * 1000); }
#define local_irq_save(flags) do { (flags) = 0; assert(!locked); locked = 1; } while (0)
#define local_irq_restore(flags) do { (void)(flags); assert(locked); locked = 0; } while (0)
#include "t551m-backlight.h"
static void stats(void) { edges = sleeps = 0; low_us = longest_low_us = elapsed_us = 0; }
int main(void)
{
    struct gpio_desc gpio;
    struct sprd_backlight bl = { &gpio, -1 };
    struct backlight_device bd = { &bl, 1, false };
    for (int from = 1; from <= 16; from++) {
        for (int to = 1; to <= 16; to++) {
            bl.step_level = -1; counter = 7; line = 1;
            bd.level = from; stats();
            assert(t551m_backlight_update(&bd) == 0);
            assert(counter == from && line && sleeps == 1);
            bd.level = to; stats();
            assert(t551m_backlight_update(&bd) == 0);
            assert(counter == to && line && bl.step_level == to);
            assert(sleeps == 0 && longest_low_us <= 100 && elapsed_us <= 3000);
            if (from == to) assert(edges == 0);
        }
    }
    for (int level = 1; level <= 16; level++) {
        bd.level = level; bd.blank = true;
        assert(t551m_backlight_update(&bd) == 0);
        assert(!line && bl.step_level == 0);
        bd.blank = false; stats();
        assert(t551m_backlight_update(&bd) == 0);
        assert(line && counter == level && sleeps == 1);
    }
    bd.level = 0;
    assert(t551m_backlight_update(&bd) == 0 && !line);
    stats();
    assert(t551m_backlight_update(&bd) == 0 && edges == 0 && sleeps == 0);
    bd.level = 17;
    assert(t551m_backlight_update(&bd) == -EINVAL && !line && bl.step_level == 0);
    puts("PASS: 256 lit transitions, 16 blank/resume cycles, zero and invalid levels");
}
'''


def main():
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for header in ('linux/gpio/consumer.h', 'linux/delay.h'):
            path = root / header
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        (root / 'test.c').write_text(HARNESS)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I', str(root), '-I', str(source), str(root / 'test.c'),
                        '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
