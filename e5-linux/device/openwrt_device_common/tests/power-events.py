"""Exercise kernel event classification, including swaps hidden by sysfs."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'overlay/usr/lib/e5'))
from e5_power_events import PowerEvents

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for name, kind, online in [('usb', 'USB', '1'), ('ac', 'Mains', '0'), ('battery', 'Battery', '1')]:
        supply = root / name
        supply.mkdir()
        (supply / 'type').write_text(kind)
        (supply / 'online').write_text(online)
    watcher = PowerEvents.__new__(PowerEvents)
    watcher.root = root
    watcher.states = watcher.snapshot()
    def event(name, online, sender=(0, 1), subsystem='power_supply'):
        data = f'change@/devices/test\0SUBSYSTEM={subsystem}\0POWER_SUPPLY_NAME={name}\0POWER_SUPPLY_ONLINE={online}\0'.encode()
        return watcher.consume(data, sender)
    assert not event('usb', '1'), 'initial/duplicate event woke screen'
    assert not event('battery', '0'), 'battery status woke screen'
    assert not event('usb', '0', sender=(123, 1)), 'userspace sender accepted'
    assert not event('usb', '0', subsystem='input'), 'unrelated event accepted'
    # Both events queued while sysfs already says online again.
    assert event('usb', '0')
    assert event('usb', '1')
    assert not event('usb', '1')
    (root / 'usb/online').write_text('0')
    (root / 'ac/online').write_text('1')
    assert event('ac', '1'), 'USB to mains swap was lost'
    assert not event('ac', '1'), 'charge current/status repeat woke screen'
    (root / 'ac/online').write_text('0')
    assert event('battery', '1'), 'driver without supply ONLINE payload lost detach'
print('Physical attach/detach, quick swap, duplicate/status filtering and sender checks PASS')
