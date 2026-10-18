/* SPDX-License-Identifier: GPL-2.0-only */
/* Called after PHY host setup/teardown, never while holding the PHY registers.
 * A sink edge can arrive before the MUSB worker has removed its host pull-downs
 * and boost supply. Keep BC1.2 quiescent until that teardown is complete.
 */
void sprd_usb_host_changed(struct sprd_bc1p2_priv *info, bool active)
{
	unsigned long flags;

	if (!info->bc1p2 || info->bc1p2->shutdown)
		return;
	spin_lock_irqsave(&info->vbus_event_lock, flags);
	info->host_active = active;
	if (active)
		info->redetect_after_host = true;
	info->vbus_events = true;
	info->vbus_generation++;
	spin_unlock_irqrestore(&info->vbus_event_lock, flags);
	if (info->bc1p2_thread)
		kthread_queue_delayed_work(&info->bc1p2_kworker,
					   &info->usb_change_kwork, 0);
}
EXPORT_SYMBOL_GPL(sprd_usb_host_changed);
