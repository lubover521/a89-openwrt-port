#!/usr/bin/env python3
"""Select Marlin3Lite RF tables using the factory IPD efuse selector.

Reconstructed from this unit's original wcn_bsp.ko and sprd_wlan_combo.ko:
marlin_get_wcn_xpe_efuse_data (0x1310c), sc2355_get_nvm_table (0x260e8).
The register sequence enables efuse shadow reads; it does not burn efuses.
Applied only to the separate M8 kernel tree.
"""
from pathlib import Path


def apply(kernel):
    path = Path(kernel) / 'drivers/unisoc_platform/sprd_wlan_combo/sc2355/hw_param.c'
    text = path.read_text()
    if 'm8_wcn_ipd_variant' in text:
        return
    anchor = 'int sc2355_get_nvm_table(struct sprd_priv *priv, struct wifi_conf_t *p)'
    helper = '''/* Match the stock Marlin3Lite efuse shadow-read sequence. */
static int m8_wcn_ipd_variant(void)
{
	static int cached = -1;
	static const u32 enable[][2] = {
		{ 0x4083c32c, BIT(22) },
		{ 0x4083c024, BIT(11) },
		{ 0x4083c050, BIT(18) },
		{ 0x40858040, BIT(0) },
	};
	u32 value;
	int i, ret;

	if (cached >= 0)
		return cached;
	for (i = 0; i < ARRAY_SIZE(enable); i++) {
		ret = sprdwcn_bus_reg_read(enable[i][0], &value, sizeof(value));
		if (ret < 0)
			return ret;
		if (!(value & enable[i][1])) {
			value |= enable[i][1];
			ret = sprdwcn_bus_reg_write(enable[i][0], &value, sizeof(value));
			if (ret < 0)
				return ret;
		}
	}
	ret = sprdwcn_bus_reg_read(0x40859030, &value, sizeof(value));
	if (ret < 0)
		return ret;
	cached = (value >> 29) & 3;
	wl_info("Marlin3Lite IPD selector: %d\\n", cached);
	return cached;
}

'''
    if text.count(anchor) != 1:
        raise ValueError('Missing Wi-Fi table selector')
    text = text.replace(anchor, helper + anchor)
    start = text.index('\t} else if (wcn_get_chip_type() == WCN_CHIP_ID_AB) {', text.index(anchor))
    end = text.index('\n\tif (prj_name', start)
    text = text[:start] + '''	} else if (wcn_get_chip_type() == WCN_CHIP_ID_AB) {
		int ipd = m8_wcn_ipd_variant();
		const char *file;

		if (ipd < 0)
			return ipd; /* Do not guess a calibration table on read failure. */
		file = ipd == 1 ? SYSTEM_WIFI_XPE_CONFIG_FILE : SYSTEM_WIFI_CONFIG_FILE;
		wl_info("%s, chip id %d IPD(%d) open %s\\n", __func__,
			wcn_get_chip_type(), ipd, file);
		return hw_param_nvm_parse(priv, file, (void *)p);
	}
''' + text[end:]
    path.write_text(text)
