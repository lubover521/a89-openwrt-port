"""Correct E5 AW32257 current encoding without borrowing the T551M charger."""
from pathlib import Path


def apply(kernel, replace_function):
    here = Path(__file__).resolve().parent
    path = kernel / 'drivers/power/supply/aw32257_charger.c'
    text = path.read_text()
    if 'e5-aw32257-current-v1' in text:
        return
    text = text.replace('struct aw32257_device {',
        'struct aw32257_device {\n\t/* e5-aw32257-current-v1: software budgets; REG01 has no IINLIM. */\n'
        '\tint requested_charge_ua;\n\tint input_budget_ua;')
    anchor = '/* set current limit in mA */'
    text = text.replace(anchor, '#include "e5-charger-current.h"\n'
        'static int aw32257_set_charge_current(struct aw32257_device *bq, int uA);\n\n' + anchor, 1)
    text = replace_function(text, 'aw32257_set_current_limit', '''
	int old = bq->input_budget_ua, ret;
	if (uA < 0) return -EINVAL;
	/* Honor charger-manager's input vote conservatively through IBAT.
	 * This is a policy budget, not a hardware input-current measurement. */
	bq->input_budget_ua = min(uA, 3000000);
	ret = aw32257_set_charge_current(bq, bq->requested_charge_ua);
	if (ret) bq->input_budget_ua = old;
	return ret;''')
    text = replace_function(text, 'aw32257_get_current_limit', '''
	return bq->input_budget_ua / 1000;''')
    text = replace_function(text, 'aw32257_set_charge_current', '''
	int code, ret, requested = uA;
	if (uA < 0 || bq->init_data.resistor_sense <= 0) return -EINVAL;
	uA = min(uA, bq->input_budget_ua);
	code = aw32257_current_code(uA, bq->init_data.resistor_sense);
	if (code == -ERANGE) {
		ret = aw32257_exec_command(bq, AW32257_CHARGER_DISABLE);
		if (!ret) { bq->requested_charge_ua = requested; bq->charging = false; }
		return ret;
	}
	if (code < 0) return code;
	ret = aw32257_i2c_write_mask(bq, AW32257_REG_CURRENT, code,
		AW32257_MASK_VI_CHRG | AW32257_MASK_RESET, AW32257_SHIFT_VI_CHRG);
	if (!ret) bq->requested_charge_ua = requested;
	return ret;''')
    text = replace_function(text, 'aw32257_get_charge_current', '''
	int code = aw32257_i2c_read_mask(bq, AW32257_REG_CURRENT,
		AW32257_MASK_VI_CHRG, AW32257_SHIFT_VI_CHRG);
	if (code < 0) return code;
	return aw32257_current_ua(code, bq->init_data.resistor_sense) / 1000;''')
    # Restore only the actual boost bits; the old full-register literals erased
    # voltage/termination settings every time a host cable was removed.
    old = '\t\taw32257_i2c_write_mask(bq, 0x01, 0x30, 0xff, 0x00);\n\t\taw32257_i2c_write_mask(bq, 0x02, 0x8e, 0xff, 0x00);'
    if text.count(old) != 1:
        raise ValueError('Unexpected AW32257 OTG disable sequence')
    text = text.replace(old, '\t\taw32257_set_otg_en(bq, 0);\n\t\taw32257_set_opa_mode(bq, 0);')
    text = text.replace('cfg.dev = info->dev;', 'cfg.dev = info->dev;\n\tcfg.of_node = info->dev->of_node;', 1)
    # Initialize before charger-manager can send votes via the power supply.
    anchor = '\tbq->charger = devm_power_supply_register('
    text = text.replace(anchor,
        '\tbq->requested_charge_ua = 496000;\n\tbq->input_budget_ua = 500000;\n' + anchor, 1)
    # Keep the existing start path, but apply the current vote before enabling.
    start = text.index('static int aw32257_charger_start_charge(')
    end = text.index('\nstatic void aw32257_charger_stop_charge', start)
    body = text[start:end].replace('\tint ret;', '''\tint ret;
	if (aw32257_current_code(min(info->requested_charge_ua, info->input_budget_ua),
		info->init_data.resistor_sense) < 0) return -ERANGE;
	ret = aw32257_set_charge_current(info, info->requested_charge_ua);
	if (ret) return ret;''', 1)
    text = text[:start] + body + text[end:]
    start = text.index('static int aw32257_property_is_writeable(')
    end = text.index('static int aw32257_power_supply_set_property(', start)
    body = text[start:end].replace('\tswitch (psp) {',
        '\tswitch (psp) {\n\tcase POWER_SUPPLY_PROP_CALIBRATE:\n\tcase POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:', 1)
    text = text[:start] + body + text[end:]
    # Expose charger-manager's previously missing IBUS vote setter.
    start = text.index('static int aw32257_power_supply_set_property(')
    end = text.index('static int aw32257_power_supply_get_property(', start)
    body = text[start:end].replace('\tswitch (psp) {',
        '\tswitch (psp) {\n\tcase POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:\n'
        '\t\tret = aw32257_set_current_limit(bq, val->intval);\n\t\tbreak;', 1)
    body = body.replace('\tcase POWER_SUPPLY_PROP_STATUS:',
                        '\tcase POWER_SUPPLY_PROP_CALIBRATE:\n\tcase POWER_SUPPLY_PROP_STATUS:', 1)
    text = text[:start] + body + text[end:]
    start = text.index('static int aw32257_power_supply_get_property(')
    end = text.index('\n/****', start)
    body = text[start:end]
    body = body.replace('\tcase POWER_SUPPLY_PROP_STATUS:',
        '\tcase POWER_SUPPLY_PROP_CALIBRATE:\n\t\tval->intval = bq->charging;\n\t\tbreak;\n\tcase POWER_SUPPLY_PROP_STATUS:', 1)
    body = body.replace('\t\t\tcur = aw32257_get_charge_current(bq);',
                        '\t\t\tcur = aw32257_get_charge_current(bq);\n\t\t\tif (cur < 0) return cur;')
    first = body.index('\tcase POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:')
    last = body.index('\tcase POWER_SUPPLY_PROP_ONLINE:', first)
    body = body[:first] + '\tcase POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:\n\t\tval->intval = bq->input_budget_ua;\n\t\tbreak;\n' + body[last:]
    text = text[:start] + body + text[end:]
    # The inherited BQ part-name decoder mislabels the verified 0x53 device.
    text = text.replace('val->strval = bq->model;', 'val->strval = "AW32257";', 1)
    path.write_text(text)
    (path.parent / 'e5-charger-current.h').write_bytes((here / 'charger-current.h').read_bytes())
    path = kernel / 'drivers/power/supply/sprd_battery_info.c'
    text = path.read_text()
    if '#include "e5-charge-profile.h"' not in text:
        text = text.replace('int sprd_battery_get_battery_info(',
            '#include "e5-charge-profile.h"\n\nint sprd_battery_get_battery_info(', 1)
        anchor = '\tsprd_battery_parse_step_chg_table(info, battery_np, psy);'
        if text.count(anchor) != 1:
            raise ValueError('Unexpected E5 battery profile loader')
        text = text.replace(anchor, anchor + '\n\tif (e5_dcp_profile(info))\n'
            '\t\tdev_info(&psy->dev, "E5 DCP: 3A input policy, 2.48A maximum battery charge; JEITA retained\\n");')
        path.write_text(text)
    (path.parent / 'e5-charge-profile.h').write_bytes((here / 'charge-profile.h').read_bytes())
