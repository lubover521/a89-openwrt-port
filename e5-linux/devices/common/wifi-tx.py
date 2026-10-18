#!/usr/bin/env python3
"""Keep ordinary SC2355 AP multicast on the flow-controlled data path."""
from pathlib import Path
import re


MARKER = 'AP multicast uses the data queue; classify control traffic below.'


def apply(kernel):
    path = Path(kernel) / 'drivers/unisoc_platform/sprd_wlan_combo/sc2355/tx.c'
    text = path.read_text()
    if MARKER in text:
        if any(re.search(r'\b' + name + r'\(', text) for name in (
                'tx_is_multicast_mac_addr', 'tx_mc_pkt_checksum', 'tx_mc_pkt')):
            raise ValueError('Unexpected partial SC2355 multicast adaptation')
        return
    start = text.index('static int tx_is_multicast_mac_addr(')
    end = text.index('static int tx_filter_ip_pkt(', start)
    old = '\t\tif (!tx_mc_pkt(skb, ndev))\n\t\t\treturn NETDEV_TX_OK;\n'
    if text.count(old) != 1:
        raise ValueError('Unexpected SC2355 multicast classifier')
    # These three helpers only divert AP multicast to CMD_TX_DATA. Removing
    # them keeps unicast/STA behavior and lets DHCP/VoWiFi/RTSP be classified
    # before ordinary traffic reaches the existing group BK data queue.
    block = text[start:end]
    for name in ('tx_is_multicast_mac_addr', 'tx_mc_pkt_checksum', 'tx_mc_pkt'):
        if len(re.findall(r'\b' + name + r'\(', block)) != (1 if name == 'tx_mc_pkt' else 2):
            raise ValueError('Unexpected SC2355 multicast helper: ' + name)
    text = text[:start] + text[end:]
    text = text.replace(old, '\t\t/* ' + MARKER + '\n'
                        '\t\t * CMD_TX_DATA has no business-packet backpressure. Keep DHCP,\n'
                        '\t\t * VoWiFi and RTSP handling in the IP filter, without changing\n'
                        '\t\t * ordinary multicast checksums or adding a retry poller.\n'
                        '\t\t */\n', 1)
    if any(re.search(r'\b' + name + r'\(', text) for name in (
            'tx_is_multicast_mac_addr', 'tx_mc_pkt_checksum', 'tx_mc_pkt')):
        raise ValueError('Unexpected additional SC2355 multicast helper reference')
    path.write_text(text)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)
