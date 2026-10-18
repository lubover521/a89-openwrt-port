#!/usr/bin/env python3
"""Exercise the board profile correction without bypassing thermal policy."""
from pathlib import Path
import subprocess
import tempfile

header = Path(__file__).with_name('charge-profile.h').read_text()
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define SPRD_BATTERY_JEITA_DCP 0
struct sprd_battery_jeita_table { int temp,recovery_temp,current_ua,term_volt; };
struct sprd_battery_info {
    int charge_full_design_uah,constant_charge_voltage_max_uv,voltage_min_design_uv;
    struct {int dcp_cur,dcp_limit,sdp_cur,sdp_limit,cdp_cur,unknown_cur;} cur;
    struct sprd_battery_jeita_table *jeita_table[2];
    unsigned int sprd_battery_jeita_size[2],max_current_jeita_index[2];
};
'''
tests = r'''
int main(void) {
    struct sprd_battery_jeita_table rows[]={
        {0,0,0,4400000},{100,100,580000,4400000},
        {450,450,1000000,4400000},{550,500,1000000,4100000}};
    struct sprd_battery_jeita_table before[4];
    memcpy(before,rows,sizeof(rows));
    struct sprd_battery_info info={
        .charge_full_design_uah=3832000,.constant_charge_voltage_max_uv=4400000,.voltage_min_design_uv=3456000,
        .cur={1000000,1000000,500000,500000,1000000,1000000},
        .jeita_table={rows,NULL},.sprd_battery_jeita_size={4,0},.max_current_jeita_index={2,0}};
    struct sprd_battery_info original=info;
    assert(board_restore_dcp_profile(&info));
    assert(info.cur.dcp_cur==3000000 && info.cur.dcp_limit==3000000);
    assert(rows[2].current_ua==3000000 && info.max_current_jeita_index[0]==2);
    assert(info.cur.sdp_cur==500000 && info.cur.sdp_limit==500000);
    assert(info.cur.cdp_cur==1000000 && info.cur.unknown_cur==1000000);
    for (unsigned int i=0;i<4;i++) {
        assert(rows[i].temp==before[i].temp && rows[i].recovery_temp==before[i].recovery_temp);
        assert(rows[i].term_volt==before[i].term_volt);
        if (i!=2) assert(rows[i].current_ua==before[i].current_ua);
    }
    assert(!board_restore_dcp_profile(&info));
    for (int bad=0;bad<8;bad++) {
        info=original;memcpy(rows,before,sizeof(rows));
        switch(bad) {
        case 0:info.charge_full_design_uah=4000000;break;
        case 1:info.constant_charge_voltage_max_uv=4200000;break;
        case 2:info.cur.dcp_limit=500000;break;
        case 3:info.sprd_battery_jeita_size[0]=3;break;
        case 4:rows[3].temp=500;break;
        case 5:rows[3].current_ua=580000;break;
        case 6:rows[2].term_volt=4200000;break;
        case 7:info.jeita_table[0]=NULL;break;
        }
        struct sprd_battery_info saved=info;
        struct sprd_battery_jeita_table saved_rows[4];memcpy(saved_rows,rows,sizeof(rows));
        assert(!board_restore_dcp_profile(&info));
        assert(!memcmp(&saved,&info,sizeof(info)) && !memcmp(saved_rows,rows,sizeof(rows)));
    }
    puts("PASS: exact profile correction, cold/warm/voltage/SDP protection, mismatched profiles untouched");
}
'''
with tempfile.TemporaryDirectory(prefix='charge-profile-test-') as temp:
    root=Path(temp)
    (root/'test.c').write_text(prelude+header+tests)
    subprocess.run(['cc','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True)
