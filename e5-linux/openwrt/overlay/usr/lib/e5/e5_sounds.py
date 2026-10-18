"""Bounded PCM notification assets shared by LuCI, ringing and SMS delivery."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import struct
import subprocess
import time

STORE = Path('/etc/e5-sounds')
RUN = Path('/run/e5-sounds')
BUILTIN = Path('/usr/share/e5')
CONFIG = Path('/etc/config')
PLAYER = '/usr/libexec/e5-notification-sound'
RATE = 32000
CHUNK = 12288
SECONDS = {'ring': 30, 'sms': 5}
TONES = {'ring': ('call', 'beep', 'custom'), 'sms': ('ding', 'custom')}
METHODS = {'status': {}, 'configure': {'target': '', 'enabled': True, 'tone': ''},
           'upload': {'target': '', 'token': '', 'offset': '', 'data': ''},
           'finish': {'target': '', 'token': '', 'name': ''},
           'reset': {'target': ''}, 'preview': {'target': ''}, 'stop': {}}


def target_arg(value):
    if value not in SECONDS:
        raise ValueError('Invalid sound target')
    return value


def json_read(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def atomic(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    with temporary.open('wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate_wav(data, target):
    """Only the canonical mono PCM16 WAV emitted by the web converter."""
    target_arg(target)
    if len(data) < 46 or len(data) > 44 + RATE * 2 * SECONDS[target]:
        raise ValueError('Sound is empty or too long')
    if data[:4] != b'RIFF' or data[8:16] != b'WAVEfmt ' or data[36:40] != b'data':
        raise ValueError('Expected canonical PCM WAV')
    size, = struct.unpack_from('<I', data, 4)
    fmt, codec, channels, rate, byte_rate, align, bits = struct.unpack_from('<IHHIIHH', data, 16)
    count, = struct.unpack_from('<I', data, 40)
    if (fmt, codec, channels, rate, byte_rate, align, bits) != (16, 1, 1, RATE, RATE * 2, 2, 16):
        raise ValueError('Expected 32000 Hz mono PCM16')
    if size != len(data)-8 or count != len(data)-44 or count % 2 or count < RATE // 10:
        raise ValueError('Invalid WAV length')
    return count / (RATE * 2)


def cfg(key, fallback):
    result = subprocess.run(['uci', '-q', 'get', key], capture_output=True, text=True, timeout=3)
    return result.stdout.strip() if result.returncode == 0 else fallback


def setting(target):
    target_arg(target)
    if target == 'ring':
        return {'enabled': cfg('e5-plugin-phone.settings.ring_sound', '1') == '1',
                'tone': cfg('e5-plugin-phone.settings.ring_tone', 'call')}
    return {'enabled': cfg('e5-notify.sms.sound', '1') == '1',
            'tone': cfg('e5-notify.sms.tone', 'ding')}


def configure(target, enabled, tone):
    target_arg(target)
    if type(enabled) is not bool or tone not in TONES[target]:
        raise ValueError('Invalid sound setting')
    if tone == 'custom' and custom(target) is None:
        raise ValueError('Upload a sound first')
    package, section, kind = ('e5-plugin-phone', 'settings', 'settings') if target == 'ring' else ('e5-notify', 'sms', 'sms')
    sound_key, tone_key = ('ring_sound', 'ring_tone') if target == 'ring' else ('sound', 'tone')
    # UCI cannot create a previously absent package through `set` alone.
    (CONFIG / package).touch(mode=0o600, exist_ok=True)
    # All interpolated values are validated enums, booleans, or fixed strings.
    batch = f'set {package}.{section}={kind}\nset {package}.{section}.{sound_key}={int(enabled)}\nset {package}.{section}.{tone_key}={tone}\ncommit {package}\n'
    subprocess.run(['uci', 'batch'], input=batch, text=True, check=True, capture_output=True, timeout=5)


def custom(target):
    info = json_read(STORE / (target + '.json'), {})
    rev = info.get('revision', '')
    if not isinstance(rev, str) or not re.fullmatch(r'[a-f0-9]{64}', rev):
        return None
    path = STORE / (target + '-' + rev + '.wav')
    try:
        data = path.read_bytes()
        duration = validate_wav(data, target)
        if hashlib.sha256(data).hexdigest() != rev:
            return None
    except (OSError, ValueError):
        return None
    return {'path': path, 'revision': rev, 'name': str(info.get('name', 'Custom sound'))[:80], 'duration': duration}


def resolve(target, tone=None):
    target_arg(target)
    tone = tone or setting(target)['tone']
    if tone == 'custom':
        info = custom(target)
        if info:
            return info['path']
    default = 'call' if target == 'ring' else 'ding'
    if target == 'ring' and tone == 'beep':
        default = 'beep'
    return BUILTIN / (default + '.wav')


def status():
    result = {'ok': True, 'targets': {}}
    for target in SECONDS:
        info = custom(target)
        state = setting(target)
        if state['tone'] not in TONES[target] or state['tone'] == 'custom' and not info:
            state['tone'] = TONES[target][0]
        state.update(custom=info is not None, name=info['name'] if info else '',
                     duration=info['duration'] if info else None, max_seconds=SECONDS[target])
        result['targets'][target] = state
    result['volume'] = cfg('e5-audio.main.volume', '10')
    result['busy_call'] = call_busy('sms')
    return result


def upload_path(target, token):
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ValueError('Invalid upload token')
    return RUN / ('upload-' + target + '-' + token)


def upload(args):
    target = target_arg(args.get('target'))
    token, offset, chunk = args.get('token', ''), args.get('offset'), args.get('data')
    if not isinstance(offset, str) or not re.fullmatch(r'[0-9]{1,7}', offset):
        raise ValueError('Invalid upload offset')
    offset = int(offset)
    if not isinstance(chunk, str) or not 0 < len(chunk) <= CHUNK * 4 // 3:
        raise ValueError('Invalid upload chunk')
    data = base64.b64decode(chunk, validate=True)
    if offset + len(data) > 44 + RATE * 2 * SECONDS[target]:
        raise ValueError('Sound is too large')
    if not token:
        if offset:
            raise ValueError('First chunk must start at zero')
        # At most one staged upload per kind. Bounded RAM, no timer service.
        for old in RUN.glob('upload-' + target + '-*'):
            old.unlink()
        token = secrets.token_hex(16)
        upload_path(target, token).touch(mode=0o600, exist_ok=False)
    path = upload_path(target, token)
    if time.time() - path.stat().st_mtime > 600 or path.stat().st_size != offset:
        raise ValueError('Upload expired or offset mismatch')
    with path.open('ab') as stream:
        stream.write(data)
    return {'ok': True, 'token': token, 'next': offset + len(data)}


def finish(args):
    target = target_arg(args.get('target'))
    path = upload_path(target, args.get('token'))
    if time.time() - path.stat().st_mtime > 600:
        raise ValueError('Upload expired')
    data = path.read_bytes()
    duration = validate_wav(data, target)
    revision = hashlib.sha256(data).hexdigest()
    name = args.get('name', '')
    if not isinstance(name, str):
        raise ValueError('Invalid sound name')
    name = ''.join(c for c in name if ord(c) >= 32 and c != '\x7f')[:80] or 'Custom sound'
    output = STORE / (target + '-' + revision + '.wav')
    atomic(output, data)
    metadata = STORE / (target + '.json')
    previous = metadata.read_bytes() if metadata.exists() else None
    atomic(metadata, json.dumps({'revision': revision, 'name': name}).encode())
    try:
        configure(target, setting(target)['enabled'], 'custom')
    except Exception:
        if previous is None:
            metadata.unlink(missing_ok=True)
        else:
            atomic(metadata, previous)
        if not custom(target) or custom(target)['path'] != output:
            output.unlink(missing_ok=True)
        raise
    path.unlink()
    for old in STORE.glob(target + '-*.wav'):
        if old != output:
            old.unlink()
    return {'ok': True, 'revision': revision, 'duration': duration}


def call_busy(target):
    state = json_read(Path('/run/e5-voice-audio/status.json'), {})
    # Do not play on top of a live CP route even when the observer is stale.
    if state.get('active'):
        return True
    blocked = {'dialing', 'ringing-out', 'active', 'held'}
    if target != 'ring':
        blocked |= {'ringing-in', 'waiting'}
    return any(call.get('state') in blocked for call in state.get('calls', []))


def stop_preview():
    path = RUN / 'preview.pid'
    try:
        pid = int(path.read_text())
        cmd = Path('/proc') / str(pid) / 'cmdline'
        parts = cmd.read_bytes().split(b'\0')
        if PLAYER.encode() in parts and b'preview' in parts and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    path.unlink(missing_ok=True)


def dispatch(method, args):
    if method not in METHODS or not isinstance(args, dict):
        raise ValueError('Invalid sound request')
    RUN.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (RUN / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if method == 'status':
            return status()
        if method == 'upload':
            return upload(args)
        if method == 'finish':
            return finish(args)
        if method == 'stop':
            stop_preview()
            return {'ok': True}
        target = target_arg(args.get('target'))
        if method == 'configure':
            configure(target, args.get('enabled'), args.get('tone'))
        elif method == 'reset':
            stop_preview()
            configure(target, setting(target)['enabled'], TONES[target][0])
            (STORE / (target + '.json')).unlink(missing_ok=True)
            for old in STORE.glob(target + '-*.wav'):
                old.unlink()
        elif method == 'preview':
            if call_busy('sms'):
                raise ValueError('Preview unavailable during calls')
            if cfg('e5-audio.main.volume', '10') == '0':
                raise ValueError('Device volume is muted')
            stop_preview()
            process = subprocess.Popen([PLAYER, 'preview', target], start_new_session=True,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (RUN / 'preview.pid').write_text(str(process.pid))
        return {'ok': True}


def play(target, tone=None, preview=False):
    target_arg(target)
    RUN.mkdir(mode=0o700, parents=True, exist_ok=True)
    if call_busy('sms' if preview else target):
        return
    if not preview and not setting(target)['enabled']:
        return
    if cfg('e5-audio.main.volume', '10') == '0':
        return
    path = resolve(target, tone)
    with (RUN / ('play-' + ('preview' if preview else target) + '.lock')).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        # Resume the PCM/DSP before restoring volume, not after it. Otherwise
        # a cold first playback can open the path with its startup gains.
        subprocess.run(['/usr/libexec/e5-volume', 'prepare'], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if call_busy('sms' if preview else target):
            return
        env = dict(os.environ, PULSE_SERVER='unix:/var/run/pulse/native')
        # Same group as RingAlert's owned helper: answer/hangup kills the whole
        # playback. No per-message daemon, no changes to voice mixer controls.
        child = subprocess.Popen(['paplay', str(path)], env=env)
        deadline = time.monotonic() + (8 if preview else SECONDS[target] + 1)
        try:
            while child.poll() is None:
                if time.monotonic() >= deadline or call_busy('sms' if preview else target):
                    break
                time.sleep(.2)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
