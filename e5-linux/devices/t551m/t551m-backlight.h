/* SPDX-License-Identifier: GPL-2.0-only */
/* T551M's 16-step GPIO backlight, matching the factory pulse interface.
 * Included by sprd_bl.c so DPU/CABC retain the shared sprd_backlight layout.
 */
#include <linux/gpio/consumer.h>
#include <linux/delay.h>

static int t551m_backlight_update(struct backlight_device *bd)
{
	struct sprd_backlight *bl = bl_get_data(bd);
	unsigned long flags;
	u16 level;
	unsigned int i, pulses;

	sprd_backlight_normalize_map(bd, &level);
	if (backlight_is_blank(bd))
		level = 0;
	if (level > 16)
		return -EINVAL;
	if (bl->step_level == level)
		return 0;
	if (!level) {
		gpiod_set_value(bl->step_gpio, 0);
		bl->step_level = 0;
		return 0;
	}
	if (bl->step_level <= 0) {
		/* Initialize once, or after blanking. Do not trust LK's counter. */
		gpiod_set_value(bl->step_gpio, 0);
		msleep(50);
		pulses = level;
	} else {
		/* The factory driver advances a wrapping 16-step counter. Keeping
		 * it enabled avoids a visible 50 ms blackout on every slider step.
		 */
		pulses = (level + 16 - bl->step_level) % 16;
	}
	/* update_status is serialized by the backlight core's update_lock. */
	local_irq_save(flags);
	for (i = 0; i < pulses; i++) {
		udelay(100);
		gpiod_set_value(bl->step_gpio, 0);
		udelay(100);
		gpiod_set_value(bl->step_gpio, 1);
	}
	local_irq_restore(flags);
	bl->step_level = level;
	return 0;
}
