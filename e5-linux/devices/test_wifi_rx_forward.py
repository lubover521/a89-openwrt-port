#!/usr/bin/env python3
"""Execute the actual AP RX forwarding branch, with/without the endian fix."""
from pathlib import Path
import argparse,subprocess,tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('kernel',type=Path)
p.add_argument('--expect-bug',action='store_true')
a=p.parse_args()
text=(a.kernel/'drivers/unisoc_platform/sprd_wlan_combo/sc2355/rx.c').read_text()
start=text.index('\tif ((vif->mode == SPRD_MODE_AP ||\n\t     vif->mode == SPRD_MODE_P2P_GO) && msdu_desc->uc_w2w_flag)')
end=text.index('\n\t\t/* skb->data MUST point to ETH HDR */',start)
branch=text[start:end]
harness=r'''
#include <arpa/inet.h>
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define SPRD_MODE_AP 2
#define SPRD_MODE_P2P_GO 3
#define SPRD_MODE_STATION 1
#define ETH_P_IP 0x0800
#define ETH_P_IPV6 0x86dd
#define ETH_P_ARP 0x0806
#define GFP_ATOMIC 0
#define likely(x) (x)
struct ethhdr { unsigned short h_proto; };
struct sk_buff { void *dev,*data; };
struct vif { int mode; };
struct desc { int uc_w2w_flag,bc_mc_w2w_flag; };
static struct sk_buff copied;
static int forwarded, delivered, copies, fail_copy;
static struct sk_buff *pskb_copy(struct sk_buff *s,int flags) {
 copies++;if(fail_copy)return NULL;copied=*s;return &copied;
}
static void dev_queue_xmit(struct sk_buff *s) { assert(s->dev);forwarded++; }
static void run(int mode,int uc,int bc,unsigned short proto) {
 struct vif v={mode},*vif=&v;
 struct desc d={uc,bc},*msdu_desc=&d;
 struct ethhdr h={htons(proto)};
 struct sk_buff s={.data=&h},*skb=&s,*tx_skb;
 void *ndev=&h;
 forwarded=delivered=copies=0;
'''+branch+r'''
 delivered++;
 }
}
int main(int argc,char **argv) {
 if(argc>1) {
  assert(htons(ETH_P_IP)!=ETH_P_IP);
  run(SPRD_MODE_AP,0,1,ETH_P_IP);
  assert(forwarded==1 && delivered==1 && copies==1);
  puts("Reproduced: IP multicast gets an extra driver copy before bridge forwarding");return 0;
 }
 for(int mode=SPRD_MODE_AP;mode<=SPRD_MODE_P2P_GO;mode++) {
  for(int ip=0;ip<2;ip++) {
   run(mode,0,1,ip?ETH_P_IPV6:ETH_P_IP);
   assert(forwarded==0 && delivered==1 && copies==0);
  }
  run(mode,0,1,ETH_P_ARP);
  assert(forwarded==1 && delivered==1 && copies==1);
  fail_copy=1;run(mode,0,1,ETH_P_ARP);
  assert(forwarded==0 && delivered==1 && copies==1);fail_copy=0;
  run(mode,1,0,ETH_P_IP);
  assert(forwarded==1 && delivered==0 && copies==0);
  run(mode,0,0,ETH_P_IP);
  assert(forwarded==0 && delivered==1 && copies==0);
 }
 run(SPRD_MODE_STATION,0,1,ETH_P_IPV6);
 assert(forwarded==0 && delivered==1 && copies==0);
 puts("PASS: AP/GO IP multicast goes to stack once; unicast W2W, ARP and allocation failure preserved");
}
'''
with tempfile.TemporaryDirectory() as temp:
    source=Path(temp)/'test.c';binary=Path(temp)/'test'
    source.write_text(harness)
    subprocess.run(['cc','-std=c11','-fsanitize=address,undefined',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)]+(['old'] if a.expect_bug else []),check=True)
