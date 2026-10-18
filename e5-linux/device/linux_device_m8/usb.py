#!/usr/bin/env python3
"""Connect the M8 USB3 PHY to its PMIC BC1.2 detector and charger manager."""
from pathlib import Path


def apply(kernel):
    kernel = Path(kernel)
    path = kernel / 'drivers/usb/phy/phy-sprd-ums9620-ssphy.c'
    s = path.read_text()
    def replace(old, new):
        nonlocal s
        if new in s:
            return
        if s.count(old) != 1:
            raise ValueError('M8 USB anchor: ' + old[:90])
        s = s.replace(old, new)
    replace('#include <linux/usb/phy.h>', '''#include <linux/usb/phy.h>
#include <linux/usb/sprd_commonphy.h>
#include <linux/power/sprd-bc1p2.h>
#include <linux/extcon.h>
#include <linux/workqueue.h>''')
    replace('\tstruct usb_phy\t\tphy;', '''\tstruct usb_phy\t\tphy;
\t/* Required common-phy prefix: device, usb_phy, operations. */
\tstruct sprd_hsphy_ops ops;
\tstruct sprd_bc1p2_priv bc1p2_info;
\tstruct notifier_block charger_nb;
\tstruct work_struct charger_work;''')
    replace('static inline void sprd_ssphy_reset_core', '''static void sprd_ssphy_dpdm_switch(struct usb_phy *x, bool enable)
{
\tstruct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
\tsc27xx_dpdm_switch_to_phy(phy->pmic, enable);
}

static bool sprd_ssphy_dpdm_get(struct usb_phy *x)
{
\tstruct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
\tu32 value;
\tif (regmap_read(phy->pmic, CHGR_DET_FGU_CTRL, &value))
\t\treturn false;
\treturn (value & (DP_DM_FS_ENB | DP_DM_BC_ENB)) ==
\t\t(DP_DM_FS_ENB | DP_DM_BC_ENB);
}

static void sprd_ssphy_charger_work(struct work_struct *work)
{
\tstruct sprd_ssphy *phy = container_of(work, struct sprd_ssphy, charger_work);
\tbool data = phy->phy.chg_state == USB_CHARGER_PRESENT &&
\t\t(phy->phy.chg_type == SDP_TYPE || phy->phy.chg_type == CDP_TYPE);
\t/* Do not connect D+/D- to the controller until detection completes. */
\tsprd_ssphy_dpdm_switch(&phy->phy, phy->is_host || data);
}

static int sprd_ssphy_charger_notify(struct notifier_block *nb,
\t\t\t\t   unsigned long event, void *data)
{
\tstruct sprd_ssphy *phy = container_of(nb, struct sprd_ssphy, charger_nb);
\tschedule_work(&phy->charger_work);
\treturn NOTIFY_OK;
}

static inline void sprd_ssphy_reset_core''')
    replace('\tdev_info(x->dev, "vbus %s\\n", event ? "on" : "off");', '''\tstruct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);

\tif (phy->is_host)
\t\treturn NOTIFY_OK;
\tsprd_usb_changed(&phy->bc1p2_info,
\t\t\tevent ? USB_CHARGER_PRESENT : USB_CHARGER_ABSENT);
\tdev_info(x->dev, "vbus %s\\n", event ? "on" : "off");''')
    replace('\tsprd_ssphy_vbus_source(dev);\n\tret = usb_add_phy_dev(&phy->phy);\n\tif (ret)\n\t\treturn dev_err_probe(dev, ret, "cannot add phy\\n");\n\n\t/* device mode only for now: route D+/D- from the charger detector to the USB PHY */\n\tsc27xx_dpdm_switch_to_phy(phy->pmic, true);', '''\tphy->phy.charger_detect = sprd_bc1p2_charger_detect;
\tphy->ops.dpdm_switch_to_phy = sprd_ssphy_dpdm_switch;
\tphy->ops.get_dpdm_from_phy = sprd_ssphy_dpdm_get;
\tINIT_WORK(&phy->charger_work, sprd_ssphy_charger_work);
\tphy->charger_nb.notifier_call = sprd_ssphy_charger_notify;
\tret = usb_add_bc1p2_init(&phy->bc1p2_info, &phy->phy);
\tif (ret)
\t\treturn dev_err_probe(dev, ret, "BC1.2 unavailable\\n");
\tsprd_ssphy_vbus_source(dev);
\tret = usb_add_phy_dev(&phy->phy);
\tif (ret) {
\t\tusb_remove_bc1p2(&phy->bc1p2_info);
\t\treturn dev_err_probe(dev, ret, "cannot add phy\\n");
\t}
\tusb_register_notifier(&phy->phy, &phy->charger_nb);
\tsc27xx_dpdm_switch_to_phy(phy->pmic, false);
\tif (!IS_ERR_OR_NULL(phy->phy.edev) &&
\t    extcon_get_state(phy->phy.edev, EXTCON_USB) > 0)
\t\tsprd_usb_changed(&phy->bc1p2_info, USB_CHARGER_PRESENT);''')
    replace('\tusb_remove_phy(&phy->phy);', '''\tusb_unregister_notifier(&phy->phy, &phy->charger_nb);
\tusb_remove_bc1p2(&phy->bc1p2_info);
\tcancel_work_sync(&phy->charger_work);
\tusb_remove_phy(&phy->phy);''')
    path.write_text(s)
    path = kernel / 'drivers/usb/phy/sprd-bc1p2.c'
    s = path.read_text()
    old = '\tbc1p2_info->phy = x;'
    new = '\tif (!bc1p2)\n\t\treturn -EPROBE_DEFER;\n\n' + old
    if new not in s:
        if s.count(old) != 1:
            raise ValueError('BC1.2 initialization anchor')
        path.write_text(s.replace(old, new))
