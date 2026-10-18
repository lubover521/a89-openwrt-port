#!/usr/bin/python3
"""Attach the tested E5 hostless audio backend to ModemManager call state.

This process never starts, accepts, deletes, or hangs up a call. It only holds
FE_ST_VOICE during existing calls and restores media routing when they end.
"""
import importlib.util
import concurrent.futures
import ctypes as C
import json
import logging
import os
from pathlib import Path
import queue
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

RUN = Path('/run/e5-voice-audio')
LIVE = {'dialing', 'ringing-out', 'active', 'held'}
CALL_PATH = '/org/freedesktop/ModemManager1/Call/'


class CallBus:
    """Read-only, persistent GDBus client using the same GLib as ModemManager.

    No GI/Python extension is needed. GIO owns transport and marshalling; every
    reply/child/error reference is released, and all reads keep the 3s timeout.
    """
    DEST = b'org.freedesktop.ModemManager1'
    ROOT = '/org/freedesktop/ModemManager1'
    VOICE = 'org.freedesktop.ModemManager1.Modem.Voice'
    CALL = 'org.freedesktop.ModemManager1.Call'
    STATES = ['unknown','dialing','ringing-out','ringing-in','active','held','waiting','terminated']
    REASONS = ['unknown','outgoing-started','incoming-new','accepted','terminated',
               'refused-or-busy','error','audio-setup-failed','transferred','deflected']

    class Error(C.Structure):
        _fields_ = [('domain', C.c_uint32), ('code', C.c_int), ('message', C.c_char_p)]

    def __init__(self):
        self.lib = C.CDLL('libgio-2.0.so.0')
        self.connection = None
        self.modem = None
        P, S, I = C.c_void_p, C.c_char_p, C.c_int
        def bind(name, result, *args):
            fn = getattr(self.lib, name); fn.restype = result; fn.argtypes = list(args)
            setattr(self, name, fn)
        bind('g_bus_get_sync', P, I, P, C.POINTER(P))
        bind('g_dbus_connection_set_exit_on_close', None, P, I)
        bind('g_dbus_connection_is_closed', I, P)
        bind('g_dbus_connection_call_sync', P, P, S, S, S, S, P, P, I, I, P, C.POINTER(P))
        bind('g_object_unref', None, P)
        bind('g_error_free', None, P)
        bind('g_variant_new_string', P, S)
        bind('g_variant_new_tuple', P, C.POINTER(P), C.c_size_t)
        bind('g_variant_get_type_string', S, P)
        bind('g_variant_n_children', C.c_size_t, P)
        bind('g_variant_get_child_value', P, P, C.c_size_t)
        bind('g_variant_unref', None, P)
        bind('g_variant_get_string', S, P, P)
        for name, kind in [('boolean', I), ('byte', C.c_ubyte), ('int16', C.c_int16),
                           ('uint16', C.c_uint16), ('int32', C.c_int32), ('uint32', C.c_uint32),
                           ('int64', C.c_int64), ('uint64', C.c_uint64), ('double', C.c_double), ('handle', I)]:
            bind('g_variant_get_' + name, kind, P)

    def close(self):
        if self.connection:
            self.g_object_unref(self.connection)
        self.connection = None
        self.modem = None

    def error(self, error):
        if not error.value:
            return RuntimeError('D-Bus request failed')
        try:
            message = C.cast(error, C.POINTER(self.Error)).contents.message
            return RuntimeError(message.decode(errors='replace'))
        finally:
            self.g_error_free(error)

    def unpack(self, value):
        kind = self.g_variant_get_type_string(value).decode()
        if kind in ('s','o','g'):
            return self.g_variant_get_string(value, None).decode()
        scalars = {'b':'boolean','y':'byte','n':'int16','q':'uint16','i':'int32',
                   'u':'uint32','x':'int64','t':'uint64','d':'double','h':'handle'}
        if kind in scalars:
            result = getattr(self, 'g_variant_get_' + scalars[kind])(value)
            return bool(result) if kind == 'b' else result
        items = []
        for i in range(self.g_variant_n_children(value)):
            child = self.g_variant_get_child_value(value, i)
            try: items.append(self.unpack(child))
            finally: self.g_variant_unref(child)
        if kind == 'v': return items[0]
        if kind.startswith('a{'): return dict(items)
        if kind.startswith(('(', '{')): return tuple(items)
        if kind.startswith('a'): return items
        raise ValueError('Unsupported D-Bus type: ' + kind)

    def call(self, path, interface, method, *strings):
        error = C.c_void_p()
        if self.connection and self.g_dbus_connection_is_closed(self.connection):
            self.close()
        if not self.connection:
            self.connection = self.g_bus_get_sync(1, None, C.byref(error))  # system bus
            if not self.connection: raise self.error(error)
            self.g_dbus_connection_set_exit_on_close(self.connection, False)
        values = (C.c_void_p * len(strings))(*[self.g_variant_new_string(s.encode()) for s in strings])
        parameters = self.g_variant_new_tuple(values, len(strings))  # floating, consumed by GIO
        reply = self.g_dbus_connection_call_sync(self.connection, self.DEST, path.encode(),
                    interface.encode(), method.encode(), parameters, None, 1, 3000, None, C.byref(error))
        if not reply:
            self.modem = None
            raise self.error(error)
        try: return self.unpack(reply)[0]
        finally: self.g_variant_unref(reply)

    @staticmethod
    def enum(names, value):
        return names[value] if isinstance(value, int) and 0 <= value < len(names) else 'unknown'

    def query(self, *args):
        if args[0] == '-m':
            if self.modem is None:
                objects = self.call(self.ROOT, 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects')
                self.modem = next((p for p in sorted(objects) if self.VOICE in objects[p]), None)
                if self.modem is None: raise RuntimeError('No voice modem available')
            paths = self.call(self.modem, 'org.freedesktop.DBus.Properties', 'Get', self.VOICE, 'Calls')
            return {'modem.voice.calls': paths}
        properties = self.call(args[1], 'org.freedesktop.DBus.Properties', 'GetAll', self.CALL)
        return {'call': {'properties': {
            'state': self.enum(self.STATES, properties.get('State')),
            'state-reason': self.enum(self.REASONS, properties.get('StateReason')),
            'direction': self.enum(['unknown','incoming','outgoing'], properties.get('Direction')),
            'number': properties.get('Number', ''), 'sim-slot': properties.get('SimSlot')}}}


def mm_json(*args):
    result = subprocess.run(['mmcli', '-J', '--timeout=3', *args], capture_output=True,
                            text=True, timeout=5, check=True)
    return json.loads(result.stdout)


def calls(terminated=None, query=None):
    query = query or mm_json
    reply = query('-m', 'any', '--voice-list-calls')
    paths = reply.get('modem.voice.call', reply.get('modem.voice.calls',
                  reply.get('modem', {}).get('voice', {}).get('calls', [])))
    result = []
    if terminated is not None:
        terminated.intersection_update(paths)
    for path in paths:
        if not isinstance(path, str) or not path.startswith(CALL_PATH) or not path[len(CALL_PATH):].isdigit():
            continue
        if terminated is not None and path in terminated:
            continue
        call = query('-o', path).get('call', {}).get('properties', {})
        if call.get('state') == 'terminated' and terminated is not None:
            terminated.add(path)
            continue
        result.append({'id': path[len(CALL_PATH):], 'state': call.get('state'),
                       'reason': call.get('state-reason'), 'number': call.get('number'), 'direction': call.get('direction'),
                       'card': int(call['sim-slot'])-1 if str(call.get('sim-slot')) in ('1','2') else None,
                       'sim': 'SIM'+str(call['sim-slot']) if str(call.get('sim-slot')) in ('1','2') else None})
    return result


def watch_call_changes(stop, changed, reset):
    """Wake the observer on MM's authoritative D-Bus transitions, not a timer.

    This never owns an AT channel or infers hangup from an ambiguous CP URC.
    The periodic read remains a fallback if the monitor disconnects.
    """
    matches = ["type='signal',sender='org.freedesktop.ModemManager1',path_namespace='/org/freedesktop/ModemManager1/Call'",
               "type='signal',sender='org.freedesktop.ModemManager1',interface='org.freedesktop.ModemManager1.Modem.Voice'",
               "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.freedesktop.ModemManager1'"]
    while not stop.is_set():
        process = None
        try:
            process = subprocess.Popen(['dbus-monitor', '--system', '--profile', *matches],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            reset.set()
            changed.set()
            pending = b''
            while not stop.is_set() and process.poll() is None:
                if not select.select([process.stdout], [], [], .5)[0]:
                    continue
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                lines = (pending + chunk).split(b'\n')
                pending = lines.pop()
                for line in lines:
                    if line.startswith(b'sig'):
                        if b'NameOwnerChanged' in line:
                            reset.set()
                        changed.set()
        except OSError as error:
            logging.warning('call signal monitor: %s', error)
        finally:
            if process is not None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                process.stdout.close()
        stop.wait(1)


def write_json(path, value):
    RUN.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value) + '\n')
    os.replace(tmp, path)


