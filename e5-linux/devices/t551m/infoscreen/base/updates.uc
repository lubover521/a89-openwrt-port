// Shared update state for the overview notification and Settings -> System.
'use strict';

return function(ctx) {
const fs = require('fs');
const RUN = '/tmp/run/e5-infoscreen';
const JOB = '/usr/libexec/e5-infoscreen/update-job';
const LOCK = RUN + '/update-job.lock';

function newer(a, b) {
	if (!match(a ?? '', /^[0-9]+(\.[0-9]+)*$/) || !match(b ?? '', /^[0-9]+(\.[0-9]+)*$/))
		return false;
	let x = split(a, '.'), y = split(b, '.');
	let count = length(x) > length(y) ? length(x) : length(y);
	for (let i = 0; i < count; i++) {
		let left = +(x[i] ?? 0), right = +(y[i] ?? 0);
		if (left != right)
			return left > right;
	}
	return false;
}

function state() {
	let latest = null;
	try { latest = json(ctx.read_trim(`${RUN}/latest.json`) ?? 'null'); } catch (e) {}
	let current = ctx.read_trim('/usr/share/e5-infoscreen/VERSION') ?? '0';
	let adaptation = ctx.read_trim('/usr/share/e5-infoscreen/ADAPTATION');
	let compatible = !adaptation || latest?.adaptation == adaptation;
	let pid = ctx.read_trim(`${LOCK}/pid`);
	let cmd = pid && match(pid, /^[0-9]+$/) ? fs.readfile(`/proc/${pid}/cmdline`) : null;
	let running = cmd != null && index(cmd, JOB) >= 0;
	let queued = +(ctx.read_trim(`${LOCK}/queued-at`) ?? 0);
	running = running || (ctx.read_trim(`${LOCK}/token`) != null && queued > time() - 30);
	let action = ctx.read_trim(`${RUN}/update-action`);
	let result = ctx.read_trim(`${RUN}/update-result`);
	let c = ctx.uci();
	let until = +(c.get('e5-infoscreen', 'main', 'update_defer_until') ?? 0);
	let deferred = latest?.version == c.get('e5-infoscreen', 'main', 'update_defer_version') && until > time();
	let error = result == 'failed' ? ctx.read_trim(`${RUN}/update.log`) : null;
	return {
		current, latest,
		available: compatible && latest != null && newer(latest.version, current),
		incompatible: !!latest && !compatible,
		busy: running && action != 'check',
		checking: running && action == 'check',
		checked_at: +(ctx.read_trim(`${RUN}/update-checked-at`) ?? 0),
		deferred: !!deferred, deferred_until: deferred ? until : null,
		error: error ? substr(error, length(error) > 1000 ? length(error) - 1000 : 0) : null,
		action, result,
		backup: fs.stat('/etc/e5-infoscreen/update-backup.tar.gz') != null
	};
}

function start(action, version) {
	let s = state();
	if (s.busy || s.checking)
		return 'An update task is already running';
	if (!(action in ['check', 'apply', 'rollback']))
		return 'Unknown update action';
	if (action == 'apply' && (!s.available || (version != null && version != s.latest.version)))
		return 'The release has changed; check again';
	if (action == 'rollback' && !s.backup)
		return 'No update backup';
	ctx.run(`mkdir -p ${RUN}`);
	// Reserve before spawning: another request can arrive before the shell
	// child has even started and written its PID.
	if (fs.stat(LOCK) && !s.busy && !s.checking) {
		for (let name in ['pid', 'token', 'queued-at']) fs.unlink(`${LOCK}/${name}`);
		fs.rmdir(LOCK);
	}
	if (!fs.mkdir(LOCK, 0700))
		return 'An update task is already running';
	let tick = clock(true), token = `${tick[0]}${tick[1]}`;
	fs.writefile(`${LOCK}/token`, token);
	fs.writefile(`${LOCK}/queued-at`, `${time()}`);
	fs.writefile(`${RUN}/update-action`, action);
	fs.writefile(`${RUN}/update-result`, 'running');
	// The archive can replace these scripts. Run private copies so a future
	// release cannot change the shell program while it is executing.
	let work = `${RUN}/job-${token}`;
	fs.mkdir(work, 0700);
	fs.writefile(`${work}/update-job`, fs.readfile(JOB));
	fs.writefile(`${work}/update`, fs.readfile('/usr/libexec/e5-infoscreen/update'));
	ctx.run(`chmod 755 ${work}/update`);
	let version_arg = action == 'apply' ? s.latest.version : '-';
	if (ctx.run(`(/bin/sh ${work}/update-job ${action} ${version_arg} ${token} ${JOB}) >/dev/null 2>&1 &`) == 0)
		return null;
	for (let name in ['token', 'queued-at']) fs.unlink(`${LOCK}/${name}`);
	fs.rmdir(LOCK);
	for (let name in ['update-job', 'update']) fs.unlink(`${work}/${name}`);
	fs.rmdir(work);
	return 'Cannot start the update task';
}

function auto_check() {
	let s = state();
	let retry = s.action == 'check' && s.result == 'failed' ? 600 : 21600;
	if (!s.busy && !s.checking && (!s.checked_at || time() - s.checked_at >= retry)) {
		let error = start('check');
		if (!error)
			return { ...s, checking: true };
	}
	return s;
}

function defer(version) {
	let s = state();
	if (!s.available || version != s.latest.version || s.busy || s.checking)
		return 'The release has changed; check again';
	let c = ctx.uci();
	c.set('e5-infoscreen', 'main', 'update_defer_version', version);
	c.set('e5-infoscreen', 'main', 'update_defer_until', `${time() + 86400}`);
	return c.commit('e5-infoscreen') ? null : 'Cannot save the reminder';
}

return { state, start, auto_check, defer };
};
