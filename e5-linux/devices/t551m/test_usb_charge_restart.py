"""Exercise the real analogue restart against late VBUS and cable changes."""
from pathlib import Path
import subprocess,sys,tempfile
source=(Path(sys.argv[1])/'drivers/usb/phy/sprd-bc1p2.c').read_text()
start=source.index('enum usb_charger_type sprd_bc1p2_retry_detect(')
end=source.index('\nEXPORT_SYMBOL_GPL(sprd_bc1p2_retry_detect)',start)
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define BIT(n) (1u<<(n))
#define dev_info(...) ((void)0)
#define USB_EVENT_ID 3
#define SPRD_CHG_DET_POLL_DELAY 20
enum usb_charger_type { UNKNOWN_TYPE, SDP_TYPE, DCP_TYPE, CDP_TYPE };
struct usb_phy {void *dev;int last_event;};
struct regs {int chg_det_fgu_ctrl;};
struct chip {void *regmap;struct regs *data;bool shutdown;int chg_redet_poll_count;};
static struct regs data={.chg_det_fgu_ctrl=0x23a0};
static struct chip chip={.data=&data};
static struct chip *bc1p2=&chip;
static struct usb_phy phy;
static unsigned control=0x2f0;
static int reads,writes,settle=3,detected,redetect_off,detach_during_reset;
static enum usb_charger_type result=DCP_TYPE;
static bool sprd_bc1p2_vchg_is_present(unsigned *a,unsigned *b) {reads++;return reads>settle;}
static int sprd_bc1p2_redetect_control(bool on) {assert(!on);redetect_off++;return 0;}
static int regmap_update_bits(void *m,int reg,unsigned mask,unsigned value) {
    assert(reads>=settle+5 && reg==0x23a0 && mask==BIT(0));
    control=(control&~mask)|value;writes++;return 0;
}
static void msleep(int ms) {assert(ms==20);if(detach_during_reset&&writes==1)phy.last_event=USB_EVENT_ID;}
static enum usb_charger_type sprd_bc1p2_detect(void) {
    assert(writes==2 && control==0x2f0 && redetect_off==1);
    detected++;return result;
}
static void reset(void) {reads=writes=detected=redetect_off=0;control=0x2f0;phy.last_event=0;}
'''
tests=r'''
int main(void) {
    assert(sprd_bc1p2_retry_detect(&phy)==DCP_TYPE);
    assert(detected==1 && reads==8);
    reset();result=SDP_TYPE;
    assert(sprd_bc1p2_retry_detect(&phy)==SDP_TYPE && detected==1);
    reset();settle=100;
    assert(sprd_bc1p2_retry_detect(&phy)==UNKNOWN_TYPE && reads==40 && !writes);
    reset();phy.last_event=USB_EVENT_ID;
    assert(sprd_bc1p2_retry_detect(&phy)==UNKNOWN_TYPE && !reads && !writes);
    reset();settle=0;detach_during_reset=1;
    assert(sprd_bc1p2_retry_detect(&phy)==UNKNOWN_TYPE && writes==1 && !detected);
    assert(control&BIT(0)); /* A new host retains ownership of D+/D-. */
    puts("PASS: stable VBUS required, masked analogue reset, genuine SDP, timeout and new-host cancellation");
}
'''
with tempfile.TemporaryDirectory(prefix='bc12-restart-') as tmp:
    p=Path(tmp)
    (p/'test.c').write_text(prelude+source[start:end]+tests)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