def watch_audio_settings(stop, changed):
    """Wake on atomic screen/headset requests, without faster idle polling."""
    libc = C.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes, libc.inotify_init1.restype = [C.c_int], C.c_int
    libc.inotify_add_watch.argtypes = [C.c_int, C.c_char_p, C.c_uint32]
    libc.inotify_add_watch.restype = C.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        logging.warning('audio settings watch unavailable; using periodic fallback')
        return
    wanted = {RUN: b'settings.json', Path('/run/e5-hfp'): b'intent.json'}
    watches = {}
    try:
        while not stop.is_set():
            for path in wanted:
                if path not in watches.values():
                    wd = libc.inotify_add_watch(fd, os.fsencode(path), 0x0088 | 0x0c00)
                    if wd >= 0: watches[wd] = path  # CLOSE_WRITE / MOVED_TO / directory loss
            if not select.select([fd], [], [], .5)[0]: continue
            data, offset = os.read(fd, 8192), 0
            while offset + 16 <= len(data):
                wd, mask, cookie, size = struct.unpack_from('iIII', data, offset)
                name = data[offset+16:offset+16+size].split(b'\0', 1)[0]
                offset += 16 + size
                path = watches.get(wd)
                if path is not None and name == wanted[path]: changed.set()
                if mask & 0x8c00: watches.pop(wd, None)
    except OSError as error:
        logging.warning('audio settings watch: %s; using periodic fallback', error)
    finally:
        os.close(fd)


