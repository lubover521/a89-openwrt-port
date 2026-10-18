'use strict';
import { readfile, writefile, rename } from 'fs';
const CONTACTS = '/etc/e5/contacts.json';
const AUDIO = '/run/e5-voice-audio';

return function(ctx) {
	let voice = loadfile('/usr/share/e5-infoscreen/www/plugins/phone/voice.uc', { raw_mode: true })()(ctx);
	function fail(r, code) {
		return { status: code ?? 502, type: 'application/json', body: sprintf('%J', r) };
	}
	function contacts() {
		try {
			let list = json(readfile(CONTACTS) ?? '[]');
			return type(list) == 'array' ? list : [];
		} catch(e) { return []; }
	}
	function audio() {
		try {
			let a = json(readfile(AUDIO + '/status.json') ?? 'null');
			if (a && time() - a.updated < 15) return a;
		} catch(e) {}
		return { available: false, active: false, speaker: false, muted: false,
			error: 'Call audio service is not ready' };
	}
	function live() {
		let a = audio(), state;
		// One shared observer owns snapshots. Screen polls must not fork mmcli
		// for every historical call, or queue more AT queries behind DTMF.
		if (a.available && type(a.calls) == 'array' && time() - a.updated < 2)
			state = { calls: a.calls, error: null };
		else state = voice.list();
		return { ...state, audio: a,
			wake: ctx.uci().get('e5-plugin-phone', 'settings', 'ring_screen') != '0' };
	}
	return {
		'GET /live': function(req) { return live(); },
		'GET /notifications': function(req) {
			let a = audio(), list;
			if (a.available && type(a.calls) == 'array') list = a.calls;
			else list = voice.list().calls;
			let wake = ctx.uci().get('e5-plugin-phone', 'settings', 'ring_screen') != '0';
			return { notifications: map(filter(list, c => c.state == 'ringing-in' || c.state == 'waiting'),
				c => ({ id: 'call-' + c.id, title: { zh: '来电', en: 'Incoming call' },
					body: (c.sim ? c.sim + ' · ' : '') + c.number, wake })) };
		},
		'GET /status': function(req) { return { ...live(), contacts: contacts(),
			sim: { card: trim(readfile('/sys/module/sipc_wwan/parameters/card') ?? '0') == '1' ? 1 : 0 } }; },
		'POST /dtmf': function(req) {
			let r = voice.dtmf(req.body?.id, req.body?.tone);
			return r.ok ? r : fail(r, r.stage == 'validate' ? 400 : 502);
		},
		'POST /audio': function(req) {
			if (!audio().available) return fail({ ok: false, error: 'Call audio service is not ready' }, 503);
			let b = req.body ?? {}, settings;
			try { settings = json(readfile(AUDIO + '/settings.json') ?? '{}'); } catch(e) { settings = {}; }
			for (let key in [ 'speaker', 'muted' ]) {
				if (b[key] == null) continue;
				if (type(b[key]) != 'bool') return fail({ ok: false, error: 'Invalid audio setting' }, 400);
				settings[key] = b[key];
			}
			if (b.route != null || b.speaker != null) {
				let route = b.route ?? (b.speaker ? 'speaker' : 'receiver');
				if (index([ 'auto', 'receiver', 'speaker', 'bluetooth' ], route) < 0)
					return fail({ ok: false, error: 'Invalid audio route' }, 400);
				if (route == 'bluetooth' && !audio().bluetooth?.connected)
					return fail({ ok: false, error: 'Bluetooth headset is not connected for calls' }, 409);
				settings.route = route;
				let now = clock(true);
				settings.route_updated = now[0] + now[1] / 1000000000;
			}
			let tmp = AUDIO + '/request.' + clock();
			if (!writefile(tmp, sprintf('%J\n', settings)) || !rename(tmp, AUDIO + '/settings.json'))
				return fail({ ok: false, error: 'Cannot save call audio setting' }, 500);
			return { ok: true };
		},
		'POST /call': function(req) {
			let r = voice.dial(req.body?.number, req.body?.card);
			return r.ok ? r : fail(r, r.stage == 'validate' ? 400 : 502);
		},
		'POST /answer': function(req) {
			let r = voice.action(req.body?.id, 'accept');
			return r.ok ? r : fail(r);
		},
		'POST /hangup': function(req) {
			let r = voice.action(req.body?.id, 'hangup');
			return r.ok ? r : fail(r);
		},
		'POST /contacts': function(req) {
			let list = req.body?.contacts;
			if (type(list) != 'array' || length(list) > 100)
				return fail({ ok: false, error: 'Invalid contacts' }, 400);
			let saved = [];
			for (let c in list) {
				let name = trim(`${c?.name ?? ''}`), number = `${c?.number ?? ''}`;
				if (length(name) > 40 || !match(number, /^\+?[0-9*#]{3,32}$/))
					return fail({ ok: false, error: 'Invalid contact name or number' }, 400);
				push(saved, { name, number });
			}
			if (ctx.run('mkdir -p /etc/e5') != 0)
				return fail({ ok: false, error: 'Cannot create contacts directory' }, 500);
			let tick = clock(true), tmp = `${CONTACTS}.${tick[0]}${tick[1]}`;
			if (!writefile(tmp, sprintf('%J\n', saved)) || !rename(tmp, CONTACTS))
				return fail({ ok: false, error: 'Cannot save contacts' }, 500);
			return { ok: true, contacts: saved };
		}
	};
};
