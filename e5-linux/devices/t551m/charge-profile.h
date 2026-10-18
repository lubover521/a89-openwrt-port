/* SPDX-License-Identifier: GPL-2.0-only */
/* Included only by this board's kernel preparation. The user's modified A-slot
 * profile and B-slot profile differ in their normal DCP current. Restore
 * the reviewed DCP profile only when the complete old profile matches.
 */
static bool board_restore_dcp_profile(struct sprd_battery_info *info)
{
	static const struct sprd_battery_jeita_table old_table[] = {
		{ 0, 0, 0, 4400000 },
		{ 100, 100, 580000, 4400000 },
		{ 450, 450, 1000000, 4400000 },
		{ 550, 500, 1000000, 4100000 },
	};
	struct sprd_battery_jeita_table *table = info->jeita_table[SPRD_BATTERY_JEITA_DCP];
	unsigned int i;

	if (info->charge_full_design_uah != 3832000 ||
	    info->constant_charge_voltage_max_uv != 4400000 ||
	    info->voltage_min_design_uv != 3456000 ||
	    info->cur.dcp_cur != 1000000 || info->cur.dcp_limit != 1000000 ||
	    info->sprd_battery_jeita_size[SPRD_BATTERY_JEITA_DCP] != ARRAY_SIZE(old_table) || !table)
		return false;
	for (i = 0; i < ARRAY_SIZE(old_table); i++) {
		if (table[i].temp != old_table[i].temp ||
		    table[i].recovery_temp != old_table[i].recovery_temp ||
		    table[i].current_ua != old_table[i].current_ua ||
		    table[i].term_volt != old_table[i].term_volt)
			return false;
	}
	/* Leave SDP, CDP, unknown sources, cold/warm limits and all voltages alone. */
	info->cur.dcp_cur = 3000000;
	info->cur.dcp_limit = 3000000;
	table[2].current_ua = 3000000;
	info->max_current_jeita_index[SPRD_BATTERY_JEITA_DCP] = 2;
	return true;
}
