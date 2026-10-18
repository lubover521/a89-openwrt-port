"""Exercise actual probe/setup/cleanup code with a root-hub ownership model."""
from pathlib import Path
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1])
core = (kernel/'drivers/usb/musb/musb_core.c').read_text()
host = (kernel/'drivers/usb/musb/musb_host.c').read_text()
a = core.index('\tswitch (musb->port_mode)', core.index('musb_init_controller('))
b = core.index('\n\tif (status < 0)', core.index('\n\tdefault:', a))
probe = core[a:b]
a = host.index('void musb_host_cleanup(')
cleanup = host[a:host.index('\nEXPORT_SYMBOL_GPL(musb_host_cleanup);', a)]
a = host.index('int musb_host_setup(')
setup = host[a:host.index('\nEXPORT_SYMBOL_GPL(musb_host_setup);', a)]
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
enum {MUSB_HOST=1,MUSB_PERIPHERAL,MUSB_OTG,MUSB_DMA_SPRD=1024,
      OTG_STATE_A_IDLE=1,PHY_MODE_USB_HOST=1};
struct usb_device {int autosuspend_disabled;};
struct usb_bus {int otg_port,is_b_host; void *controller; struct usb_device *root_hub;};
struct usb_hcd {struct usb_bus self; int power_budget,skip_phy_initialization,rh_registered;};
struct usb_otg {struct usb_bus *host;};
struct phy {struct usb_otg *otg;};
struct ops {int quirks;};
struct musb {struct usb_hcd *hcd; int port_mode; struct ops *ops; struct phy *xceiv; void *phy;};
struct platform {int power;};
static int adds,removes,live,gadget,error,gadget_error,pm_disables;
static struct usb_device root;
#define MUSB_HST_MODE(m) ((void)0)
#define dev_err(...) ((void)0)
static void musb_set_state(struct musb *m,int state) {}
static void otg_set_host(struct usb_otg *o,struct usb_bus *b) {}
static void phy_set_mode(void *p,int mode) {}
static void device_wakeup_enable(void *d) {}
static int usb_add_hcd(struct usb_hcd *h,int irq,int flags) {
    assert(!h->rh_registered && live==0); /* Reusing a live HCD is invalid. */
    if(error) return error;
    root.autosuspend_disabled=0; h->self.root_hub=&root;
    adds++; live++; h->rh_registered=1; return 0;
}
static void usb_disable_autosuspend(struct usb_device *d) {
    assert(live==1 && d==&root && !d->autosuspend_disabled);
    d->autosuspend_disabled=1; pm_disables++;
}
static void usb_remove_hcd(struct usb_hcd *h) {
    assert(h->rh_registered && live==1);
    removes++; live--; h->rh_registered=0;
}
static int musb_gadget_setup(struct musb *m) {gadget++; return gadget_error;}
static int musb_platform_set_mode(struct musb *m,int mode) {return 0;}
'''
tests = r'''
int main(void) {
    struct usb_hcd h={0}; struct ops ops={MUSB_DMA_SPRD};
    struct musb m={.hcd=&h,.ops=&ops,.port_mode=MUSB_OTG};
    struct platform p={250};
    assert(probe_port(&m,&p)==0 && gadget==1 && adds==0 && live==0);
    musb_host_cleanup(&m); /* Probe rollback / remove while still gadget. */
    for(int i=0;i<5;i++) {
        assert(musb_host_setup(&m,250)==0 && live==1);
        assert(root.autosuspend_disabled && pm_disables==i+1);
        assert(musb_host_setup(&m,250)==0 && adds==i+1); /* Duplicate notification. */
        musb_host_cleanup(&m); musb_host_cleanup(&m);
        assert(live==0 && removes==i+1);
    }
    error=-12;
    assert(musb_host_setup(&m,250)==-12 && !live);
    assert(pm_disables==5); /* Failed registration must not dereference a root. */
    musb_host_cleanup(&m); error=0;
    gadget_error=-5;
    assert(probe_port(&m,&p)==-5 && !live); /* No host to remove on gadget failure. */
    gadget_error=0;
    ops.quirks=0; /* Other platforms retain the generic OTG probe behavior. */
    assert(probe_port(&m,&p)==0 && live==1);
    assert(!root.autosuspend_disabled && pm_disables==5);
    musb_host_cleanup(&m);
    ops.quirks=MUSB_DMA_SPRD; m.port_mode=MUSB_HOST;
    assert(probe_port(&m,&p)==0 && live==1 && root.autosuspend_disabled);
    musb_host_cleanup(&m);
    m.port_mode=MUSB_PERIPHERAL;
    assert(probe_port(&m,&p)==0 && !live); musb_host_cleanup(&m);
    puts("PASS: single root hub, role cycles, SPRD root-only PM, failure cleanup and non-SPRD behavior");
}
'''
with tempfile.TemporaryDirectory(prefix='musb-host-lifecycle-') as tmp:
    path=Path(tmp)
    (path/'test.c').write_text(prelude+cleanup+setup+
        '\nstatic int probe_port(struct musb *musb,struct platform *plat) {\n'
        'int status=0; void *dev=NULL; (void)dev;\n'+probe+'\nfail3: return status;\n}\n'+tests)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
