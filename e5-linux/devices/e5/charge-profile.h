/* SPDX-License-Identifier: GPL-2.0-only */
/* Match the complete native E5 battery profile before changing its DCP row.
 * 3 A is the input policy budget, not an independently regulated AW32257 limit.
 * Battery current stays within the datasheet's 2.48 A at the board's 33 mOhm.
 */
static bool e5_dcp_profile(struct sprd_battery_info *info)
{
	static const struct sprd_battery_jeita_table original[] = {
		{ 0, 0, 0, 4340000 }, { 150, 150, 650000, 4340000 },
		{ 450, 450, 1650000, 4370000 }, { 550, 550, 650000, 4340000 }
	};
	struct sprd_battery_jeita_table *t = info->jeita_table[SPRD_BATTERY_JEITA_DCP];
	unsigned int i;
	if (info->charge_full_design_uah != 3082000 ||
	    info->constant_charge_voltage_max_uv != 4370000 ||
	    info->voltage_min_design_uv != 3433000 ||
	    info->cur.dcp_cur != 1650000 || info->cur.dcp_limit != 1650000 ||
	    !t || info->sprd_battery_jeita_size[SPRD_BATTERY_JEITA_DCP] != ARRAY_SIZE(original))
		return false;
	for (i = 0; i < ARRAY_SIZE(original); i++)
		if (t[i].temp != original[i].temp || t[i].recovery_temp != original[i].recovery_temp ||
		    t[i].current_ua != original[i].current_ua || t[i].term_volt != original[i].term_volt)
			return false;
	info->cur.dcp_cur = 2480000;
	info->cur.dcp_limit = 3000000;
	t[2].current_ua = 2480000;
	info->max_current_jeita_index[SPRD_BATTERY_JEITA_DCP] = 2;
	return true;
}
