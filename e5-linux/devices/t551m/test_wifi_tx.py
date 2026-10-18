#!/usr/bin/env python3
"""Exercise the actual TX preparation C with allocation/clone failures.

Run against a prepared kernel. --expect-bug demonstrates the old ownership
violation before applying wifi.py; no hardware, radio or packet injection.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def function(text, name):
    start = text.index('static int ' + name + '(')
    body = text.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define unlikely(x) (x)
#define wl_err(...) ((void)0)
#define netdev_err(...) ((void)0)
struct sk_buff { int headroom, cloned, freed, linear_fail; };
struct sprd_hif { int cp_asserted, exit; };
struct sprd_priv { struct sprd_hif hif; int chip; };
struct sprd_vif { struct sprd_priv *priv; };
struct net_device { int needed_headroom; struct {int tx_dropped;} stats; };
static int alloc_fail, allocations;
static struct sk_buff replacement;
static int skb_linearize(struct sk_buff *s) {return s->linear_fail;}
static void dev_kfree_skb(struct sk_buff *s) {assert(!s->freed);s->freed=1;}
static void iface_stop_net(struct sprd_vif *v) {(void)v;}
static int sprd_chip_tx_prepare(int *chip, struct sk_buff *s) {(void)chip;(void)s;return 0;}
static int skb_headroom(struct sk_buff *s) {return s->headroom;}
static struct sk_buff *skb_realloc_headroom(struct sk_buff *s,int h) {
    allocations++;
    if(alloc_fail)return NULL;
    replacement=*s;replacement.headroom=h;replacement.cloned=0;return &replacement;
}
static int skb_cow_head(struct sk_buff *s,int h) {
    if(s->headroom<h || s->cloned) {
        allocations++;
        if(alloc_fail)return -1;
        s->headroom=h;s->cloned=0;
    }
    return 0;
}
@FUNCTION@
int main(int argc,char **argv) {
    struct sprd_priv priv={0}; struct sprd_vif vif={&priv};
    struct net_device dev={.needed_headroom=28};
    struct sk_buff skb={.headroom=8}, *p=&skb;
    int ret=iface_prepare_xmit(&vif,&dev,&p);
    if(argc>1) {
        assert(ret==0 && skb.freed && p!=&skb);
        puts("Reproduced: queue-full retry would reuse freed original skb");return 0;
    }
    assert(ret==0 && p==&skb && !skb.freed && skb.headroom>=28);
    /* A later NETDEV_TX_BUSY must leave this original object alive. */
    allocations=0;skb=(struct sk_buff){.headroom=64,.cloned=1};p=&skb;
    assert(iface_prepare_xmit(&vif,&dev,&p)==0);
    assert(!skb.cloned && !skb.freed && p==&skb && allocations==1);
    allocations=0;skb=(struct sk_buff){.headroom=64};p=&skb;
    assert(iface_prepare_xmit(&vif,&dev,&p)==0 && allocations==0);
    alloc_fail=1;skb=(struct sk_buff){.headroom=8};p=&skb;
    assert(iface_prepare_xmit(&vif,&dev,&p)==-1 && skb.freed);
    alloc_fail=0;skb=(struct sk_buff){.linear_fail=1};p=&skb;
    assert(iface_prepare_xmit(&vif,&dev,&p)==-1 && skb.freed);
    for(int i=0;i<2;i++) {
        priv.hif.cp_asserted=!i;priv.hif.exit=i;skb=(struct sk_buff){0};p=&skb;
        assert(iface_prepare_xmit(&vif,&dev,&p)==-1 && skb.freed);
    }
    puts("PASS: skb ownership, cloned headers, fast path and 4 failure paths");
    return 0;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel',type=Path)
    parser.add_argument('--expect-bug',action='store_true')
    args=parser.parse_args()
    text=(args.kernel/'drivers/unisoc_platform/sprd_wlan_combo/common/iface.c').read_text()
    code=HARNESS.replace('@FUNCTION@',function(text,'iface_prepare_xmit'))
    with tempfile.TemporaryDirectory(prefix='wifi-tx-test-') as directory:
        src=Path(directory)/'test.c';binary=Path(directory)/'test'
        src.write_text(code)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Wno-unused-parameter',
                        '-Wno-unused-function','-fsanitize=address,undefined',
                        '-o',str(binary),str(src)],check=True)
        subprocess.run([str(binary)]+(['old'] if args.expect_bug else []),check=True)


if __name__=='__main__':
    main()
