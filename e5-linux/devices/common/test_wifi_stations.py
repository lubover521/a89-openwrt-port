#!/usr/bin/env python3
"""Exercise the compiled driver's actual AP table and channel callbacks."""
from pathlib import Path
import re, subprocess, sys, tempfile

source = (Path(sys.argv[1]) / 'drivers/unisoc_platform/sprd_wlan_combo/common/cfg80211.c').read_text()


def function(name):
    m = re.search(r'(?m)^(?:static )?(?:int|bool) '+name+r'\([^;{}]*\)\s*\{', source)
    assert m, name
    a = source.index('{', m.start()); depth = 1; b = a + 1
    while depth:
        depth += (source[b] == '{') - (source[b] == '}'); b += 1
    return source[m.start():b] + '\n'


prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
typedef unsigned char u8;
#define ETH_ALEN 6
#define MAX_LUT_NUM 8
#define READ_ONCE(x) (x)
enum {NL80211_IFTYPE_AP,NL80211_IFTYPE_P2P_GO,NL80211_IFTYPE_STATION};
struct cfg80211_chan_def {void *chan;int width;};
struct wireless_dev {int iftype;struct {struct {struct cfg80211_chan_def chandef;} ap;} links[1];};
struct station_info {unsigned long filled;};
struct sprd_hif {struct {u8 ctx_id;struct {u8 da[6];} tx;} peer_entry[MAX_LUT_NUM];};
struct priv {struct sprd_hif hif;};
struct net_device;
struct sprd_vif {struct priv*priv;struct net_device*ndev;struct wireless_dev wdev;u8 ctx_id;};
struct net_device {u8 dev_addr[6];struct sprd_vif*vif;};
struct wiphy {int unused;};
#define netdev_priv(n) ((n)->vif)
static bool is_valid_ether_addr(const u8*a){static const u8 z[6]={0};return !(a[0]&1)&&memcmp(a,z,6);}
static bool ether_addr_equal(const u8*a,const u8*b){return !memcmp(a,b,6);}
static void ether_addr_copy(u8*a,const u8*b){memcpy(a,b,6);}
'''
test = r'''
int main(void){
 struct priv priv={0};struct net_device dev={{2,1,2,3,4,5},0};
 struct sprd_vif vif={&priv,&dev,{.iftype=NL80211_IFTYPE_AP},3};dev.vif=&vif;
 const u8 mac[6]={2,0xaa,0xbb,0xcc,0xdd,1},other[6]={2,0xaa,0xbb,0xcc,0xdd,2};
 u8 out[6];struct station_info info={123};
 for(int i=0;i<MAX_LUT_NUM;i++)priv.hif.peer_entry[i].ctx_id=0xff;
 priv.hif.peer_entry[0].ctx_id=3;memcpy(priv.hif.peer_entry[0].tx.da,dev.dev_addr,6);
 priv.hif.peer_entry[1].ctx_id=3;memset(priv.hif.peer_entry[1].tx.da,255,6);
 priv.hif.peer_entry[2].ctx_id=4;memcpy(priv.hif.peer_entry[2].tx.da,other,6);
 priv.hif.peer_entry[3].ctx_id=3;memcpy(priv.hif.peer_entry[3].tx.da,mac,6);
 assert(!sprd_ap_peer(&vif,other));assert(sprd_ap_peer(&vif,mac));
 assert(sprd_cfg80211_dump_station(0,&dev,-1,out,&info)==-ENOENT);
 assert(!sprd_cfg80211_dump_station(0,&dev,0,out,&info));assert(!memcmp(out,mac,6)&&!info.filled);
 assert(sprd_cfg80211_dump_station(0,&dev,1,out,&info)==-ENOENT);
 priv.hif.peer_entry[3].ctx_id=0xff;assert(!sprd_ap_peer(&vif,mac));
 assert(sprd_cfg80211_dump_station(0,&dev,0,out,&info)==-ENOENT);
 vif.wdev.iftype=NL80211_IFTYPE_STATION;assert(sprd_cfg80211_dump_station(0,&dev,0,out,&info)==-ENOENT);
 struct cfg80211_chan_def chandef={0};vif.wdev.links[0].ap.chandef=(struct cfg80211_chan_def){&priv,80};
 assert(sprd_cfg80211_get_channel(0,&vif.wdev,0,&chandef)==-ENODATA);
 vif.wdev.iftype=NL80211_IFTYPE_AP;assert(!sprd_cfg80211_get_channel(0,&vif.wdev,0,&chandef));assert(chandef.width==80);
 assert(sprd_cfg80211_get_channel(0,&vif.wdev,1,&chandef)==-ENODATA);
 assert(sprd_cfg80211_get_channel(0,&vif.wdev,~0U,&chandef)==-ENODATA);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    (p/'test.c').write_text(prelude+''.join(function(n) for n in ('sprd_ap_peer','sprd_cfg80211_dump_station','sprd_cfg80211_get_channel'))+test)
    subprocess.run(['cc','-Wall','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('PASS: real AP callback C, self/group/context filtering, disconnect, STA isolation and channel link bounds')
