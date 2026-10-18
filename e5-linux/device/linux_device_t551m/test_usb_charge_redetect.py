"""Run the real BC1.2 state machine against stale and fresh hardware results."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel=Path(sys.argv[1])
source=(kernel/'drivers/usb/phy/sprd-bc1p2.c').read_text()
start=source.index('static void sprd_get_bc1p2_type(')
end=source.index('\nstatic void sprd_get_bc1p2_type_work(',start)
header=(kernel/'include/linux/power/sprd-bc1p2.h').read_text()
states=re.search(r'enum sprd_chg_detect_state \{.*?\};',header,re.S)[0]
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define dev_info(...) ((void)0)
#define pr_info(...) ((void)0)
#define fallthrough __attribute__((fallthrough))
#define xchg(p,v) __atomic_exchange_n(p,v,__ATOMIC_SEQ_CST)
#define CHARGER_DETECT_DONE 1
#define SPRD_CHG_MAX_REDETECT_COUNT 5
enum { UNKNOWN_TYPE, SDP_TYPE, DCP_TYPE, CDP_TYPE };
struct usb_phy {void *dev;int chg_type,flags;};
struct sprd_bc1p2 {int detect_state,type,retry_chg_detect_count;bool redetect_enable,shutdown;};
struct sprd_bc1p2_priv {struct usb_phy *phy;struct sprd_bc1p2 *bc1p2;bool redetect_after_host,rework;};
static int raw=SDP_TYPE,fresh=DCP_TYPE,redetects,detects;
static int sprd_bc1p2_detect(void) {detects++;return raw;}
static int sprd_bc1p2_retry_detect(struct usb_phy *x) {redetects++;return fresh;}
static bool sprd_bc1p2_vchg_is_present(unsigned int *a,unsigned int *b) {return true;}
'''
tests=r'''
int main(void) {
    struct usb_phy phy={0};
    struct sprd_bc1p2 bc={.redetect_enable=true};
    struct sprd_bc1p2_priv info={.phy=&phy,.bc1p2=&bc,.redetect_after_host=true};
    sprd_get_bc1p2_type(&info);
    assert(phy.chg_type==DCP_TYPE && phy.flags && redetects==1 && !detects);
    assert(!info.redetect_after_host && !info.rework);
    sprd_get_bc1p2_type(&info);
    assert(redetects==1); /* No persistent redetection loop. */
    bc.detect_state=CHG_STATE_UNDETECT;phy.flags=0;
    info.redetect_after_host=true;fresh=SDP_TYPE;
    sprd_get_bc1p2_type(&info);
    assert(phy.chg_type==SDP_TYPE && redetects==2 && !detects);
    /* A real computer keeps its SDP limit; this never forces DCP. */
    bc.detect_state=CHG_STATE_UNDETECT;phy.flags=0;raw=DCP_TYPE;
    sprd_get_bc1p2_type(&info);
    assert(phy.chg_type==DCP_TYPE && detects==1 && redetects==2);
    /* Failure uses the existing bounded retry path, not the stale SDP. */
    bc.detect_state=CHG_STATE_UNDETECT;phy.flags=0;fresh=UNKNOWN_TYPE;
    info.redetect_after_host=true;
    sprd_get_bc1p2_type(&info);
    assert(phy.chg_type==UNKNOWN_TYPE && !phy.flags && info.rework);
    assert(bc.detect_state==CHG_STATE_RETRY_DETECT);
    fresh=DCP_TYPE;info.rework=false;
    sprd_get_bc1p2_type(&info);
    assert(phy.chg_type==DCP_TYPE && phy.flags && !info.rework);
    puts("PASS: stale OTG result replaced, genuine SDP retained, one-shot detection and bounded failure recovery");
}
'''
with tempfile.TemporaryDirectory(prefix='bc12-role-test-') as tmp:
    path=Path(tmp)
    (path/'test.c').write_text(prelude+states+source[start:end]+tests)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