class Controller:
    def __init__(self, hardware, suspend, bluetooth=None):
        self.hardware, self.suspend = hardware, suspend
        self.bluetooth = bluetooth
        self.route = 'receiver'
        self.route_error = None
        self.route_pending = False
        self.failed_route = None
        self.headset_intent = 0
        self.bt_state = {}
        self.active = False
        self.error = None
        self.previous = {}
        self.muted = False
        self.card = None

    def update(self, observed, settings):
        now = {c['id']: c['state'] for c in observed}
        for call in observed:
            if self.previous.get(call['id']) != call['state']:
                logging.info('call=%s sim=%s state=%s reason=%s', call['id'], call.get('sim'), call['state'], call.get('reason'))
        self.previous = now
        active_calls = [c for c in observed if c['state'] in LIVE]
        active_calls.sort(key=lambda c: c['state'] != 'active')
        needed = bool(active_calls)
        card = active_calls[0].get('card') if needed else None
        self.bt_state = self.bluetooth.status() if self.bluetooth else {}
        try:
            self.hardware.set_volume(settings.get('volume', 15),
                                     self.bt_state.get('remote_volume', False))
            if needed and self.active and card is not None and self.card is not None and card != self.card:
                self.stop()
            if needed and not self.active:
                # Start SCO negotiation alongside local PCM setup. An explicit
                # local choice can also select its endpoint before PCM opens.
                self.select_route(settings, active_calls)
                self.suspend(True)
                try:
                    self.hardware.start()
                except Exception:
                    if self.bluetooth: self.bluetooth.release()
                    self.suspend(False)
                    raise
                self.active = True
                self.card = card
                self.muted = False
            if needed and self.active:
                route_changed = self.select_route(settings, active_calls)
                mute = bool(settings.get('muted', False))
                if mute != self.muted or route_changed:
                    self.hardware.mute(mute)
                    self.muted = mute
            if not needed and self.active:
                self.stop()
            self.error = None
        except Exception as error:
            self.error = str(error)
            logging.exception('voice audio operation failed')
        return self.status()

    def select_route(self, settings, active_calls):
        requested = settings.get('route', 'speaker' if settings.get('speaker') else 'auto')
        stamp = settings.get('route_updated', 0)
        if self.bluetooth:
            intent = self.bluetooth.intent()
            if intent.get('call') in [c['id'] for c in active_calls] and time.time() - intent.get('updated', 0) < 10:
                self.headset_intent = max(self.headset_intent, intent.get('updated', 0))
        if self.headset_intent > stamp: requested = 'bluetooth'
        connected = self.bt_state.get('connected', False)
        target = ('bluetooth' if connected else 'receiver') if requested == 'auto' else requested
        if target not in ('receiver', 'speaker', 'bluetooth'): target = 'receiver'
        key = (self.bt_state.get('connection'), requested, stamp, self.headset_intent)
        old = self.route
        self.route_error = None
        self.route_pending = False
        if target == 'bluetooth' and (not connected or self.failed_route == key):
            target = 'receiver'
            if requested == 'bluetooth': self.route_error = 'Bluetooth call audio unavailable; using phone'
        if target == 'bluetooth' and self.bluetooth:
            try:
                rate = self.bluetooth.acquire()
                if rate is None:
                    # Negotiation runs outside the call observer. Incoming,
                    # hangup and screen updates keep their existing cadence.
                    self.route_pending = True
                else:
                    self.hardware.set_route('bluetooth', rate)
                    self.route = 'bluetooth'
                    self.failed_route = None
            except Exception as error:
                self.bluetooth.release()
                self.failed_route = key
                self.route_error = 'Bluetooth: ' + str(error)
                logging.warning('Bluetooth route failed: %s', error)
                target = 'receiver'
        if target != 'bluetooth':
            if hasattr(self.hardware, 'set_route'): self.hardware.set_route(target)
            else: self.hardware.set_speaker(target == 'speaker')
            self.route = target
            if self.bluetooth: self.bluetooth.release()
        if old != self.route:
            logging.info('call audio route: %s -> %s', old, self.route)
        return old != self.route

    def stop(self):
        try:
            self.hardware.stop()
        finally:
            if self.bluetooth: self.bluetooth.release()
            self.active = False
            self.card = None
            self.muted = False
            self.route = 'receiver'
            self.failed_route = None
            self.headset_intent = 0
            self.route_pending = False
            self.route_error = None
            self.suspend(False)

    def status(self):
        return {'available': True, 'active': self.active, 'speaker': self.hardware.speaker,
                'muted': self.muted, 'error': self.error or self.route_error, 'pcm': 'hw:0,5',
                'route': self.route, 'bluetooth': self.bt_state,
                'route_pending': self.route_pending,
                'volume': self.hardware.volume, 'volume_max': 15,
                'card': self.card, 'sim': 'SIM'+str(self.card+1) if self.card is not None else None}


