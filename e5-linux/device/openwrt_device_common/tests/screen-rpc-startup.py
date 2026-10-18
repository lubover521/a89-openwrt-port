#!/usr/bin/env python3
"""Screen RPC must start even if the audio DSP never becomes ready."""
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'overlay/usr/libexec/e5-voice-audio'
loader = importlib.machinery.SourceFileLoader('voice_startup', str(source))
spec = importlib.util.spec_from_loader(loader.name, loader)
voice = importlib.util.module_from_spec(spec)
loader.exec_module(voice)
started = []


class WaitingForDSP(Exception):
    pass


def wait(_):
    assert started == ['events'], 'Screen RPC is blocked behind audio firmware'
    raise WaitingForDSP


with patch.dict('sys.modules', {
    'e5_call_volume': SimpleNamespace(Volume=lambda: object()),
    'e5_call_events': SimpleNamespace(CallEvents=lambda: started.append('events')),
}), patch.object(voice.Path, 'exists', lambda p: p.name == 'calls.js'), \
        patch.object(voice.time, 'sleep', wait):
    try:
        voice.main()
    except WaitingForDSP:
        pass
    else:
        raise AssertionError('Expected the unchanged DSP wait')
print('Screen RPC starts while audio hardware is unavailable: PASS')
