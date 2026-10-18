"""Shared source editing and verified A6 charger register helpers."""
import re

def replace_function(source, name, body):
    match = re.search(r'\b' + name + r'\([^;{}]*\)\s*\{', source)
    if not match:
        raise ValueError('Missing function: ' + name)
    start = source.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[:start] + '{\n' + body + '\n}' + source[end:]

def board_charger(source):
    # This unit reports REG0B=0x12. Its stock driver (dumped for inspection,
    # never redistributed) uses the A6 piecewise current encoding. Do not use
    # the upstream TI/SGM 60 mA encoding for this board.
    source = source.replace('.name\t\t\t= "charger",', '.name\t\t\t= "bq2560x_charger",')
    source = source.replace('#define BQ2560X_REG_NUM\t\t\t\t0x10', '#define BQ2560X_REG_NUM\t\t\t\t0x0c')
    source = source.replace('val->intval = info->chip_type;',
                            '{ u8 status; ret = bq2560x_read(info, BQ2560X_REG_8, &status);\n\t\t\tif (!ret) val->intval = !!(status & BIT(2)); }')
    bodies = {
        'bq2560x_charger_set_vindpm': '''
\tu8 code = (clamp_val(vol, 3900, 5400) - 3900) / 100;
\treturn bq2560x_update_bits(info, BQ2560X_REG_6,
\t\tBQ2560X_REG_VINDPM_VOLTAGE_MASK, code);''',
        'bq2560x_charger_get_termina_vol': '''
\tu8 value;
\tint ret = bq2560x_read(info, BQ2560X_REG_4, &value);
\tif (ret < 0) return ret;
\t*vol = ((value >> 3) & 0x1f) * 32 + 3856;
\treturn 0;''',
        'bq2560x_charger_set_termina_vol': '''
\t/* The factory battery/JEITA tables request up to 4.4 V. */
\tu8 code = (clamp_val(vol, 3856, 4400) - 3856) / 32;
\treturn bq2560x_update_bits(info, BQ2560X_REG_4,
\t\tBQ2560X_REG_TERMINAL_VOLTAGE_MASK, code << 3);''',
        'bq2560x_charger_set_current': '''
\t/* Factory REG0B=0x12 path: <=1170 mA uses 90 mA steps;
\t * the upper range uses the stock (mA - 805) / 57 + 14 mapping.
\t * 3047 mA is the original setter's ceiling (code 53).
\t */
\tu32 ma = min(cur / 1000, 3047U);
\tu8 code = ma <= 1170 ? ma / 90 : (ma - 805) / 57 + 14;
\treturn bq2560x_update_bits(info, BQ2560X_REG_2,
\t\tBQ2560X_REG_ICHG_MASK, code);''',
        'bq2560x_charger_get_current': '''
\tu8 value;
\tint ret = bq2560x_read(info, BQ2560X_REG_2, &value);
\tif (ret < 0) return ret;
\tvalue &= BQ2560X_REG_ICHG_MASK;
\t/* Preserve the factory getter's integer-mA rounding at 57.5 mA/step. */
\t*cur = (value <= 13 ? value * 90 : (value - 14) * 115 / 2 + 805) * 1000;
\treturn 0;''',
        'bq2560x_charger_register_vbus_regulator': '''
\tstatic struct regulator_consumer_supply supply = {
\t\t.supply = "vddvbus",
\t};
\tstruct regulator_init_data *init;
\tstruct regulator_config cfg = {
\t\t.dev = info->dev,
\t\t.of_node = info->dev->of_node,
\t\t.driver_data = info,
\t};
\tstruct regulator_dev *reg;
\t/* Mirror the user's working A-slot OTG supply lookup in memory.
\t * A DT phandle takes precedence; B-slot otherwise lacks this mapping.
\t */
\tinit = devm_kzalloc(info->dev, sizeof(*init), GFP_KERNEL);
\tif (!init)
\t\treturn -ENOMEM;
\tinit->constraints.valid_ops_mask = REGULATOR_CHANGE_STATUS;
\tinit->constraints.min_uV = 5000000;
\tinit->constraints.max_uV = 5000000;
\tinit->num_consumer_supplies = 1;
\tinit->consumer_supplies = &supply;
\tcfg.init_data = init;
\treg = devm_regulator_register(info->dev, &bq2560x_charger_vbus_desc, &cfg);
\treturn PTR_ERR_OR_ZERO(reg);''',
    }
    for name, body in bodies.items():
        source = replace_function(source, name, body)
    start = source.index('\tret = bq2560x_read(info,BQ2560X_REG_B, &val);')
    end = source.index('\n\ti2c_set_clientdata(client, info);', start)
    source = source[:start] + '''
\tret = bq2560x_read(info, BQ2560X_REG_B, &val);
\tif (ret < 0) return ret;
\tif (val != 0x12 || client->addr != 0x6b) {
\t\tdev_err(dev, "unsupported T551M charger ID %#x at %#x\\n", val, client->addr);
\t\treturn -ENODEV;
\t}
\tstrscpy(info->charge_ic_vendor_name, "T551M-0x12",
\t\tsizeof(info->charge_ic_vendor_name));
''' + source[end:]
    # Remove SGM-specific register 0x0f helpers (the T551M register map ends at B).
    source = replace_function(source, 'bq2560x_charger_set_vindpmos', '\treturn -EOPNOTSUPP;')
    # REG00[4:0] is 100 mA + code * 100 mA: 3.2 A is the register range,
    # not a bring-up cap. Keep SDP/DCP and temperature policy in charger-manager.
    # Clamp the lower end as well so requests below 100 mA cannot underflow.
    source = source.replace(
        '\tif (limit_cur >= BQ2560X_LIMIT_CURRENT_MAX)\n\t\tlimit_cur = BQ2560X_LIMIT_CURRENT_MAX;',
        '\tlimit_cur = clamp_val(limit_cur, BQ2560X_LIMIT_CURRENT_OFFSET, BQ2560X_LIMIT_CURRENT_MAX);')
    # Retain the stock safety-timer, recharge and boost-current configuration.
    start = source.index('\n\tret = bq2560x_update_bits(info, BQ2560X_REG_A,')
    end = source.index('\n\tinfo->current_charge_limit_cur', start)
    source = source[:start] + source[end:]
    source = source.replace('for (i = 0; i < 0x10; i++)', 'for (i = 0; i <= 0x0b; i++)')
    return source
