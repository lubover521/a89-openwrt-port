// Independent card readings, refreshed outside the HTTP request path.
function sim_status() {
	let data = null;
	try { data = json(readfile('/run/t551m-sims.json') ?? 'null'); } catch (e) {}
	let now = +(split(readfile('/proc/uptime') ?? '0', ' ')[0]);
	let active = sim_card();
	return map([0,1], slot => {
		let s = data?.sims?.[slot];
		if (s == null || s.slot != slot || now - s.updated > 15 || now < s.updated)
			return { slot, data: slot == active, registration: 'unknown', stale: true, signal: {} };
		return { ...s, data: slot == active, stale: false };
	});
}

function card_modem(m, sims) {
	let s = sims[sim_card()];
	// Never borrow the standby card's access technology or signal from MM.
	let r = { ...m, tech: s.tech, radio_label: s.radio_label, signal: { ...(s.signal ?? {}) }, quality: null,
		registration: s.registration == 'camped' ? 'unknown' : s.registration };
	// A live CP can still advertise emergency camping with no SIM. The
	// per-slot CPIN result takes precedence over an old MM SIM/operator cache.
	if (!s.stale && s.present === false) {
		r.sim = false; r.operator = null; r.cell = null;
		return r;
	}
	if (r.cell?.type != (s.tech == '5gnr' ? '5gnr' : s.tech)) r.cell = null;
	let cached = null;
	try { cached = json(readfile('/tmp/unisoc-modem/sim' + sim_card() + '/sig.json') ?? readfile('/tmp/unisoc-modem/sig.json') ?? 'null'); } catch (e) {}
	if (!s.stale && s.present === true && !s.error && cached?.card == sim_card() && !cached.error && !cached.partial && time()-cached.ts >= 0 && time()-cached.ts <= 10) {
		// Same serving-NR > LTE/AcT decision as the dashboard; no MM bitmask.
		if (cached.nr?.band) {
			r.tech = '5gnr'; r.radio_label = cached.lte?.band ? '5G NSA' : '5G SA';
		} else if (cached.lte?.band) {
			r.tech = (s.act == 13 || s.act == 11 || s.act == 18 || s.act == 19) ? '5gnr' : (s.act >= 2 && s.act <= 6) ? 'umts' : 'lte';
			r.radio_label = s.act == 13 ? '5G NSA' : r.tech == '5gnr' ? '5G' : r.tech == 'umts' ? '3G' : '4G';
		}
		let cell = cached.nr?.band ? cached.nr : cached.lte;
		if (cell?.band) {
			r.signal = { rsrp: cell.rsrp, rsrq: cell.rsrq,
				snr: cell.sinr ?? (s.tech == r.tech ? s.signal?.snr : null) };
			r.cell = { type: cached.nr?.band ? '5gnr' : 'lte', band: (cached.nr?.band ? 'n' : 'B') + cell.band,
				pci: cell.pci, arfcn: cell.arfcn ?? cell.earfcn,
				bandwidth_mhz: cell.bw ? +replace(cell.bw, 'M', '') : null };
		}
		s.tech = r.tech; s.radio_label = r.radio_label;
	}
	if (s.operator) r.operator = s.operator;
	let rsrp = r.signal.rsrp;
	if (rsrp != null) r.quality = max(0, min(100, (rsrp + 120) * 2.5));
	return r;
}
