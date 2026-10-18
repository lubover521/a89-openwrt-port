#!/usr/bin/env python3
"""Exercise the patched reset worker and OpenWrt's radio recovery callback."""
from pathlib import Path
import subprocess
import sys
import tempfile

top = Path(__file__).resolve().parents[1]
base = Path(sys.argv[1]) / 'drivers/unisoc_platform/sprd_wlan_combo'
text = (base / 'common/cfg80211.c').read_text()
start = text.index('static void sprd_do_reset_delay_work(')
worker = text[start:text.index('\nstatic void sprd_init_reset_delay_work(', start)]
c = r'''
#include <assert.h>
#include <stddef.h>
#include <string.h>
struct work_struct { int unused; };
struct device { int kobj; };
struct sprd_hif { int reset_lock, cp_asserted, report_try, block_cmd_after_close; };
struct sprd_priv { struct {struct work_struct work;} reset_delay_work; struct sprd_hif hif; struct device *wiphy; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define KOBJ_CHANGE 2
#define wl_info(...) ((void)0)
static int events, reports, scheduled;
static void mutex_lock(int *p) {}
static void mutex_unlock(int *p) {}
static int atomic_read(int *p) {return *p;}
static struct device *wiphy_dev(struct device *d) {return d;}
static int kobject_uevent_env(int *p,int action,char **env) {
 assert(action==KOBJ_CHANGE && !strcmp(env[0],"SC2355_RECOVERY=1") && !env[1]); events++; return 0;
}
static void sprd_iface_report_assert_evt(struct sprd_priv *p) {reports++;}
static int msecs_to_jiffies(int n) {return n;}
static void schedule_delayed_work(void *p,int n) {assert(n==500); scheduled++;}
'''
c += worker + r'''
int main(void) {
 struct device d={0}; struct sprd_priv p={.wiphy=&d};
 sprd_do_reset_delay_work(&p.reset_delay_work.work); assert(events==0);
 p.hif.cp_asserted=1; p.hif.block_cmd_after_close=1;
 sprd_do_reset_delay_work(&p.reset_delay_work.work); assert(events==0);
 p.hif.report_try=0; p.hif.block_cmd_after_close=0;
 for(int i=0;i<7;i++) sprd_do_reset_delay_work(&p.reset_delay_work.work);
 assert(events==1 && reports==5 && scheduled==5);
 p.hif.report_try=0;
 sprd_do_reset_delay_work(&p.reset_delay_work.work); assert(events==2);
}
'''
hook = (top / 'openwrt/overlay/etc/hotplug.d/ieee80211/90-sc2355-recovery').read_text()
function = hook[hook.index('recover_radio()'):hook.index('\n(\n')]
with tempfile.TemporaryDirectory() as tmp:
    temp = Path(tmp)
    source = temp / 'test.c'
    source.write_text(c)
    subprocess.run(['cc', str(source), '-o', str(temp / 'test')], check=True)
    subprocess.run([str(temp / 'test')], check=True)
    # Execute the production function, with only filesystem paths and external
    # wifi/UCI commands replaced. Verify cooldown and manual-disable behavior.
    function = function.replace('/tmp/sc2355-recovery-', str(temp / 'recovery-'))
    shell = r'''
set -eu
config_get() { case "$3" in type) val=mac80211;; path) val=platform/radio;; esac; eval "$1=\$val"; }
config_get_bool() { eval "$1=\$disabled_value"; }
config_load() { :; }
wifi() { printf '%s %s\n' "$1" "$2" >> "$calls"; }
logger() { :; }
sleep() { [ "$disable_during_reset" = 0 ] || disabled_value=1; }
radio_device=/sys/devices/platform/radio
disabled_value=0
disable_during_reset=0
'''
    shell += function + '\n'
    shell += r'''
recover_radio radio0
[ "$(cat "$calls")" = "down radio0
up radio0" ]
recover_radio radio0
[ "$(wc -l < "$calls")" = 2 ]
disabled_value=1
recover_radio radio1
[ "$(wc -l < "$calls")" = 2 ]
disabled_value=0
radio_device=/sys/devices/platform/another
recover_radio radio2
[ "$(wc -l < "$calls")" = 2 ]
radio_device=/sys/devices/platform/radio
disable_during_reset=1
recover_radio radio3
[ "$(tail -1 "$calls")" = "down radio3" ]
[ "$(wc -l < "$calls")" = 3 ]
'''
    import os
    subprocess.run(['sh', '-c', shell], check=True,
                   env={**os.environ, 'calls': str(temp / 'calls')})
print('PASS: one event per reset; five vendor retries; radio matching, cooldown and manual disable')