class SCOLease:
    """One root-only Unix lease owns SCO; closing the client releases it."""
    def __init__(self):
        self.lease = None
        self.rate = 8000
        self.sinks = []
        self.cancelled = threading.Event()

    @staticmethod
    def read(name):
        try:
            data = json.loads((Path('/run/e5-hfp') / name).read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError): return {}

    def status(self):
        value = self.read('status.json')
        return value if 0 <= time.time() - value.get('updated', 0) < 5 else {'connected': False}

    def intent(self): return self.read('intent.json')

    def acquire(self):
        if self.lease:
            # An SCO/profile loss closes the lease server-side; do not leave
            # a silent Bluetooth route selected merely because HFP is alive.
            if select.select([self.lease], [], [], 0)[0]:
                self.release()
                raise RuntimeError('Headset audio disconnected')
            return self.rate
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(9)
        self.lease = sock
        try:
            listing = subprocess.run(['pactl', 'list', 'sinks', 'short'], capture_output=True, text=True, timeout=3)
            for line in listing.stdout.splitlines():
                fields = line.split()
                if len(fields) > 1 and fields[1].startswith('bluez_sink.'):
                    r = subprocess.run(['pactl', 'suspend-sink', fields[1], '1'], capture_output=True, timeout=3)
                    if r.returncode == 0: self.sinks.append(fields[1])
            if self.cancelled.is_set(): raise RuntimeError('Audio request canceled')
            sock.connect('/run/e5-hfp/audio.sock')
            sock.sendall(b'{"acquire":true}\n')
            reply = b''
            while b'\n' not in reply and len(reply) < 2048:
                part = sock.recv(2048)
                if not part: raise RuntimeError('HFP gateway disconnected')
                reply += part
            result = json.loads(reply)
            if not result.get('ok'): raise RuntimeError(result.get('error', 'SCO failed'))
            if self.cancelled.is_set(): raise RuntimeError('Audio request canceled')
            self.rate = int(result['rate'])
            return self.rate
        except Exception:
            self.release()
            raise

    def cancel(self):
        self.cancelled.set()
        sock = self.lease
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()

    def release(self):
        if self.lease:
            self.lease.close()
            self.lease = None
        sinks, self.sinks = self.sinks, []
        for sink in sinks:
            try: subprocess.run(['pactl', 'suspend-sink', sink, '0'], capture_output=True, timeout=3)
            except (OSError, subprocess.TimeoutExpired): pass


