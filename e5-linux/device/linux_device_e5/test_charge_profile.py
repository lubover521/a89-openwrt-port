#!/usr/bin/env python3
"""Check the E5-only DCP change and preservation of all thermal boundaries."""
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define SPRD_BATTERY_JEITA_DCP 0
struct sprd_battery_jeita_table {int temp,recovery_temp,current_ua,term_volt;};
struct sprd_battery_info {
 int charge_full_design_uah,constant_charge_voltage_max_uv,voltage_min_design_uv;
 struct {int dcp_cur,dcp_limit,sdp_cur,cdp_cur,unknown_cur;} cur;
 struct sprd_battery_jeita_table *jeita_table[1];
 unsigned int sprd_battery_jeita_size[1],max_current_jeita_index[1];
};
'''
test = r'''
int main(void) {
 struct sprd_battery_jeita_table rows[]={
  {0,0,0,4340000},{150,150,650000,4340000},
  {450,450,1650000,4370000},{550,550,650000,4340000}};
 struct sprd_battery_jeita_table original[4];memcpy(original,rows,sizeof(rows));
 struct sprd_battery_info info={3082000,4370000,3433000,
  {1650000,1650000,500000,1650000,1650000},{rows},{4},{2}};
 struct sprd_battery_info before=info;
 assert(e5_dcp_profile(&info));
 assert(info.cur.dcp_cur==2480000 && info.cur.dcp_limit==3000000);
 assert(info.cur.sdp_cur==500000 && info.cur.cdp_cur==1650000 && info.cur.unknown_cur==1650000);
 for(int i=0;i<4;i++) {
  assert(rows[i].temp==original[i].temp && rows[i].recovery_temp==original[i].recovery_temp);
  assert(rows[i].term_volt==original[i].term_volt);
  assert(rows[i].current_ua==(i==2?2480000:original[i].current_ua));
 }
 assert(!e5_dcp_profile(&info));
 for(int bad=0;bad<6;bad++) {
  info=before;memcpy(rows,original,sizeof(rows));
  switch(bad) {
   case 0:info.charge_full_design_uah++;break;
   case 1:info.constant_charge_voltage_max_uv++;break;
   case 2:info.cur.dcp_limit=500000;break;
   case 3:rows[2].term_volt=4400000;break;
   case 4:rows[3].temp=500;break;
   case 5:info.jeita_table[0]=NULL;break;
  }
  struct sprd_battery_info saved=info;
  struct sprd_battery_jeita_table saved_rows[4];memcpy(saved_rows,rows,sizeof(rows));
  assert(!e5_dcp_profile(&info));
  assert(!memcmp(&saved,&info,sizeof(info)) && !memcmp(saved_rows,rows,sizeof(rows)));
 }
 puts("PASS: E5 DCP only; battery hardware ceiling, source policies, voltage/JEITA bounds and unknown boards protected");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(prelude + (HERE / 'charge-profile.h').read_text() + test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
