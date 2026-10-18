#!/usr/bin/env python3
"""Inject registration failures into the actual patched C notifier functions.

Usage (Linux + cc): test_wifi_lifetime.py /path/to/patched/kernel
"""
from pathlib import Path
import subprocess
import sys
import tempfile

base = Path(sys.argv[1]) / 'drivers/unisoc_platform/sprd_wlan_combo'
text = (base / 'common/iface.c').read_text()
functions = text[text.index('static int iface_notify_init('):text.index('\nstatic void iface_init_vif(')]
harness = r'''
#include <assert.h>
#include <stdbool.h>
struct sprd_hif { int reset_lock; };
struct sprd_priv { struct sprd_hif hif; int fw_capa, reset_delay_work; };
#define SPRD_CAPA_NS_OFFLOAD 1
static int wlan_misc_device, iface_inetaddr_cb, iface_inet6addr_cb;
static int wcn_reset_notifier_list, iface_host_reset_cb;
static int failure, step, alive[5], canceled;
static int acquire(int n) { step++; if (step == failure) return -5; assert(!alive[n]); alive[n]=1; return 0; }
static void release(int n) { assert(alive[n]); alive[n]=0; }
static void mutex_init(int *p) { assert(!alive[0]); alive[0]=1; }
static void mutex_destroy(int *p) { assert(!alive[1] && !alive[2] && !alive[3] && !alive[4]); release(0); }
static int misc_register(int *p) { return acquire(1); }
static int register_inetaddr_notifier(int *p) { return acquire(2); }
static int register_inet6addr_notifier(int *p) { return acquire(3); }
static int atomic_notifier_chain_register(int *p,int *q) { assert(alive[0] && alive[1] && alive[2]); return acquire(4); }
static void misc_deregister(int *p) { release(1); }
static void unregister_inetaddr_notifier(int *p) { release(2); }
static void unregister_inet6addr_notifier(int *p) { release(3); }
static void atomic_notifier_chain_unregister(int *p,int *q) { release(4); }
static void cancel_delayed_work_sync(int *p) { assert(alive[0] && !alive[4]); canceled++; }
static void sprd_cancel_reset_work(struct sprd_priv *p) { assert(alive[0] && !alive[4]); }
'''
harness += functions + r'''
int main(void) {
    for (int ipv6=0; ipv6<=1; ipv6++) {
        struct sprd_priv p={.fw_capa=ipv6};
        for (failure=1; failure<=4; failure++) {
            step=0;
            int rc=iface_notify_init(&p);
            if (!rc) iface_notify_deinit(&p);
            else assert(rc==-5);
            for(int j=0;j<5;j++) assert(!alive[j]);
        }
        failure=0; step=0; assert(iface_notify_init(&p)==0);
        iface_notify_deinit(&p);
        for(int j=0;j<5;j++) assert(!alive[j]);
    }
    assert(canceled>=2);
}
'''
with tempfile.TemporaryDirectory() as temp:
    source = Path(temp) / 'test.c'
    source.write_text(harness)
    for define in ([], ['-DDRV_RESET_SELF']):
        binary = Path(temp) / 'test'
        subprocess.run(['cc', '-std=c11', *define, str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
print('PASS: all notifier registration failures unwind; both reset modes unregister before cancel/free')
