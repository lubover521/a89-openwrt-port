/* SPDX-License-Identifier: GPL-2.0-only */
/* QogirN6Pro legacy DT: Type-C and boost supply belong to the glue node.
 * The real combined PHY is usb-phy[1]; usb-phy[0] is only a dummy.
 */
#include <linux/extcon.h>
#include <linux/regulator/consumer.h>
#include <linux/usb/otg.h>
#include <linux/usb/role.h>
#include "core.h"

struct sprd_dwc3_role {
	struct device *dev;
	struct extcon_dev *extcon;
	struct regulator *vbus;
	struct usb_phy *phy;
	struct device_node *child;
	struct usb_role_switch *sw;
	struct notifier_block nb;
	struct delayed_work work;
	unsigned int retries;
	bool enabled, registered, stopped;
};

static bool sprd_dwc3_wants_host(struct sprd_dwc3_role *r)
{
	/* Never source into a reported sink connection. */
	return extcon_get_state(r->extcon, EXTCON_USB_HOST) > 0 &&
	       extcon_get_state(r->extcon, EXTCON_USB) == 0;
}

static void sprd_dwc3_role_work(struct work_struct *work)
{
	struct sprd_dwc3_role *r = container_of(to_delayed_work(work),
						struct sprd_dwc3_role, work);
	struct platform_device *child;
	struct dwc3 *dwc;
	bool host;
	int ret;

	if (READ_ONCE(r->stopped))
		return;
	if (!r->sw) {
		r->sw = usb_role_switch_find_by_fwnode(of_fwnode_handle(r->child));
		if (IS_ERR_OR_NULL(r->sw)) {
			r->sw = NULL;
			if (++r->retries < 100)
				mod_delayed_work(system_wq, &r->work, msecs_to_jiffies(100));
			else
				dev_err(r->dev, "Type-C: child role switch unavailable\n");
			return;
		}
	}
	child = of_find_device_by_node(r->child);
	if (!child)
		return;
	dwc = platform_get_drvdata(child);
	if (!dwc)
		goto out;
	host = sprd_dwc3_wants_host(r);
	if (host == r->enabled && usb_role_switch_get_role(r->sw) ==
	    (host ? USB_ROLE_HOST : USB_ROLE_DEVICE))
		goto out;

	if (!host && r->enabled) {
		ret = regulator_disable(r->vbus);
		if (ret)
			goto fail;
		r->enabled = false;
		/* Let our own VBUS fall before the PHY samples external power. */
		msleep(50);
	}
	ret = otg_set_vbus(r->phy->otg, host);
	if (ret)
		goto fail;
	ret = usb_role_switch_set_role(r->sw, host ? USB_ROLE_HOST : USB_ROLE_DEVICE);
	if (ret)
		goto fail;
	/* DWC3's setter queues work. Finish the controller transition before
	 * enabling boost, and re-read CC after this potentially sleeping step.
	 */
	flush_work(&dwc->drd_work);
	if (host) {
		if (!sprd_dwc3_wants_host(r)) {
			mod_delayed_work(system_wq, &r->work, 0);
			goto out;
		}
		if (!dwc->xhci) {
			ret = -ENODEV;
			goto fail;
		}
		ret = regulator_enable(r->vbus);
		if (ret)
			goto fail;
		r->enabled = true;
	}
	dev_info(r->dev, "Type-C role=%s boost=%d\n", host ? "host" : "device", r->enabled);
	goto out;
fail:
	dev_err(r->dev, "Type-C transition failed: %d\n", ret);
	if (host && !r->enabled) {
		otg_set_vbus(r->phy->otg, false);
		usb_role_switch_set_role(r->sw, USB_ROLE_DEVICE);
		flush_work(&dwc->drd_work);
	}
out:
	put_device(&child->dev);
}

static int sprd_dwc3_role_notify(struct notifier_block *nb,
				unsigned long event, void *data)
{
	struct sprd_dwc3_role *r = container_of(nb, struct sprd_dwc3_role, nb);
	if (!READ_ONCE(r->stopped))
		mod_delayed_work(system_wq, &r->work, 0);
	return NOTIFY_OK;
}

static void sprd_dwc3_role_stop(void *data)
{
	struct sprd_dwc3_role *r = data;
	if (!r || r->stopped)
		return;
	WRITE_ONCE(r->stopped, true);
	if (r->registered)
		extcon_unregister_notifier_all(r->extcon, &r->nb);
	cancel_delayed_work_sync(&r->work);
	if (r->enabled)
		regulator_disable(r->vbus);
	usb_role_switch_put(r->sw);
	of_node_put(r->child);
}

static struct sprd_dwc3_role *sprd_dwc3_role_prepare(struct device *dev)
{
	struct sprd_dwc3_role *r;
	struct device_node *np;
	int ret, index;
	if (!of_device_is_compatible(dev->of_node, "sprd,qogirn6pro-dwc3"))
		return NULL;
	r = devm_kzalloc(dev, sizeof(*r), GFP_KERNEL);
	if (!r)
		return ERR_PTR(-ENOMEM);
	r->dev = dev;
	/* M8 orders these as VBUS GPIO, then Type-C. Select by provider,
	 * not by position: GPIO tells us voltage, never the host CC role.
	 */
	for (index = 0; ; index++) {
		bool typec;
		np = of_parse_phandle(dev->of_node, "extcon", index);
		if (!np)
			return ERR_PTR(-ENODEV);
		typec = of_device_is_compatible(np, "sprd,sc27xx-typec") ||
			of_device_is_compatible(np, "sprd,ump96xx-typec");
		of_node_put(np);
		if (typec)
			break;
	}
	r->extcon = extcon_get_edev_by_phandle(dev, index);
	if (IS_ERR(r->extcon))
		return ERR_CAST(r->extcon);
	/* Require the actual DT supply; a dummy regulator cannot power OTG. */
	r->vbus = devm_regulator_get_optional(dev, "vbus");
	if (IS_ERR(r->vbus))
		return ERR_CAST(r->vbus);
	r->phy = devm_usb_get_phy_by_phandle(dev, "usb-phy", 1);
	if (IS_ERR(r->phy))
		return ERR_CAST(r->phy);
	for_each_available_child_of_node(dev->of_node, np) {
		if (of_device_is_compatible(np, "snps,sprd-dwc3") ||
		    of_device_is_compatible(np, "snps,dwc3")) {
			r->child = np;
			break;
		}
	}
	if (!r->child)
		return ERR_PTR(-ENODEV);
	dev_info(dev, "Type-C provider extcon %d, real PHY usb-phy[1]\n", index);
	INIT_DELAYED_WORK(&r->work, sprd_dwc3_role_work);
	r->nb.notifier_call = sprd_dwc3_role_notify;
	ret = devm_add_action_or_reset(dev, sprd_dwc3_role_stop, r);
	return ret ? ERR_PTR(ret) : r;
}

static int sprd_dwc3_role_start(struct sprd_dwc3_role *r)
{
	int ret;
	if (!r)
		return 0;
	ret = extcon_register_notifier_all(r->extcon, &r->nb);
	if (ret)
		return ret;
	r->registered = true;
	mod_delayed_work(system_wq, &r->work, 0);
	return 0;
}
