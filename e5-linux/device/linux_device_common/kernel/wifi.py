"""Fix SC2355 TX scheduling, AP command pressure and skb ownership.

Adapted from mu300-linux 7e0acce0a01b and f4f5e760cfa6. This tree uses
the SDIO driver's is_dns/sc2355 names instead of the PCIe fork's fields.
"""
from pathlib import Path
import runpy


def apply(kernel):
    path = kernel / 'drivers/unisoc_platform/sprd_wlan_combo/sc2355/tx.c'
    text = path.read_text()
    changes = [
        ('Yield between accumulated TX completions',
         '\t\ttx_work_queue(tx_mgmt);\n\t}\n',
         '''		tx_work_queue(tx_mgmt);
		/* Yield between accumulated TX completions: wait_for_completion()
		 * does not sleep while wakeups are pending. On PREEMPT_NONE, a
		 * busy credit-polling loop otherwise starves RX/IRQ threads and
		 * eventually the watchdog, especially after a firmware failure.
		 */
		cond_resched();
	}
'''),
        ('AP ARP uses the data queue',
         '\tif (ethhdr->h_proto == htons(ETH_P_ARP)) {\n\t\twl_info("incoming ARP packet\\n");',
         '''	if (ethhdr->h_proto == htons(ETH_P_ARP)) {
		/* AP ARP uses the data queue: a burst of CMD_TX_DATA can starve
		 * firmware control replies and assert the whole WCN radio.
		 */
		if (vif->mode == SPRD_MODE_AP || vif->mode == SPRD_MODE_P2P_GO)
			return 1;
		wl_info("incoming ARP packet\\n");'''),
        ('AP DNS uses the data queue',
         '\t/*as CP request, send data with CMD */\n\tif (is_data2cmd) {\n',
         '''	/*as CP request, send data with CMD */
	if (is_data2cmd) {
		/* AP DNS uses the data queue, before any command-path checksum
		 * modification. Preserve DHCP, VoWiFi and RTSP control handling.
		 */
		if ((vif->mode == SPRD_MODE_AP || vif->mode == SPRD_MODE_P2P_GO) &&
		    is_dns && !is_ipv4_dhcp && !is_ipv6_dhcp &&
		    !is_vowifi2cmd && !is_alive_rtsp)
			return 1;

'''),
    ]
    for marker, old, new in changes:
        if marker in text:
            if text.count(new) != 1:
                raise ValueError('Unexpected existing Wi-Fi adaptation: ' + marker)
            continue
        if text.count(old) != 1:
            raise ValueError('Unexpected Wi-Fi source: ' + marker)
        text = text.replace(old, new, 1)
    path.write_text(text)

    path = kernel / 'drivers/unisoc_platform/sprd_wlan_combo/common/iface.c'
    text = path.read_text()
    marker = 'Keep the original skb object for a possible NETDEV_TX_BUSY retry.'
    headroom = '''	/* Keep the original skb object for a possible NETDEV_TX_BUSY retry.
	 * Bridge/TCP clones also need private writable descriptor headroom.
	 */
	if (skb_cow_head(skb, ndev->needed_headroom)) {
		dev_kfree_skb(skb);
		ndev->stats.tx_dropped++;
		return -1;
	}
'''
    if marker not in text:
        start = text.index('static int iface_prepare_xmit(')
        end = text.index('\nstatic netdev_tx_t iface_start_xmit(', start)
        func = text[start:end]
        old = '\tstruct sk_buff *tmp_skb = skb;\n'
        if func.count(old) != 1:
            raise ValueError('Unexpected Wi-Fi TX preparation locals')
        func = func.replace(old, '')
        first = func.index('\tif (skb_headroom(skb) < ndev->needed_headroom) {')
        last = func.index('\treturn ret;', first)
        func = func[:first] + headroom + func[last:]
        text = text[:start] + func + text[end:]
        path.write_text(text)
    elif text.count(headroom) != 1:
        raise ValueError('Unexpected existing Wi-Fi TX headroom adaptation')

    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'wifi-common.py'))['apply'](kernel)


if __name__ == '__main__':
    import sys
    apply(Path(sys.argv[1]))
