// Metadata renders immediately; the AT owner pool refreshes radio data in the
// background. Read the radio cache every request, independently of metadata TTL.
function advanced() {
	let r = advanced_base();
	let radio = sh_json('/usr/libexec/t551m-screen-details');
	let v = radio?.values ?? {};
	if (r.baseband) {
		r.baseband.lte_lock = v.lte ? lte_bands(v.lte) : null;
		r.baseband.nr_lock = v.nr ? nr_bands(v.nr) : null;
		r.baseband.sa_allowed = v.sa ? payload_ints(v.sa)[0] == 1 : null;
		r.baseband.lte_cell_lock = v.lte_cell ? cell_locks(v.lte_cell) : null;
		r.baseband.nr_cell_lock = v.nr_cell ? cell_locks(v.nr_cell) : null;
	}
	if (r.sim) r.sim.active_slot = sim_card() + 1;
	r.radio_pending = radio?.pending ?? true;
	r.radio_error = radio?.error ?? false;
	return r;
}
