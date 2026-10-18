"""Preserve USB disconnect edges and respect a peripheral controller's role."""

from pathlib import Path


def apply(kernel, replace_function, restore_board_current=True, charge_profile=None):
    if restore_board_current and charge_profile is None:
        raise ValueError('The device must supply its own charge profile')
    path = kernel / 'drivers/usb/typec/sc27xx_typec.c'
    text = path.read_text()
    if 'sc27xx_typec_controller_mode' not in text:
        helper = r'''
/* Honor the standard dr_mode property only. The vendor's legacy dr-mode
 * spelling is intentionally ignored by MUSB, which needs OTG mode for both
 * peripheral and host operation on this platform.
 */
static int sc27xx_typec_controller_mode(struct device_node *node, int mode)
{
	struct device_node *usb, *extcon;
	const char *role;
	bool linked;

	for_each_node_with_property(usb, "dr_mode") {
		if (!of_device_is_available(usb))
			continue;
		extcon = of_parse_phandle(usb, "extcon", 0);
		linked = extcon == node;
		of_node_put(extcon);
		if (linked && !of_property_read_string(usb, "dr_mode", &role) &&
		    !strcmp(role, "peripheral")) {
			of_node_put(usb);
			return TYPEC_PORT_UFP;
		}
	}
	return mode;
}

'''
        text = text.replace('static int sc27xx_typec_probe(struct platform_device *pdev)',
                            helper + 'static int sc27xx_typec_probe(struct platform_device *pdev)', 1)
        marker = '\tsc->use_pdhub_c2c = of_property_read_bool(node, "use_pdhub_c2c");'
        assert text.count(marker) == 1
        text = text.replace(marker,
            '\tmode = sc27xx_typec_controller_mode(node, mode);\n'
            '\tdev_info(dev, "USB controller policy: Type-C mode %d\\n", mode);\n\n' + marker, 1)
    text = replace_function(text, 'sc27xx_typec_interrupt', r'''
	struct sc27xx_typec *sc = data;
	u32 event, status, dbg1 = 0, dbg2 = 0;
	int ret;

	ret = regmap_read(sc->regmap, sc->base + SC27XX_INT_MASK, &event);
	if (ret)
		return IRQ_NONE;
	event &= sc->var_data->event_mask;
	if (!event)
		return IRQ_NONE;
	/* Acknowledge before notifying consumers: those callbacks can sleep.
	 * Clearing at the end can erase a new edge arriving during disconnect.
	 */
	ret = regmap_write(sc->regmap, sc->base + sc->var_data->int_clr, event);
	if (ret)
		return IRQ_HANDLED;
	ret = regmap_read(sc->regmap, sc->base + SC27XX_STATUS, &status);
	if (ret)
		return IRQ_HANDLED;
	sc->state = status & sc->var_data->state_mask;
	regmap_read(sc->regmap, sc->base + SC27XX_TYPEC_DBG1, &dbg1);
	regmap_read(sc->regmap, sc->base + SC27XX_TYPEC_DBG2, &dbg2);

	if (event & SC27XX_ERR_IN_INT)
		sc27xx_typec_err_recover_state_disen();
	/* Both bits may be latched during a quick unplug/replug. Always retire
	 * the old partner before attaching the new one, using the final state.
	 */
	if (event & (SC27XX_DETACH_INT | SC27XX_ERR_IN_INT)) {
		if (sc->partner_connected)
			sc27xx_typec_disconnect(sc, sc->state);
		sc27xx_typec_connect_state = 0;
		if (event & SC27XX_DETACH_INT)
			sc27xx_typec_random_tdrp(sc);
	}
	if ((event & SC27XX_ATTACH_INT) &&
	    (sc->state == SC27XX_ATTACHED_SNK || sc->state == SC27XX_ATTACHED_SRC ||
	     sc->state == SC27XX_DEBUG_CABLE || sc->state == SC27XX_AUDIO_CABLE)) {
		/* Hardware already debounces CC. Dropping the fifth software event
		 * within 500 ms can leave a real attached cable unreported forever.
		 */
		ret = sc27xx_typec_connect(sc, sc->state);
		sc27xx_typec_connect_state = sc->partner_connected;
		if (ret)
			dev_warn(sc->dev, "failed to register partner: %d\n", ret);
	}
	dev_info(sc->dev, "typec state %d, event %#x, dbg1 %#x, dbg2 %#x\n",
		 sc->state, event, dbg1, dbg2);
	return IRQ_HANDLED;''')
    marker = '\tdev_info(sc->dev, "%s enter\\n", __func__);\n'
    start = text.index('static int sc27xx_typec_reset_rp_rd(void)\n{')
    tail = text[start:]
    if 'Hardware CC needs no artificial disconnect pulse' not in tail:
        tail = tail.replace(marker, marker + r'''
	/* Hardware CC needs no artificial disconnect pulse without a PD policy
	 * engine. A 20 ms forced-open pulse here can disrupt a freshly replugged
	 * USB-C source while we are still handling the preceding detach IRQ.
	 */
	if (!IS_ENABLED(CONFIG_SPRD_TYPEC_TCPM))
		return regmap_update_bits(sc->regmap, sc->base + SC27XX_SW_CFG,
			SC27XX_CC1_SW_SWITCH_MASK | SC27XX_CC2_SW_SWITCH_MASK, 0);
''', 1)
        text = text[:start] + tail
    path.write_text(text)

    path = kernel / 'drivers/power/supply/sprd_battery_info.c'
    text = path.read_text()
    if restore_board_current and '#include "board-charge-profile.h"' not in text:
        marker = 'int sprd_battery_get_battery_info('
        assert text.count(marker) == 1
        text = text.replace(marker, '#include "board-charge-profile.h"\n\n' + marker, 1)
        marker = '\tsprd_battery_parse_step_chg_table(info, battery_np, psy);'
        assert text.count(marker) == 1
        text = text.replace(marker, marker + '\n\n'
            '\tif (board_restore_dcp_profile(info))\n'
            '\t\tdev_info(&psy->dev, "Restored board DCP profile: 3000000 uA; thermal limits retained\\n");', 1)
    path.write_text(text)
    if restore_board_current:
        (path.parent / 'board-charge-profile.h').write_bytes(
            Path(charge_profile).read_bytes())

    path = kernel / 'include/linux/power/sprd-bc1p2.h'
    text = path.read_text()
    if 'disconnect_pending' not in text:
        text = text.replace('\tbool vbus_events;',
            '\tbool vbus_events;\n\tbool disconnect_pending;\n\tu32 vbus_generation;')
    if 'bool host_active;' not in text:
        text = text.replace('\tbool disconnect_pending;',
            '\tbool disconnect_pending;\n\tbool host_active;\n\tbool redetect_after_host;')
        marker = 'extern void sprd_usb_changed('
        assert text.count(marker) == 1
        text = text.replace(marker,
            'extern void sprd_usb_host_changed(struct sprd_bc1p2_priv *info, bool active);\n' + marker, 1)
        text = text.replace('static inline void sprd_usb_changed(',
            'static inline void sprd_usb_host_changed(struct sprd_bc1p2_priv *info, bool active) {}\n'
            'static inline void sprd_usb_changed(', 1)
    path.write_text(text)

    path = kernel / 'drivers/usb/phy/sprd-bc1p2.c'
    text = path.read_text()
    text = replace_function(text, 'sprd_bc1p2_retry_detect', r'''
	enum usb_charger_type type = UNKNOWN_TYPE;
	unsigned int control = 0, status = 0;
	int ret, i, stable = 0;

	/* After boost stops, an external source can take hundreds of ms to
	 * establish VBUS. A REDET pulse before that can strand the analogue
	 * detector at CHGR_INT without DET_DONE, even across further pulses.
	 * Wait for stable external power, then reset the BC1.2 route itself.
	 * This is only used before data enumeration, never on an active link. */
	for (i = 0; i < 40; i++) {
		if (bc1p2->shutdown || x->last_event == USB_EVENT_ID)
			return UNKNOWN_TYPE;
		stable = sprd_bc1p2_vchg_is_present(&control, &status) ? stable + 1 : 0;
		if (stable >= 5)
			break;
		msleep(SPRD_CHG_DET_POLL_DELAY);
	}
	if (stable < 5)
		return UNKNOWN_TYPE;

	ret = sprd_bc1p2_redetect_control(false);
	if (ret)
		return UNKNOWN_TYPE;
	/* DP_DM_BC_ENB is active low on all PMICs supporting redetection. */
	ret = regmap_update_bits(bc1p2->regmap, bc1p2->data->chg_det_fgu_ctrl, BIT(0), BIT(0));
	if (ret)
		return UNKNOWN_TYPE;
	msleep(SPRD_CHG_DET_POLL_DELAY);
	if (bc1p2->shutdown || x->last_event == USB_EVENT_ID)
		return UNKNOWN_TYPE;
	ret = regmap_update_bits(bc1p2->regmap, bc1p2->data->chg_det_fgu_ctrl, BIT(0), 0);
	if (!ret) {
		bc1p2->chg_redet_poll_count = 0;
		type = sprd_bc1p2_detect();
	}
	dev_info(x->dev, "bc1p2:stable-power restart result %d\n", type);
	return type;''')
    # The old REDET-only helper is no longer used. Keep the public retry entry
    # point, with the same bounded retry policy in the caller.
    start = text.find('static int sprd_bc1p2_redetect_trigger(')
    if start >= 0:
        end = text.index('\nenum usb_charger_type sprd_bc1p2_charger_detect(', start)
        text = text[:start] + text[end + 1:]
    text = replace_function(text, 'sprd_usb_changed', r'''
	struct usb_phy *usb_phy = bc1p2_info->phy;
	unsigned long flags;

	if (!bc1p2_info->bc1p2 || bc1p2_info->bc1p2->shutdown)
		return;
	spin_lock_irqsave(&bc1p2_info->vbus_event_lock, flags);
	bc1p2_info->vbus_events = true;
	bc1p2_info->vbus_generation++;
	if (state == USB_CHARGER_ABSENT)
		bc1p2_info->disconnect_pending = true;
	usb_phy->chg_state = state;
	spin_unlock_irqrestore(&bc1p2_info->vbus_event_lock, flags);
	if (bc1p2_info->bc1p2_thread)
		kthread_queue_delayed_work(&bc1p2_info->bc1p2_kworker,
					   &bc1p2_info->usb_change_kwork, 0);''')
    text = replace_function(text, 'sprd_usb_change_work', r'''
	struct sprd_bc1p2_priv *info = container_of(work, struct sprd_bc1p2_priv,
						 usb_change_kwork.work);
	struct sprd_bc1p2 *bc = info->bc1p2;
	struct usb_phy *phy = info->phy;
	unsigned long flags;
	bool detached;

	for (;;) {
		spin_lock_irqsave(&info->vbus_event_lock, flags);
		if (!info->vbus_events) {
			spin_unlock_irqrestore(&info->vbus_event_lock, flags);
			break;
		}
		info->vbus_events = false;
		detached = info->disconnect_pending;
		info->disconnect_pending = false;
		spin_unlock_irqrestore(&info->vbus_event_lock, flags);
		if (info->bc1p2_thread)
			kthread_cancel_delayed_work_sync(&info->bc1p2_kwork);
		/* The latest level may already be PRESENT. Keep the intervening
		 * disconnect edge so the old cable's SDP/DCP result is never reused.
		 */
		if (detached || (!READ_ONCE(info->host_active) && READ_ONCE(info->redetect_after_host))) {
			mutex_lock(&bc->bc1p2_lock);
			phy->chg_type = UNKNOWN_TYPE;
			phy->flags &= ~CHARGER_DETECT_DONE;
			usb_phy_set_default_current(phy);
			bc->type = UNKNOWN_TYPE;
			bc->detect_state = CHG_STATE_UNDETECT;
			bc->retry_chg_detect_count = 0;
			bc->chg_redet_poll_count = 0;
			info->rework = false;
			mutex_unlock(&bc->bc1p2_lock);
		}
		if (!READ_ONCE(info->host_active) || phy->chg_state == USB_CHARGER_ABSENT)
			kthread_queue_delayed_work(&info->bc1p2_kworker, &info->bc1p2_kwork, 0);
	}''')
    start = text.index('static void sprd_get_bc1p2_type_work(')
    end = text.index('\nstatic void sprd_usb_change_work(', start)
    body = text[start:end]
    if 'generation = READ_ONCE' not in body:
        body = body.replace('\tif (!bc1p2 || !x->charger_detect)',
            '\tu32 generation = READ_ONCE(bc1p2_info->vbus_generation);\n\n'
            '\tif (!bc1p2 || !x->charger_detect)', 1)
        body = body.replace('\n\t\tif (bc1p2_info->bc1p2_thread && bc1p2_info->rework)',
            '\n\t\t/* A detect may sleep while the physical cable changes. */\n'
            '\t\tif (generation != READ_ONCE(bc1p2_info->vbus_generation))\n'
            '\t\t\treturn;\n\n'
            '\t\tif (bc1p2_info->bc1p2_thread && bc1p2_info->rework)', 1)
        text = text[:start] + body + text[end:]
    if 'Host pull-downs are not a charger signature' not in text:
        marker = '\tcase USB_CHARGER_PRESENT:\n\t\tmutex_lock(&bc1p2->bc1p2_lock);'
        assert text.count(marker) == 1
        text = text.replace(marker,
            '\tcase USB_CHARGER_PRESENT:\n'
            '\t\t/* Host pull-downs are not a charger signature. Host teardown\n'
            '\t\t * queues a fresh work item; there is no periodic retry here. */\n'
            '\t\tif (READ_ONCE(bc1p2_info->host_active))\n\t\t\treturn;\n'
            '\t\tmutex_lock(&bc1p2->bc1p2_lock);', 1)
    if 'xchg(&bc1p2_info->redetect_after_host' not in text:
        marker = '\t\tbc1p2->type = sprd_bc1p2_detect();'
        assert text.count(marker) == 1
        text = text.replace(marker,
            '\t\t/* Discard the hardware result latched while OTG drove D+/D-. */\n'
            '\t\tif (xchg(&bc1p2_info->redetect_after_host, false) && bc1p2->redetect_enable)\n'
            '\t\t\tbc1p2->type = sprd_bc1p2_retry_detect(x);\n'
            '\t\telse\n\t\t\tbc1p2->type = sprd_bc1p2_detect();', 1)
    if '#include "board-usb-charge-role.h"' not in text:
        marker = 'EXPORT_SYMBOL_GPL(sprd_usb_changed);'
        text = text.replace(marker, marker + '\n\n#include "board-usb-charge-role.h"', 1)
    path.write_text(text)
    (path.parent / 'board-usb-charge-role.h').write_bytes(
        Path(__file__).with_name('usb-charge-role.h').read_bytes())

    path = kernel / 'drivers/usb/phy/phy-sprd-qogirn6lite.c'
    text = path.read_text()
    if 'sprd_usb_host_changed' not in text:
        text = text.replace('\t\tphy->is_host = true;',
            '\t\tphy->is_host = true;\n\t\tsprd_usb_host_changed(&phy->bc1p2_info, true);', 1)
        text = text.replace('\t\tphy->is_host = false;',
            '\t\tphy->is_host = false;\n\t\tsprd_usb_host_changed(&phy->bc1p2_info, false);', 1)
    path.write_text(text)

    path = kernel / 'drivers/usb/musb/musb_sprd.c'
    text = path.read_text()
    if 'Stop hosting before waiting for BC1.2' not in text:
        marker = '\tswitch (glue->chg_state) {'
        assert text.count(marker) == 1
        text = text.replace(marker, r'''
	/* Stop hosting before waiting for BC1.2: both works share one ordered
	 * queue, so waiting here would prevent the host teardown we need. */
	if (glue->id_state == MUSB_ID_FLOAT &&
	    (glue->drd_state == DRD_STATE_HOST || glue->drd_state == DRD_STATE_HOST_IDLE)) {
		queue_work(glue->musb_wq, &glue->resume_work);
		queue_delayed_work(glue->sm_usb_wq, &glue->chg_detect_work, msecs_to_jiffies(20));
		return;
	}
''' + marker, 1)
        marker = '\t\t/* Decrement pm usage count when leave host state.*/'
        assert text.count(marker) == 1
        text = text.replace(marker,
            '\t\t/* Boost and the DP/DM mux are off; release host pull-downs\n'
            '\t\t * before allowing a pending sink BC1.2 measurement. */\n'
            '\t\tusb_phy_vbus_off(glue->xceiv);\n\n' + marker, 1)
        marker = '\tif (glue->vbus_active && !glue->in_restart)'
        assert text.count(marker) == 1
        text = text.replace(marker,
            '\t/* A sink may power the port before its data role is known. */\n'
            '\tif (glue->vbus_active && !glue->in_restart && !glue->charging_mode &&\n'
            '\t    (glue->chg_state == USB_CHG_STATE_DETECTED ||\n'
            '\t     glue->chg_state == USB_CHG_STATE_RETRY_DETECTED))', 1)
        start = text.index('static void musb_sprd_resume_work(')
        end = text.index('\n/**', start)
        body = text[start:end]
        marker = '\tif (glue->vbus_active) {'
        assert body.count(marker) == 1
        body = body.replace(marker, r'''
	/* An old host must shut down even while the new sink is being detected. */
	if (glue->id_state == MUSB_ID_FLOAT &&
	    (glue->drd_state == DRD_STATE_HOST || glue->drd_state == DRD_STATE_HOST_IDLE)) {
		musb_sprd_ext_event_notify(glue);
		return;
	}
''' + marker, 1)
        text = text[:start] + body + text[end:]
    path.write_text(text)
