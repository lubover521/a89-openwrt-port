"""Verify the real MUSB work gates cannot strand an old host behind BC1.2."""
from pathlib import Path
import subprocess
import sys
import tempfile

source=(Path(sys.argv[1])/'drivers/usb/musb/musb_sprd.c').read_text()
start=source.index('static void musb_sprd_ext_event_notify(')
end=source.index('\n/**',source.index('static void musb_sprd_resume_work(',start))
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define dev_dbg(...) ((void)0)
#define dev_info(...) ((void)0)
#define atomic_read(p) (*(p))
#define set_bit(n,p) (*(p)|=1UL<<(n))
#define clear_bit(n,p) (*(p)&=~(1UL<<(n)))
enum {ID,B_SESS_VLD,B_SUSPEND,A_RECOVER,B_DATA_DISABLED};
enum {MUSB_ID_FLOAT,MUSB_ID_GROUND};
enum {DRD_STATE_IDLE,DRD_STATE_HOST,DRD_STATE_HOST_IDLE};
enum {USB_CHG_STATE_UNDETECT,USB_CHG_STATE_DETECTED,USB_CHG_STATE_RETRY_DETECTED};
struct work_struct {int unused;};
struct delayed_work {int unused;};
struct sprd_glue {
    struct work_struct resume_work;
    struct delayed_work sm_work;
    void *dev,*sm_usb_wq,*musb_wq;
    int id_state,drd_state,chg_state,pm_suspended,usb_data_enabled;
    bool vbus_active,charging_mode,in_restart,gadget_suspend,host_recover;
    unsigned long inputs;
};
static int boot_charging,queued_sm,queued_resume,slept;
static void flush_delayed_work(void *w) {}
static void queue_delayed_work(void *q,void *w,int delay) {queued_sm++;}
static void queue_work(void *q,void *w) {queued_resume++;}
static void msleep(int t) {slept++;}
'''
tests=r'''
int main(void) {
    struct sprd_glue g={.id_state=MUSB_ID_FLOAT,.drd_state=DRD_STATE_HOST,
        .vbus_active=true,.usb_data_enabled=1};
    musb_sprd_resume_work(&g.resume_work);
    assert(queued_sm==1 && !queued_resume && !slept);
    assert(g.inputs&(1UL<<ID));
    assert(!(g.inputs&(1UL<<B_SESS_VLD))); /* Never start gadget during detection. */
    g.charging_mode=true;g.chg_state=USB_CHG_STATE_DETECTED;queued_sm=0;
    musb_sprd_resume_work(&g.resume_work);
    assert(queued_sm==1 && !(g.inputs&(1UL<<B_SESS_VLD)));
    g.drd_state=DRD_STATE_IDLE;queued_sm=0;
    musb_sprd_resume_work(&g.resume_work);
    assert(!queued_sm); /* DCP is power only. */
    g.charging_mode=false;g.chg_state=USB_CHG_STATE_UNDETECT;
    musb_sprd_resume_work(&g.resume_work);
    assert(!queued_sm); /* Detection pending after teardown. */
    g.chg_state=USB_CHG_STATE_DETECTED;
    musb_sprd_resume_work(&g.resume_work);
    assert(queued_sm==1 && (g.inputs&(1UL<<B_SESS_VLD)));
    g.id_state=MUSB_ID_GROUND;g.vbus_active=false;queued_sm=0;
    musb_sprd_resume_work(&g.resume_work);
    assert(queued_sm==1 && !(g.inputs&(1UL<<ID))); /* Ordinary OTG unchanged. */
    puts("PASS: host teardown before BC1.2, charger cannot start gadget, computer and OTG gates retained");
}
'''
with tempfile.TemporaryDirectory(prefix='musb-charge-transition-') as tmp:
    path=Path(tmp)
    (path/'test.c').write_text(prelude+source[start:end]+tests)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
