#!/usr/bin/env python3
"""Exercise the actual restored full-charge and SOC smoothing C paths."""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
functions = runpy.run_path(str(here / 'test_fuel_gauge.py'))


def main():
    kernel = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='stock-charge-') as tmp:
        root = Path(tmp)
        names = {line[6:] for patch in ('fuel-gauge-state.patch', 'charger-stock-policy.patch')
                 for line in (here / patch).read_text().splitlines() if line.startswith('+++ b/')}
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(['git', '-c', 'safe.directory=' + str(kernel),
                             '-C', str(kernel), 'show', 'HEAD:' + name]))
        functions['apply'](root)
        source = (root / 'drivers/power/supply/charger-manager.c').read_text()
        full = functions['function'](source.replace('static bool is_full_charged',
                                                  'static int is_full_charged'), 'is_full_charged')
        start = source.index('\tswitch (cm->desc->charger_status)', source.index('static void cm_batt_works'))
        end = source.index('\n\twork_cycle = cm_calc_batt_works_cycle', start)
        smooth = 'static int smooth(struct charger_manager *cm, int fuel_cap, int batt_uA, int batt_ocV) {\nint last_fuel_cap=1000, period_time=15,flush_time=30,recharge_uv;struct {int tv_sec;} cur_time={30};\n' + source[start:end] + '\nreturn fuel_cap;\n}'
        stubs = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define CM_CAP_FULL_PERCENT 1000
#define CM_FORCE_SET_FUEL_CAP_FULL 1000
#define CM_HCAP_THRESHOLD 995
#define CM_HCAP_DECREASE_STEP 8
#define CM_CAP_ONE_PERCENT 10
#define DIV_ROUND_CLOSEST(n,d) (((n)+(d)/2)/(d))
#define dev_info(...) ((void)0)
enum {POWER_SUPPLY_PROP_CHARGE_FULL,POWER_SUPPLY_PROP_CAPACITY};
enum {POWER_SUPPLY_STATUS_CHARGING=1, POWER_SUPPLY_STATUS_DISCHARGING,
 POWER_SUPPLY_STATUS_NOT_CHARGING, POWER_SUPPLY_STATUS_FULL};
typedef uint32_t u32;
union power_supply_propval { int intval; };
struct power_supply {};
struct charger_desc {int fullbatt_full_capacity,fullbatt_uV,fullbatt_uA,fullbatt_soc,
 fullbatt_vchkdrop_uV,first_fullbatt_uA,first_trigger_cnt,trigger_cnt,cap,cap_one_time,
 charger_status,update_capacity_time,trickle_time,trickle_time_out;bool force_set_full;char *psy_fuel_gauge;};
struct charger_manager {struct charger_desc *desc;int dev,battery_status;};
static int voltage=4000000,current=1000000,ocv=4000000,calibrations,full_capacity,capacity;
static bool present=true,online=true;
static bool is_batt_present(struct charger_manager *c){return present;}
static bool is_ext_pwr_online(struct charger_manager *c){return online;}
static struct power_supply *power_supply_get_by_name(char *s){static struct power_supply p;return &p;}
static int power_supply_get_property(struct power_supply *p,int prop,union power_supply_propval *v){v->intval=prop==POWER_SUPPLY_PROP_CHARGE_FULL?full_capacity:capacity;return 0;}
static void power_supply_put(struct power_supply *p){}
static int get_vbat_now_uV(struct charger_manager *c,int *v){*v=voltage;return 0;}
static int get_ibat_now_uA(struct charger_manager *c,int *v){*v=current;return 0;}
static int get_batt_ocv(struct charger_manager *c,int *v){*v=ocv;return 0;}
static void adjust_fuel_cap(struct charger_manager *c,int target){assert(target==1000);calibrations++;}
int main(void);
'''
        cases = r'''
int main(void){
 struct charger_desc d={.fullbatt_uV=4400000,.fullbatt_uA=100000,.fullbatt_vchkdrop_uV=100000,.cap=1000,.cap_one_time=30};
 struct charger_manager c={.desc=&d};
 assert(!is_full_charged(&c)); // UI 100% at 4V/1A is not electrical full.
 voltage=4440000;assert(!is_full_charged(&c)); // High charge current.
 current=-100000;assert(!is_full_charged(&c)); // Discharge cannot calibrate full.
 current=80000;assert(!is_full_charged(&c));assert(is_full_charged(&c));assert(calibrations==1);
 d.cap=650;d.trigger_cnt=0;assert(!is_full_charged(&c));assert(!is_full_charged(&c));assert(calibrations==2);
 c.battery_status=POWER_SUPPLY_STATUS_FULL;ocv=4200000;assert(!is_full_charged(&c));assert(!d.force_set_full);
 present=false;assert(!is_full_charged(&c));present=true;c.battery_status=0;
 d.cap=970;d.charger_status=POWER_SUPPLY_STATUS_CHARGING;
 assert(smooth(&c,970,100000,4200000)==970); // No hard-coded 97 -> 100.
 d.cap=600;assert(smooth(&c,900,100000,4200000)==605); // Factory 0.5% step.
 d.charger_status=POWER_SUPPLY_STATUS_DISCHARGING;
 assert(smooth(&c,900,-100000,4200000)==600); // No upward jump on discharge.
 d.cap=990;d.cap_one_time=10;d.charger_status=POWER_SUPPLY_STATUS_CHARGING;
 assert(smooth(&c,1000,100000,4400000)==994); // Original trickle treatment.
 d.charger_status=POWER_SUPPLY_STATUS_FULL;
 assert(smooth(&c,900,10000,4400000)==991); // Full UI rises by original steps.
 return 0;
}
'''
        path = root / 'policy.c'
        path.write_text(stubs + full + '\n' + smooth + cases)
        subprocess.run(['cc', '-Wall', '-Werror', '-Wno-unused-but-set-variable',
                        str(path), '-o', str(root / 'policy')], check=True)
        subprocess.run([str(root / 'policy')], check=True)
        print('PASS: electrical full, consecutive samples, calibration, recharge, factory SOC smoothing')


if __name__ == '__main__':
    main()
