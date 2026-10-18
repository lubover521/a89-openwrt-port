"""Physical supply transitions for the screen; kernel events, no polling."""
from pathlib import Path
import socket


class PowerEvents:
    def __init__(self, root=Path('/sys/class/power_supply')):
        self.root = root
        self.socket = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
        try:
            self.socket.bind((0, 1))  # NETLINK_KOBJECT_UEVENT, kernel multicast
            self.socket.setblocking(False)
            self.states = self.snapshot()
        except Exception:
            self.socket.close()
            raise

    def snapshot(self):
        states = {}
        for supply in self.root.glob('*'):
            try:
                kind = (supply / 'type').read_text().strip()
                # Battery.online is battery presence, not charger attachment.
                if kind in ('Mains', 'Wireless') or kind.startswith('USB'):
                    states[supply.name] = (supply / 'online').read_text().strip() == '1'
            except OSError:
                pass
        return states

    def consume(self, data, sender):
        if sender[0] != 0:
            return False
        fields = dict(part.split('=', 1) for part in data.decode('utf-8', 'replace').split('\0') if '=' in part)
        if fields.get('SUBSYSTEM') != 'power_supply':
            return False
        current = self.snapshot()
        name, online = fields.get('POWER_SUPPLY_NAME'), fields.get('POWER_SUPPLY_ONLINE')
        # Preserve a queued disconnect even when sysfs already shows the next
        # connection. Merely sampling the aggregate online flag loses this.
        if name in current and online in ('0', '1'):
            current[name] = online == '1'
        changed = any(name in self.states and value != self.states[name]
                      for name, value in current.items())
        self.states = current
        return changed

    def receive(self):
        data, sender = self.socket.recvfrom(16384)
        return self.consume(data, sender)

    def close(self):
        self.socket.close()