class BluetoothLink:
    read = staticmethod(SCOLease.read)
    status = SCOLease.status
    intent = SCOLease.intent

    def __init__(self, wake=None):
        self.worker = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.future = self.client = None
        self.retiring = False
        self.wake = wake or (lambda: None)

    def acquire(self):
        if self.retiring:
            if not self.future.done(): return None
            self.release()
        if self.future is None:
            self.client = SCOLease()
            self.future = self.worker.submit(self.client.acquire)
            self.future.add_done_callback(lambda _: self.wake())
            return None
        if not self.future.done(): return None
        self.future.result()  # report the original negotiation error once
        return self.client.acquire()  # checks lease EOF without blocking

    def release(self):
        if not self.future: return
        if self.retiring and not self.future.done(): return
        if not self.future.done():
            self.retiring = True
            self.client.cancel()
            # Serialize cleanup after the connect worker even if cancellation
            # races its last instruction. A2DP cannot remain suspended.
            self.future = self.worker.submit(self.client.release)
            self.future.add_done_callback(lambda _: self.wake())
            return
        self.client.release()
        self.future = self.client = None
        self.retiring = False


def suspend_media(on):
    result = subprocess.run(['pactl', 'suspend-sink', 'speaker', '1' if on else '0'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        logging.warning('cannot %s media sink: %s', 'suspend' if on else 'resume', result.stderr.strip())



_alert_signature, _alert_values = None, None


def alert_settings():
    global _alert_signature, _alert_values
    signature = []
    for path in [Path('/etc/config/e5-plugin-phone'), Path('/tmp/.uci/e5-plugin-phone')]:
        try:
            st = path.stat()
            signature.append((st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size))
        except FileNotFoundError:
            signature.append(None)
    if _alert_values is not None and signature == _alert_signature:
        return _alert_values
    r = subprocess.run(['uci', '-q', 'show', 'e5-plugin-phone'], capture_output=True, text=True, timeout=3)
    values = {}
    for line in r.stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key.rsplit('.', 1)[-1]] = value.strip("'")
    result = {'sound': values.get('ring_sound', '1') == '1',
            'screen': values.get('ring_screen', '1') != '0',
            'vibrate': values.get('ring_vibrate', '1') == '1',
            'tone': values.get('ring_tone') if values.get('ring_tone') in ('beep', 'custom') else 'call'}
    if r.returncode == 0 or signature == [None, None]:
        _alert_signature, _alert_values = signature, result
    return result


class RingAlert:
    def __init__(self, spawn=None, clock=None):
        self.spawn = spawn or (lambda argv: subprocess.Popen(argv, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self.clock = clock or time.monotonic
        self.sound = self.vibration = None
        self.next = 0
        self.call_ids = set()

    @staticmethod
    def cancel(process):
        if process is not None and process.poll() is None:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass

    def stop(self):
        self.cancel(self.sound); self.cancel(self.vibration)
        self.sound = self.vibration = None
        self.next = 0
        self.call_ids = set()

    def update(self, observed, settings, voice_active):
        ids = {c['id'] for c in observed if c['state'] in {'ringing-in', 'waiting'}}
        if not ids:
            self.stop()
            return
        if not self.call_ids: logging.info('incoming call alert started')
        self.call_ids = ids
        if not settings.get('sound') or voice_active:
            self.cancel(self.sound); self.sound = None
        if not settings.get('vibrate'):
            self.cancel(self.vibration); self.vibration = None
        now = self.clock()
        if now < self.next: return
        # Only the ringing notification is repeated, never a call operation.
        self.next = now + 2.5
        if settings.get('sound') and not voice_active and (self.sound is None or self.sound.poll() is not None):
            tone = settings.get('tone') if settings.get('tone') in ('beep', 'custom') else 'call'
            self.sound = self.spawn(['/usr/libexec/e5-notification-sound', 'ring', tone])
        if settings.get('vibrate') and (self.vibration is None or self.vibration.poll() is not None):
            self.vibration = self.spawn(['e5-vibrate', '250', '150', '250'])


def main():
    sys.path.insert(0, '/usr/lib/e5')
    from e5_call_volume import Volume
    volume = Volume()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='e5-voice-audio: %(message)s')
    # Screen RPC serves network/settings as well as calls. Keep it available
    # even when audio hardware is absent or its firmware is still starting.
    events = None
    if Path('/usr/share/e5-infoscreen/www/calls.js').exists():
        try:
            from e5_call_events import CallEvents
            events = CallEvents()
        except (ImportError, OSError):
            logging.exception('call events unavailable; UI can use polling fallback')
    # Opening PCM before the firmware has booted can reset the audio domain.
    # e5-audio writes this boot-local marker only after DSP setup succeeds.
    while not Path('/run/e5-audio.ready').exists():
        time.sleep(1)
    spec = importlib.util.spec_from_file_location('e5_voice_hardware', '/opt/e5/e5-call-audio.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stop = threading.Event()
    changed, reset = threading.Event(), threading.Event()
    controller = Controller(module.VoiceHardware(), suspend_media, BluetoothLink(changed.set))
    ringer = RingAlert()
    terminated = set()
    try:
        bus = CallBus()
    except (OSError, AttributeError):
        bus = None
        logging.warning('GIO unavailable; using mmcli fallback')
    messages = queue.Queue()
    pipe_fd = None
    def notification_reader():
        nonlocal pipe_fd
        try:
            pipe_fd = os.open('/dev/audio_pipe_voice', os.O_RDWR)
            logging.info('DSP voice notification channel opened')
            while not stop.is_set():
                data = os.read(pipe_fd, 20)
                if len(data) != 20:
                    raise RuntimeError('short DSP voice notification')
                messages.put(struct.unpack('<HH4I', data))
                changed.set()
        except Exception as error:
            if not stop.is_set():
                logging.error('DSP notification listener: %s', error)

    def shutdown(*args):
        stop.set()
        changed.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(target=notification_reader, daemon=True).start()
    call_monitor = threading.Thread(target=watch_call_changes, args=(stop, changed, reset), daemon=True)
    call_monitor.start()
    last_settings = {'speaker': False, 'muted': False}
    write_json(RUN / 'settings.json', last_settings)
    settings_monitor = threading.Thread(target=watch_audio_settings, args=(stop, changed), daemon=True)
    settings_monitor.start()
    logging.info('ready; audio only, no modem call-control commands')
    try:
        while not stop.is_set():
            changed.clear()
            try:
                while not messages.empty():
                    command, channel, p0, p1, p2, p3 = messages.get_nowait()
                    logging.info('DSP cmd=%#x channel=%d params=%#x,%#x,%#x,%#x', command, channel, p0,p1,p2,p3)
                    if command == 0 and channel == 2:
                        controller.hardware.network(p0, p1)
                settings = json.loads((RUN / 'settings.json').read_text())
                settings['volume'] = volume.get()
                if reset.is_set():
                    terminated.clear()
                    if bus: bus.modem = None
                    reset.clear()
                observed = calls(terminated, bus.query if bus else None)
                alerts = alert_settings()
                ringer.update(observed, alerts, controller.active or any(c['state'] in LIVE for c in observed))
                was_active = controller.active
                state = controller.update(observed, settings)
                if was_active and not controller.active:
                    write_json(RUN / 'settings.json', last_settings)
                snapshot = {**state, 'updated': time.time(), 'calls': observed}
                write_json(RUN / 'status.json', snapshot)
                if events: events.publish(snapshot, alerts['screen'])
            except Exception as error:
                # A temporary D-Bus query failure must not tear down an active
                # audio route, and there is never a timer that hangs up calls.
                logging.error('state read: %s', error)
                snapshot = {**controller.status(), 'error': str(error), 'updated': time.time()}
                write_json(RUN / 'status.json', snapshot)
                if events: events.publish(snapshot)
            changed.wait(.5)
    finally:
        stop.set()
        call_monitor.join(timeout=3)
        settings_monitor.join(timeout=1)
        if bus: bus.close()
        ringer.stop()
        controller.stop()
        write_json(RUN / 'status.json', {**controller.status(), 'available': False, 'updated': time.time()})
        if events: events.close()


if __name__ == '__main__':
    main()
