#!/usr/bin/env python3
"""Expose SC2355 AP peers without pretending STA-wide data is per-client data."""
from pathlib import Path

HELPERS = '''/* AP peers are authoritative; GET_STATION firmware data is STA-wide. */
static bool sprd_ap_peer(struct sprd_vif *vif, const u8 *mac)
{
	struct sprd_hif *hif = &vif->priv->hif;
	int i;

	if (!is_valid_ether_addr(mac) || ether_addr_equal(mac, vif->ndev->dev_addr))
		return false;
	for (i = 0; i < MAX_LUT_NUM; i++) {
		if (READ_ONCE(hif->peer_entry[i].ctx_id) == vif->ctx_id &&
		    ether_addr_equal(hif->peer_entry[i].tx.da, mac))
			return true;
	}
	return false;
}

static int sprd_cfg80211_dump_station(struct wiphy *wiphy, struct net_device *ndev,
				     int idx, u8 *mac, struct station_info *sinfo)
{
	struct sprd_vif *vif = netdev_priv(ndev);
	struct sprd_hif *hif = &vif->priv->hif;
	u8 peer[ETH_ALEN];
	int i, n = 0;

	if (idx < 0 || (vif->wdev.iftype != NL80211_IFTYPE_AP &&
			vif->wdev.iftype != NL80211_IFTYPE_P2P_GO))
		return -ENOENT;
	for (i = 0; i < MAX_LUT_NUM; i++) {
		if (READ_ONCE(hif->peer_entry[i].ctx_id) != vif->ctx_id)
			continue;
		ether_addr_copy(peer, hif->peer_entry[i].tx.da);
		if (!sprd_ap_peer(vif, peer) || n++ != idx)
			continue;
		ether_addr_copy(mac, peer);
		sinfo->filled = 0;
		return 0;
	}
	return -ENOENT;
}

static int sprd_cfg80211_get_channel(struct wiphy *wiphy, struct wireless_dev *wdev,
				    unsigned int link_id, struct cfg80211_chan_def *chandef)
{
	/* This non-MLO driver only has the default link. Check before indexing. */
	if (link_id != 0 || (wdev->iftype != NL80211_IFTYPE_AP &&
			    wdev->iftype != NL80211_IFTYPE_P2P_GO) ||
	    !wdev->links[0].ap.chandef.chan)
		return -ENODATA;
	*chandef = wdev->links[0].ap.chandef;
	return 0;
}

'''


def apply(kernel):
    path = Path(kernel) / 'drivers/unisoc_platform/sprd_wlan_combo/common/cfg80211.c'
    source = path.read_text()
    marker = '/* AP peers are authoritative; GET_STATION firmware data is STA-wide. */'
    if marker in source:
        return
    anchor = 'int sprd_cfg80211_get_station('
    if source.count(anchor) != 1 or 'sprd_cfg80211_dump_station(' in source:
        raise ValueError('Unexpected SC2355 station source')
    source = source.replace(anchor, HELPERS + anchor, 1)
    pos = source.index(anchor)
    old = '\tint ret;\n'
    index = source.index(old, pos) + len(old)
    source = source[:index] + '''
	/* AP firmware has no addressed per-peer RSSI/rate/counter command. */
	if (vif->wdev.iftype == NL80211_IFTYPE_AP ||
	    vif->wdev.iftype == NL80211_IFTYPE_P2P_GO) {
		if (!sprd_ap_peer(vif, mac))
			return -ENOENT;
		sinfo->filled = 0;
		return 0;
	}
''' + source[index:]
    anchor = '\t.get_station = sprd_cfg80211_get_station,'
    if source.count(anchor) != 1:
        raise ValueError('Unexpected SC2355 station ops')
    source = source.replace(anchor, anchor + '\n\t.dump_station = sprd_cfg80211_dump_station,\n\t.get_channel = sprd_cfg80211_get_channel,', 1)
    path.write_text(source)


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
