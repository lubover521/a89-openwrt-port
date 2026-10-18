/* SPDX-License-Identifier: GPL-2.0-only */
/* AW32257 datasheet v1.5, REG04/REG06, with current scaled by board RSNS.
 * REG01[7:4] is reserved: this chip has no BQ24158 input-limit register.
 */
static const unsigned int aw32257_current_ma[] = {
	496, 620, 868, 992, 1116, 1240, 1364, 1488,
	1612, 1736, 1860, 1984, 2108, 2232, 2356, 2480
};

static int aw32257_current_ua(unsigned int code, unsigned int rsns)
{
	if (code >= ARRAY_SIZE(aw32257_current_ma) || !rsns)
		return -EINVAL;
	return (unsigned long long)aw32257_current_ma[code] * 33000 / rsns;
}

static int aw32257_current_code(int ua, unsigned int rsns)
{
	int code;
	if (!rsns || ua < 0)
		return -EINVAL;
	for (code = ARRAY_SIZE(aw32257_current_ma) - 1; code >= 0; code--)
		if (aw32257_current_ua(code, rsns) <= ua)
			return code;
	return -ERANGE;
}
