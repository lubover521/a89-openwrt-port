// ModemManager owns call control. This adapter only maps its CLI operations
// and states to the screen API; it never controls a call from a status poll.
'use strict';
import { readfile } from 'fs';

return function(ctx) {
	const PATH = '/org/freedesktop/ModemManager1/Call/';
	const LIVE = [ 'dialing', 'ringing-out', 'ringing-in', 'active', 'held', 'waiting' ];
	function q(s) { return "'" + replace(`${s}`, /'/g, "'\\''") + "'"; }
	function run(cmd) {
		let out = ctx.sh(`{ LC_ALL=C ${cmd}; r=$?; printf '\\n__E5_VOICE_RC__%s\\n' "$r"; } 2>&1`) ?? '';
		let m = match(out, /\n__E5_VOICE_RC__([0-9]+)\s*$/);
		return { rc: m ? +m[1] : 1,
			out: trim(replace(out, /\n__E5_VOICE_RC__[0-9]+\s*$/, '')) };
	}
	function call_id(id) {
		let s = `${id ?? ''}`;
		if (substr(s, 0, length(PATH)) == PATH) s = substr(s, length(PATH));
		return match(s, /^[0-9]+$/) ? s : null;
	}
	function sim() { let card = trim(readfile('/sys/module/sipc_wwan/parameters/card') ?? '0') == '1' ? 1 : 0; return { card, name: `SIM${card + 1}` }; }
	function list() {
		let r = run('mmcli -J -m any --timeout=3 --voice-list-calls');
		if (r.rc) return { calls: [], error: r.out || 'Cannot read modem calls' };
		let j;
		try { j = json(r.out); } catch(e) { return { calls: [], error: 'Invalid ModemManager call list' }; }
		let paths = j?.['modem.voice.call'] ?? j?.['modem.voice.calls'] ?? j?.modem?.voice?.call ?? j?.modem?.voice?.calls ?? [];
		let calls = [];
		for (let path in paths) {
			let id = call_id(path);
			if (id == null) continue;
			let c = ctx.sh_json(`mmcli -J --timeout=2 -o ${q(PATH + id)} 2>/dev/null`)?.call;
			let p = c?.properties;
			// '--'/unknown objects have been created but not started. A terminated
			// object also remains on D-Bus until explicitly deleted. Neither is live.
			if (index(LIVE, p?.state) < 0) continue;
			push(calls, { id, path: PATH + id, number: p.number == '--' ? '' : (p.number ?? ''),
				state: p.state, reason: p['state-reason'], direction: p.direction,
				card: +p['sim-slot'] == 1 ? 0 : +p['sim-slot'] == 2 ? 1 : null,
				sim: +p['sim-slot'] > 0 ? `SIM${+p['sim-slot']}` : null });
		}
		return { calls, sim: sim(), error: null };
	}
	function result(r, stage, id) {
		return r.rc ? { ok: false, stage, id, error: r.out || `${stage} failed (exit ${r.rc})` }
			: { ok: true, id };
	}
	function dial(number, card) {
		number = `${number ?? ''}`;
		if (!match(number, /^\+?[0-9*#]{3,32}$/))
			return { ok: false, stage: 'validate', error: 'Invalid number' };
		if (card != null && card !== 0 && card !== 1 && card !== '0' && card !== '1')
			return { ok: false, stage: 'validate', error: 'Invalid SIM card' };
		let properties = 'number=' + number + (card == null ? '' : ',sim-slot=' + (+card + 1));
		let created = run(`mmcli -m any --timeout=5 --voice-create-call=${q(properties)}`);
		if (created.rc) return result(created, 'create', null);
		let m = match(created.out, /\/org\/freedesktop\/ModemManager1\/Call\/([0-9]+)/);
		if (!m) return { ok: false, stage: 'create', error: 'ModemManager did not return a call ID' };
		// CreateCall does not dial. Start exactly the object returned above; never
		// choose an arbitrary previous object or retry a timed-out call automatically.
		return result(run(`mmcli --timeout=15 -o ${q(PATH + m[1])} --start`), 'start', m[1]);
	}
	function action(id, op) {
		id = call_id(id);
		if (id == null) return { ok: false, stage: 'validate', error: 'Invalid call ID' };
		if (op != 'accept' && op != 'hangup')
			return { ok: false, stage: 'validate', error: 'Invalid call action' };
		return result(run(`mmcli --timeout=15 -o ${q(PATH + id)} --${op}`), op, id);
	}
	function dtmf(id, tone) {
		id = call_id(id);
		if (id == null || type(tone) != 'string' || !match(tone, /^[0-9*#]$/))
			return { ok: false, stage: 'validate', error: 'Invalid call ID or DTMF digit' };
		// Address this exact call; ModemManager validates ACTIVE and selects its SIM.
		// Never retry a tone: an uncertain result must not enter a digit twice.
		return result(run(`mmcli --timeout=5 -o ${q(PATH + id)} --send-dtmf=${q(tone)}`), 'dtmf', id);
	}
	return { list, dial, action, dtmf };
};
