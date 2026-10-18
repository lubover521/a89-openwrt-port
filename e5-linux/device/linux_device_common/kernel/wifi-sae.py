#!/usr/bin/env python3
"""Bridge standard AP SAE password offload to the SC2355 BSP protocol."""
from pathlib import Path
import re


def apply(kernel):
    base = Path(kernel) / 'drivers/unisoc_platform/sprd_wlan_combo'
    apply_driver(base)


def apply_driver(base):
    base = Path(base)
    files = {name: (base / name).read_text(encoding='utf-8') for name in
             ('sc2355/cmdevt.c', 'sc2355/init.c', 'common/cfg80211.c')}

    def edit(name, old, new):
        text = files[name]
        if new in text:
            return
        if text.count(old) != 1:
            raise ValueError('Unexpected SC2355 SAE source: ' + name + ': ' + old[:65])
        files[name] = text.replace(old, new, 1)

    name = 'sc2355/init.c'
    old = '\twiphy->features |= NL80211_FEATURE_SAE;'
    gate = old + '''
	/* Standard password transport; four-way handshake stays in hostapd. */
	if ((priv->extend_feature & SPRD_EXTEND_SOATAP_WPA3) &&
	    (priv->fw_capa & SPRD_CAPA_AP_SME) &&
	    (priv->fw_std & SPRD_STD_11W))
		wiphy_ext_feature_set(wiphy, NL80211_EXT_FEATURE_SAE_OFFLOAD_AP);'''
    extended = gate.replace('(priv->fw_std & SPRD_STD_11W))\n',
                            '(priv->fw_std & SPRD_STD_11W)) {\n') + '''
		/* Mixed mode carries PSK, PSK-SHA256 and SAE. A default limit
		 * of two makes hostapd omit AKM_SUITES entirely (including SAE).
		 */
		wiphy->max_num_akm_suites = 3;
	}'''
    if extended not in files[name] and gate in files[name]:
        files[name] = files[name].replace(gate, extended, 1)
    else:
        edit(name, old, extended)

    name = 'sc2355/cmdevt.c'
    edit(name, 'int sc2355_start_ap(', '#include "sae.h"\n\nint sc2355_start_ap(')
    text = files[name]
    start = text.index('int sc2355_start_ap(')
    end = text.index('\nint sc2355_del_station(', start)
    func = text[start:end]
    if 'sc2355_prepare_sae(priv, vif, settings)' not in func:
        func = func.replace('\tstruct sprd_msg *msg;', '\tint ret;\n\tstruct sprd_msg *msg;', 1)
        anchor = '\tfw_ver = (api + CMD_SCAN)->fw_version;'
        if func.count(anchor) != 1:
            raise ValueError('Unexpected SC2355 START_AP declarations')
        func = func.replace(anchor, '''	ret = sc2355_prepare_sae(priv, vif, settings);
	if (ret)
		return ret;

''' + anchor, 1)
        files[name] = text[:start] + func + text[end:]

    text = files[name]
    start = text.index('int sc2355_send_cmd_recv_rsp(')
    end = text.index('\n/* Commands */', start)
    func = text[start:end]
    marker = 'SAE rejection must not become a successful START_AP.'
    if marker not in func:
        anchor = '\tif (ret != -1) {\n'
        if func.count(anchor) != 1:
            raise ValueError('Unexpected SC2355 response path')
        func = func.replace(anchor, anchor + '''		/* SAE rejection must not become a successful START_AP. */
		if (cmd_id == CMD_SET_SAE_PARAM &&
		    (!cmd->data || ((struct sprd_cmd_hdr *)cmd->data)->status))
			ret = -EIO;
''', 1)
        # Preserve command mutex ownership and propagate a failed acquisition.
        anchor = 'if (ret || cmdevt_lock_cmd(cmd, hif)) {'
        if func.count(anchor) != 1:
            raise ValueError('Unexpected SC2355 command lock')
        func = func.replace(anchor, 'if (!ret)\n\t\tret = cmdevt_lock_cmd(cmd, hif);\n\tif (ret) {', 1)
        for condition in ('if (cmd_id != CMD_CLOSE) {',
                          'if (cmd_id != CMD_CLOSE && cmd_id != CMD_OPEN) {'):
            if func.count(condition) != 1:
                raise ValueError('Unexpected SC2355 command suppression')
            func = func.replace(condition, condition + '\n\t\t\tret = -EBUSY;', 1)
        files[name] = text[:start] + func + text[end:]

    # The native AP SME owns authentication, as in the Android BSP. Registering
    # AUTH frames redirects them away from firmware and races software SAE.
    name = 'common/cfg80211.c'
    anchor = '\t\tframe_type = i << 4;\n'
    edit(name, anchor, anchor + '''		if (frame_type == IEEE80211_STYPE_AUTH &&
		    (vif->mode == SPRD_MODE_AP || vif->mode == SPRD_MODE_P2P_GO) &&
		    wiphy_ext_feature_isset(wiphy, NL80211_EXT_FEATURE_SAE_OFFLOAD_AP))
			continue;
''')

    name = 'sc2355/cmdevt.c'
    text = files[name]
    # Generic debug dumps otherwise expose the password and firmware PMK.
    for label, condition in [('CMD: ', 'hdr->cmd_id != CMD_SET_SAE_PARAM'),
                             ('EVENT: ', 'hdr->cmd_id != EVT_NEW_STATION')]:
        pattern = r'(?m)^(\s*)print_hex_dump_debug\("' + re.escape(label) + r'"'
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError('Unexpected SC2355 debug dump: ' + label)
        match = matches[0]
        # Nonblank indentation, without consuming an earlier newline.
        line = text.rfind('\n', 0, match.end()) + 1
        indent = text[line:match.end()].split('print_hex_dump_debug')[0]
        if condition not in text[max(0, line - 120):line]:
            text = text[:line] + indent + 'if (' + condition + ')\n\t' + text[line:]
    for label, condition in [('CMD: ', 'hdr->cmd_id != CMD_SET_SAE_PARAM'), ('EVENT: ', 'hdr->cmd_id != EVT_NEW_STATION')]:
        pattern = r'(?m)^(\t*)if \(' + re.escape(condition) + r'\)\n\t*print_hex_dump_debug'
        text = re.sub(pattern, lambda m: m[1] + 'if (' + condition + ')\n' + m[1] + '\tprint_hex_dump_debug', text)
    files[name] = text

    # Validate every edit before touching the caller's tree.
    for name, text in files.items():
        (base / name).write_text(text, encoding='utf-8')
    (base / 'sc2355/sae.h').write_bytes(Path(__file__).with_name('wifi-sae.h').read_bytes())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)
