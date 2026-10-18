/* SPDX-License-Identifier: GPL-2.0-only */
/* Manual CC policy; VBUS is enabled only after a real source attachment. */
static int sc27xx_typec_set_policy(struct sc27xx_typec *sc, int mode)
{
	u32 mask = SC27XX_CC1_SW_SWITCH_MASK | SC27XX_CC2_SW_SWITCH_MASK;
	u32 open = SC27XX_CC1_SW_SWITCH(SC27XX_TYPEC_NC) |
		   SC27XX_CC2_SW_SWITCH(SC27XX_TYPEC_NC);
	u32 hw;
	int ret, restore, old;

	if (IS_ENABLED(CONFIG_SPRD_TYPEC_TCPM))
		return -EOPNOTSUPP;
	switch (mode) {
	case TYPEC_PORT_UFP: hw = SC27XX_MODE_SNK; break;
	case TYPEC_PORT_DFP: hw = SC27XX_MODE_SRC; break;
	case TYPEC_PORT_DRP: hw = SC27XX_MODE_DRP; break;
	default: return -EINVAL;
	}
	mutex_lock(&sc->role_lock);
	old = sc->mode;
	if (old == mode) {
		ret = 0;
		goto out;
	}
	sc27xx_typec_role_finish(sc);
	if (sc->partner_connected)
		sc27xx_typec_disconnect(sc, sc->state);
	sc27xx_typec_connect_state = 0;
	/* An explicit policy change requires a fresh CC negotiation. This pulse
	 * is never used on the normal plug/unplug path. Do not force an extcon
	 * Host event or bypass the source's detection of a real sink accessory.
	 */
	ret = regmap_update_bits(sc->regmap, sc->base + SC27XX_SW_CFG, mask, open);
	if (!ret)
		ret = sc27xx_typec_hw_mode(sc, hw);
	if (!ret) {
		sc->mode = mode;
		msleep(30);
	} else {
		sc27xx_typec_hw_mode(sc, old == TYPEC_PORT_UFP ? SC27XX_MODE_SNK :
				    old == TYPEC_PORT_DFP ? SC27XX_MODE_SRC : SC27XX_MODE_DRP);
	}
	restore = regmap_update_bits(sc->regmap, sc->base + SC27XX_SW_CFG, mask, 0);
	if (!ret)
		ret = restore;
out:
	mutex_unlock(&sc->role_lock);
	return ret;
}

static ssize_t usb_role_policy_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct sc27xx_typec *sc = dev_get_drvdata(dev);
	int mode;
	if (!sc)
		return -EAGAIN;
	mode = READ_ONCE(sc->mode);
	return sysfs_emit(buf, "%s\n", mode == TYPEC_PORT_UFP ? "device" :
			  mode == TYPEC_PORT_DFP ? "host" : "auto");
}

static ssize_t usb_role_policy_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct sc27xx_typec *sc = dev_get_drvdata(dev);
	int mode, ret;
	if (!sc)
		return -EAGAIN;
	if (sysfs_streq(buf, "device"))
		mode = TYPEC_PORT_UFP;
	else if (sysfs_streq(buf, "host"))
		mode = TYPEC_PORT_DFP;
	else if (sysfs_streq(buf, "auto"))
		mode = TYPEC_PORT_DRP;
	else
		return -EINVAL;
	ret = sc27xx_typec_set_policy(sc, mode);
	return ret ? ret : count;
}
static DEVICE_ATTR_RW(usb_role_policy);

static ssize_t usb_role_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct sc27xx_typec *sc = dev_get_drvdata(dev);
	if (!sc)
		return -EAGAIN;
	return sysfs_emit(buf, "%s\n", extcon_get_state(sc->edev, EXTCON_USB_HOST) > 0 ?
		"host" : extcon_get_state(sc->edev, EXTCON_USB) > 0 ? "device" : "none");
}
static DEVICE_ATTR_RO(usb_role);
