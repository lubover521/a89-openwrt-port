#!/usr/bin/env python3
"""Exercise the imported watchdog PM callbacks against running/stopped hardware."""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
kernel = Path(sys.argv[1]).resolve()
scope = runpy.run_path(str(HERE / 'power.py'))
paths = sorted({line[6:].split('\t', 1)[0] for patch in scope['PATCHES']
                for line in patch.read_text().splitlines() if line.startswith('+++ b/')})
watchdog = 'drivers/watchdog/ump9620-pmic-wdt.c'
dpu = 'drivers/unisoc_platform/sprd_disp/sprd_dpu.c'

with tempfile.TemporaryDirectory() as directory:
    stage = Path(directory)
    for name in paths:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if (kernel / name).exists():
            target.write_bytes((kernel / name).read_bytes())
    apply = scope['apply']
    apply(stage)
    first = {name: (stage / name).read_bytes() for name in paths}
    apply(stage)
    assert all((stage / name).read_bytes() == first[name] for name in paths)

    def function(text, name):
        start = text.index('static int ' + name + '(')
        end = text.index('\n}', start) + 2
        return text[start:end]

    text = (stage / watchdog).read_text()
    code = r'''
#include <assert.h>
#include <stdbool.h>
struct watchdog_device { bool running; };
struct ump9620_wdt { struct watchdog_device wdd; };
struct device { struct ump9620_wdt *data; };
static int stopped, started, ctrl_error, start_error;
static void *dev_get_drvdata(struct device *dev) { return dev->data; }
static bool watchdog_hw_running(struct watchdog_device *wdd) { return wdd->running; }
static int ump9620_wdt_ctrl(struct ump9620_wdt *w, bool on) {
    assert(w && !on); stopped++; return ctrl_error;
}
static int ump9620_wdt_start(struct watchdog_device *wdd) {
    assert(wdd->running); started++; return start_error;
}
'''
    code += function(text, 'ump9620_wdt_suspend') + '\n'
    code += function(text, 'ump9620_wdt_resume') + '\n'
    code += r'''
int main(void) {
    struct ump9620_wdt w = {0}; struct device d = {&w};
    assert(ump9620_wdt_suspend(&d) == 0 && stopped == 0);
    assert(ump9620_wdt_resume(&d) == 0 && started == 0);
    w.wdd.running = true;
    assert(ump9620_wdt_suspend(&d) == 0 && stopped == 1);
    assert(ump9620_wdt_resume(&d) == 0 && started == 1);
    ctrl_error = -5; start_error = -16;
    assert(ump9620_wdt_suspend(&d) == -5);
    assert(ump9620_wdt_resume(&d) == -16);
    return 0;
}
'''
    source = stage / 'pm-test.c'; source.write_text(code)
    binary = stage / 'pm-test'
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    # Reject an unknown second driver before modifying the first driver.
    for name in paths:
        if (kernel / name).exists():
            (stage / name).write_bytes((kernel / name).read_bytes())
    (stage / dpu).write_text('unknown driver revision\n')
    before = {p: p.read_bytes() for p in stage.rglob('*') if p.is_file()}
    try:
        apply(stage)
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown DPU source accepted')
    assert {p: p.read_bytes() for p in stage.rglob('*') if p.is_file()} == before
print('Power callback state/error cases and atomic, idempotent staging passed')
