// ucode test with a fake command runner. Never opens AT or calls ModemManager.
'use strict';
let commands = [], rc = 0;
let voice = loadfile(ARGV[0], { raw_mode: true })()({
    sh: function(command) {
        push(commands, command);
        return `mock result\n__E5_VOICE_RC__${rc}\n`;
    }
});
function check(condition, message) { if (!condition) die(message); }
for (let tone in [ '', '12', 'a', '; reboot', '\n', null, 2 ]) {
    check(!voice.dtmf('12', tone).ok, 'Invalid tone accepted');
}
for (let id in [ null, '', '12;reboot', 'x', '../12' ])
    check(!voice.dtmf(id, '1').ok, 'Invalid call accepted');
check(length(commands) == 0, 'Invalid input reached the command runner');
for (let tone in [ '0', '1', '9', '*', '#' ]) {
    check(voice.dtmf('12', tone).ok, 'Valid tone failed');
    let command = commands[length(commands) - 1];
    check(index(command, "-o '/org/freedesktop/ModemManager1/Call/12'") >= 0, 'Wrong call target');
    check(index(command, `--send-dtmf='${tone}'`) >= 0, 'Tone was not safely quoted');
}
rc = 1;
let result = voice.dtmf('12', '#');
check(!result.ok && result.stage == 'dtmf', 'Failure was hidden');
check(length(commands) == 6, 'Tone was retried');
print('DTMF validation, exact call targeting, quoting and no retry: PASS\n');
