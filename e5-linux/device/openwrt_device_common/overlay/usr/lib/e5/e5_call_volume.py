"""Persistent call volume, separate from media; no audio or modem operations."""
import fcntl
import json
from pathlib import Path
import subprocess
import threading
import time

MAX = 15
DEFAULT = 15  # Preserve the previously fixed call gain until explicitly changed.
CONFIG = Path('/etc/config/e5-audio')
DELTA = Path('/tmp/.uci/e5-audio')
LOCK = Path('/run/e5-call-volume.lock')
STATUS = Path('/run/e5-voice-audio/status.json')


class Volume:
    def __init__(self):
        self.signature = None
        self.level = DEFAULT
        self.lock = threading.RLock()

    def get(self):
        with self.lock:
            return self._get()

    def _get(self):
        signature = []
        for path in (CONFIG, DELTA):
            try:
                st = path.stat()
                signature.append((st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size))
            except FileNotFoundError:
                signature.append(None)
        if signature != self.signature:
            try:
                result = subprocess.run(['uci', '-q', 'get', 'e5-audio.main.call_volume'],
                                        capture_output=True, text=True, timeout=3)
            except (OSError, subprocess.SubprocessError):
                return self.level  # Retry later; never drop HFP on a config error.
            try: level = int(result.stdout.strip())
            except ValueError: level = DEFAULT
            self.level = max(0, min(MAX, level))
            self.signature = signature
        return self.level

    def change(self, command, value=None):
        # Serialize headset buttons and screen keys, including read-modify-write.
        with self.lock, LOCK.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            old = self.get()
            level = old + 1 if command == 'up' else old - 1 if command == 'down' else int(value)
            level = max(0, min(MAX, level))
            if level != old:
                try:
                    subprocess.run(['uci', '-q', 'batch'], input=(
                        "set e5-audio.main=audio\n"
                        f"set e5-audio.main.call_volume='{level}'\n"
                        "commit e5-audio\n"), text=True, check=True, timeout=3)
                except (OSError, subprocess.SubprocessError) as error:
                    raise RuntimeError('Cannot save call volume') from error
                self.level = level
                self.signature = None
            return level


def call_status():
    try:
        state = json.loads(STATUS.read_text())
        if isinstance(state, dict) and 0 <= time.time() - state.get('updated', 0) < 5:
            return state
    except (OSError, ValueError, TypeError):
        pass
    return {}
