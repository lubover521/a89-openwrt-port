"""Call/media dispatch, saved gain and config caching without real hardware."""
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'overlay/usr/lib/e5'))
import e5_call_volume as volume
loader = importlib.machinery.SourceFileLoader('call_volume_cli', str(ROOT/'overlay/usr/libexec/e5-call-volume'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    config, delta, status = root/'config', root/'delta', root/'status'
    config.write_text('media volume 3')
    reads, writes, saved = [], [], [15]
    def uci(argv, **kwargs):
        if argv[-1] == 'batch':
            lines = kwargs['input'].splitlines()
            assert lines[0] == 'set e5-audio.main=audio'
            assert '.main.volume=' not in kwargs['input'], 'call keys overwrote media'
            saved[0] = int(lines[1].split("'")[1]); writes.append(saved[0])
            config.write_text('saved call '+str(saved[0]))
            return SimpleNamespace(returncode=0, stdout='')
        reads.append(argv)
        return SimpleNamespace(returncode=0, stdout=str(saved[0]))
    with patch.multiple(volume, CONFIG=config, DELTA=delta, LOCK=root/'lock', STATUS=status), \
         patch.object(volume.subprocess, 'run', side_effect=uci):
        control = volume.Volume()
        for _ in range(100): assert control.get() == 15
        assert len(reads) == 1
        assert control.change('down') == 14 and writes == [14]
        assert control.get() == 14
        control.change('set', 14)
        assert writes == [14], 'unchanged headset reports wrote flash'
        saved[0] = 5; delta.write_text('staged')
        assert control.get() == 5, 'staged sound setting was cached forever'
        delta.unlink(); saved[0] = 0
        assert control.get() == 0
        count = len(writes)
        control.change('down'); assert len(writes) == count
        for data in ({}, {'active': True, 'updated': time.time()-6},
                     {'active': False, 'updated': time.time()}):
            status.write_text(json.dumps(data))
            with redirect_stdout(io.StringIO()) as out:
                assert cli.main(['auto', 'up']) == 3
                assert not out.getvalue()
        status.write_text(json.dumps({'active': True, 'available': True,
                                     'route': 'bluetooth', 'updated': time.time()}))
        with redirect_stdout(io.StringIO()) as out:
            assert cli.main(['auto', 'up']) == 0
        value = json.loads(out.getvalue())
        assert value['kind'] == 'call' and value['level'] == 1 and value['output'] == 'bluetooth'
        assert writes[-1] == 1
        try: cli.main(['set', '1;reboot'])
        except ValueError: pass
        else: raise AssertionError('invalid gain accepted')
        # Transient UCI failures retain the last known gain and retry later.
        config.write_text('changed again; different size for coarse filesystem timestamps')
        with patch.object(volume.subprocess, 'run', side_effect=subprocess.TimeoutExpired('uci',3)):
            assert control.get() == 0
        assert control.get() == 1, (control.level, saved, reads, writes)
print('PASS: call/media isolation, stale-state fallback, limits, staged config, cache and no redundant flash writes')
