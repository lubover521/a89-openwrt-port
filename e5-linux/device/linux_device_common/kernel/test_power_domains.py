#!/usr/bin/env python3
"""Run actual camera/GPU transition functions with clock and regmap failures."""
from pathlib import Path
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1])


def function(text, name):
    for prefix in ('static int ', 'static void '):
        start = text.find(prefix + name + '(')
        if start >= 0:
            return text[start:text.index('\n}', start) + 2] + '\n'
    raise ValueError(name)


camera = (kernel/'drivers/soc/sprd/domain/sprd_camsys_pd.c').read_text()
types = camera[camera.index('#define CAMSYS_POLL_MAX'):camera.index('static int camsys_reg_get')]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
typedef unsigned int u32;
struct regmap { int unused; };
struct device { int unused; };
struct clk { int unused; };
struct generic_pm_domain { int unused; };
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define __ffs(x) __builtin_ctz(x)
#define dev_err(...) ((void)0)
static unsigned int regs[9], masks[9];
static int writes, reads, fail_write, fail_read, clock_refs, fail_clock, bad_state;
static int order[100], orders;
static void usleep_range(int a, int b) { assert(a==300 && b==350); }
static int regmap_update_bits(struct regmap *m, unsigned int r, unsigned int mask, unsigned int value) {
    (void)m; assert(r<9); writes++;
    if (writes==fail_write) return -EIO;
    regs[r]=(regs[r]&~mask)|(value&mask);
    if (r%3==0) {
        order[orders++]=r/3;
        regs[r+2]=value ? 7U<<__ffs(masks[r+2]) : 0;
    }
    return 0;
}
static int regmap_read(struct regmap *m, unsigned int r, unsigned int *value) {
    (void)m; assert(r<9); reads++;
    if (reads==fail_read) return -EIO;
    *value=bad_state ? masks[r] : regs[r]; return 0;
}
static int clk_prepare_enable(struct clk *c) {
    (void)c; if(fail_clock) return -EBUSY; clock_refs++; return 0;
}
static void clk_disable_unprepare(struct clk *c) { (void)c; assert(clock_refs==1); clock_refs--; }
'''+types
for name in ('camsys_switch', 'camsys_all_off', 'camsys_all_on', 'camsys_clock_off',
             'camsys_pd_power_on', 'camsys_pd_power_off'):
    code += function(camera, name)
code += r'''
static struct camsys_pd fresh(void) {
    struct camsys_pd p={0};
    memset(regs,0,sizeof(regs)); memset(masks,0,sizeof(masks));
    writes=reads=fail_write=fail_read=clock_refs=fail_clock=bad_state=orders=0;
    for(int i=0;i<3;i++) {
        p.banks[i].force=(struct camsys_reg){NULL,(u32)(3*i),1U<<25};
        p.banks[i].automatic=(struct camsys_reg){NULL,(u32)(3*i+1),1U<<24};
        p.banks[i].state=(struct camsys_reg){NULL,(u32)(3*i+2),0x1fU<<(8*i)};
        masks[3*i+2]=p.banks[i].state.mask;
        regs[3*i+2]=7U<<(8*i);
    }
    return p;
}
static void assert_on(void) { for(int i=0;i<3;i++) assert(regs[3*i+2]==0); }
static void assert_off(void) { for(int i=0;i<3;i++) assert(regs[3*i+2]==(7U<<(8*i))); }
int main(void) {
    struct camsys_pd p=fresh();
    assert(camsys_pd_power_on(&p.gpd)==0); assert_on();
    assert(clock_refs==1 && p.clock_on && orders==3);
    assert(order[0]==0 && order[1]==1 && order[2]==2);
    assert(camsys_pd_power_off(&p.gpd)==0); assert_off();
    assert(!clock_refs && !p.clock_on && orders==6);
    assert(order[3]==1 && order[4]==2 && order[5]==0);
    for(int i=1;i<=6;i++) {
        p=fresh(); fail_write=i;
        assert(camsys_pd_power_on(&p.gpd)==-EIO); assert_off();
        assert(!clock_refs && !p.clock_on);
        p=fresh(); assert(camsys_pd_power_on(&p.gpd)==0);
        fail_write=writes+i;
        assert(camsys_pd_power_off(&p.gpd)==-EIO); assert_on();
        assert(clock_refs==1 && p.clock_on);
    }
    for(int i=1;i<=9;i++) {
        p=fresh(); fail_read=i;
        assert(camsys_pd_power_on(&p.gpd)==-EIO); assert_off();
        assert(!clock_refs && !p.clock_on);
    }
    p=fresh(); fail_clock=1;
    assert(camsys_pd_power_on(&p.gpd)==-EBUSY && writes==0 && !p.clock_on);
    p=fresh(); bad_state=1;
    assert(camsys_switch(&p.banks[0],true)==-ETIMEDOUT && reads==90);
    p=fresh(); p.banks[0].state.mask=1;
    assert(camsys_switch(&p.banks[0],false)==-EINVAL && writes==0);
    return 0;
}
'''

gpu = (kernel/'drivers/gpu/drm/panfrost/panfrost_sprd.c').read_text()
gpu_code = r'''
#include <assert.h>
struct regmap { int unused; };
struct reg { struct regmap *map; int reg,mask; };
struct panfrost_sprd { struct reg clk_core_gpu_eb; struct regmap *gpu_dvfs_apb; };
struct panfrost_device { void *dev,*rstc; };
static int powered,stops,writes,fail_write,wait_error;
#define SPRD_DVFS_APB_FREQ_UPD_CFG0 1
#define SPRD_DVFS_APB_FREQ_UPD_MASK 3
#define SPRD_DVFS_APB_DVFS_INDEX_CFG 2
#define SPRD_DVFS_APB_DVFS_INDEX_MASK 7
#define SPRD_DVFS_INDEX_DEFAULT 3
#define dev_err(...) ((void)0)
static void sprd_gpu_power_on(struct panfrost_sprd *s,void *r) { (void)s;(void)r; powered=1; }
static void sprd_gpu_stop(struct panfrost_sprd *s) { (void)s; powered=0;stops++; }
static int sprd_gpu_top_state_wait(struct panfrost_sprd *s) { (void)s;return wait_error; }
static void udelay(int d) { assert(d==400); }
static int regmap_update_bits(struct regmap *m,int r,int mask,int value) {
    (void)m;(void)r;(void)mask;(void)value;return ++writes==fail_write ? -5 : 0;
}
'''+function(gpu, 'sprd_gpu_start')+r'''
int main(void) {
    struct panfrost_device p={0};struct panfrost_sprd s={0};
    assert(sprd_gpu_start(&p,&s)==0 && powered && stops==0 && writes==3);
    powered=stops=writes=0;wait_error=-110;
    assert(sprd_gpu_start(&p,&s)==-110 && !powered && stops==1);
    wait_error=0;
    for(int i=1;i<=3;i++) {
        powered=stops=writes=0;fail_write=i;
        assert(sprd_gpu_start(&p,&s)==-5 && !powered && stops==1);
    }
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    for name, text in [('camera',code),('gpu',gpu_code)]:
        root=Path(directory);source=root/(name+'.c');source.write_text(text)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(source),'-o',str(root/name)],check=True)
        subprocess.run([str(root/name)],check=True)
print('Camera stock sequencing, clocks, all transition bus errors, timeout and GPU rollback passed')
