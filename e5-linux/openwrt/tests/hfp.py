#!/usr/bin/env python3
"""HFP protocol, exact-call actions and audio-route failure regression tests."""
import asyncio
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'openwrt/overlay/usr/lib/e5/vendor/dbus_next-0.2.3-py3-none-any.whl'))
sys.path.insert(0, str(ROOT/'openwrt/overlay/usr/lib/e5'))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT/path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


hfp = load('hfp', 'openwrt/overlay/usr/libexec/e5-hfp')
voice = load('voice', 'openwrt/overlay/usr/libexec/e5-voice-audio')
hwmod = load('hardware', 'rootfs/overlay/opt/e5/e5-call-audio.py')


async def protocol():
    gateway = hfp.Gateway(None)
    gateway.publish = lambda: None
    gateway.battery_at = float('inf')
    class Volume:
        level=6
        writes=[]
        def get(self): return self.level
        def change(self,command,level):
            if level!=self.level: self.writes.append(level)
            self.level=level
    gateway.volume=Volume()
    actions, preferences, sent = [], [], []
    async def control(call, method, *args): actions.append((call['id'], method, args))
    gateway.control = control
    gateway.prefer_bluetooth = preferences.append
    s, remote = socket.socketpair()
    headset = hfp.Headset(gateway, '/device', s, {'Address':'00:11:22:33:44:55','Adapter':'/adapter'})
    gateway.peer = headset
    async def send(*lines): sent.extend(lines)
    headset.send = send
    calls = []
    with patch.object(hfp, 'call_list', lambda: calls):
        for command in ['AT+BRSF=127', 'AT+CIND=?', 'AT+CIND?', 'AT+CMER=3,0,0,1']:
            await headset.command(command)
        assert headset.ready and '+BRSF: 608' in sent
        await headset.notify(calls)
        assert '+VGS: 6' in sent and headset.remote_volume
        sent.clear(); await headset.notify(calls)
        assert not sent, 'unchanged gain generated repeated HFP traffic'
        await headset.command('AT+VGS=3')
        assert gateway.volume.level==3 and gateway.volume.writes==[3]
        sent.clear(); await headset.notify(calls)
        assert not sent, 'headset gain report was echoed back'
        await headset.command('AT+VGM=0')
        assert gateway.volume.level==3
        await headset.command('AT+VGS=16')
        assert sent[-1]=='ERROR' and gateway.volume.level==3
        # Idle button must not dial, redial, answer, or infer a nonexistent call.
        for command in ['ATA', 'AT+CHUP', 'AT+BLDN', 'ATD10010;', 'AT+VTS=1']:
            await headset.command(command)
            assert sent[-1] == 'ERROR'
        assert not actions
        calls[:] = [{'id':'7','state':'ringing-in','direction':'incoming','number':'+123','card':1}]
        headset.clip = True
        await headset.notify(calls)
        assert 'RING' in sent and '+CIEV: 3,1' in sent
        await headset.command('ATA')
        assert actions == [('7','Accept',())] and preferences == ['7']
        calls[0]['state'] = 'active'
        await headset.notify(calls)
        assert '+CIEV: 2,1' in sent and '+CIEV: 3,0' in sent
        await headset.command('AT+VTS=#')
        assert actions[-1] == ('7','SendDtmf',('s',['#']))
        await headset.command('AT+CLCC')
        assert '+CLCC: 8,1,0,0,0,"+123",145' in sent
        await headset.command('AT+CHUP')
        assert actions[-1][1] == 'Hangup'
        # Both cards ringing: no guessed slot or destructive "hangup all".
        calls[:] = [{'id':'8','state':'ringing-in'}, {'id':'9','state':'ringing-in'}]
        count = len(actions)
        await headset.command('ATA'); await headset.command('AT+CHUP')
        assert len(actions) == count and sent[-1] == 'ERROR'
        await headset.command('AT+BAC=1,2')
        headset.codec_requested = 2
        await headset.command('AT+BCS=1')
        assert not headset.codec_ready.is_set()
        await headset.command('AT+BCS=2')
        assert headset.codec == 2 and headset.codec_ready.is_set()
        calls.clear(); await headset.notify(calls)
        assert '+CIEV: 2,0' in sent
    headset.close(); remote.close()
    # Verify exact call revalidation uses ModemManager, not cached UI guesses.
    real = hfp.Gateway(None); methods = []
    async def dbus(dest,path,interface,member,signature='',body=None):
        methods.append((path,member))
        if member == 'GetAll': return [{'State':hfp.Variant('i',7)}]
        raise AssertionError('terminated call must not be acted upon')
    real.dbus = dbus
    try: await real.control({'id':'4'},'Accept')
    except RuntimeError: pass
    else: raise AssertionError('stale accept allowed')
    assert methods == [('/org/freedesktop/ModemManager1/Call/4','GetAll')]
    # Headsets require each result (including final OK) to have its own CRLF
    # envelope. Collapsing the envelopes stalled a real headset after BRSF.
    left,right=socket.socketpair();left.setblocking(False);right.setblocking(False)
    framing=hfp.Headset(gateway,'/device',left,{'Address':'00:11:22:33:44:55','Adapter':'/adapter'})
    await framing.send('+BRSF: 608','OK')
    data=await asyncio.get_running_loop().sock_recv(right,1024)
    assert data==b'\r\n+BRSF: 608\r\n\r\nOK\r\n'
    left.close();right.close()


class Hardware:
    def __init__(self): self.speaker=False; self.events=[]; self.volume=15
    def set_volume(self,value,remote=False): self.volume=value
    def start(self): self.events.append('start')
    def stop(self): self.events.append('stop'); self.speaker=False
    def set_route(self,route,rate=8000): self.events.append((route,rate)); self.speaker=route=='speaker'
    def mute(self,value): self.events.append(('mute',value))


class Bluetooth:
    def __init__(self): self.connected=True; self.fail=False; self.acquisitions=0; self.releases=0; self.button={}
    def status(self): return {'connected':self.connected,'connection':1,'device':'Test'}
    def intent(self): return self.button
    def acquire(self):
        self.acquisitions+=1
        if self.fail: raise RuntimeError('test SCO failure')
        return 16000
    def release(self): self.releases+=1


def routes():
    hw,bt=Hardware(),Bluetooth()
    ctl=voice.Controller(hw,lambda value:None,bt)
    call=[{'id':'7','state':'active'}]
    assert ctl.update(call,{})['route']=='bluetooth'
    assert ('bluetooth',16000) in hw.events
    choice={'route':'receiver','route_updated':time.time(),'muted':True}
    assert ctl.update(call,choice)['route']=='receiver'
    count=bt.acquisitions
    for _ in range(10): ctl.update(call,choice)
    assert bt.acquisitions==count, 'auto routing overrode the explicit phone choice'
    bt.button={'call':'7','updated':time.time()+.01}
    assert ctl.update(call,choice)['route']=='bluetooth'
    assert hw.events[-1]==('mute',True), 'switching audio lost mic mute'
    choice={'route':'receiver','route_updated':time.time()+.1}
    assert ctl.update(call,choice)['route']=='receiver'
    bt.button={};ctl.headset_intent=0
    bt.fail=True
    choice={'route':'bluetooth','route_updated':time.time()+1}
    state=ctl.update(call,choice)
    assert state['route']=='receiver' and state['error'] and state['active']
    count=bt.acquisitions
    for _ in range(10): ctl.update(call,choice)
    assert bt.acquisitions==count, 'failed SCO setup was retried continuously'
    bt.fail=False; choice['route_updated']+=1
    assert ctl.update(call,choice)['route']=='bluetooth'
    bt.connected=False
    assert ctl.update(call,choice)['route']=='receiver'
    assert not ctl.update([],choice)['active']


def mixers():
    # Route programming without opening hardware or a real call. Failure must
    # restore all prior controls, and SCO SRC must follow profile changes.
    hw=hwmod.VoiceHardware.__new__(hwmod.VoiceHardware)
    hw.speaker=False;hw.bluetooth=False;hw.bt_rate=8000;hw.band=1
    hw.volume=15;hw.remote_volume=False
    hw.volume_curves={}
    hw.codec_gains={};hw.applied_volume=None
    hw.handles=[object()]
    hw.saved={n:'original' for n in hw.controls()}
    state=hw.saved.copy();events=[]
    hw.get=lambda name: state[name]
    def put(name,value): state[name]=value;events.append((name,value))
    hw.put=put
    hw.set_route('bluetooth',16000)
    assert events.index(('S_VOICE_P_BT SWITCH','on')) < events.index(('S_VOICE_P_CODEC SWITCH','off'))
    assert events.index(('S_VOICE_C_BT SWITCH','on')) < events.index(('S_VOICE_C_CODEC SWITCH','off'))
    assert state['Speaker Function']=='off' and state['Earpiece Function']=='off'
    assert state['S_VOICE_P_CODEC SWITCH']=='off' and state['S_VOICE_C_CODEC SWITCH']=='off'
    assert state['VBC_SRC_BT_ADC']=='16000' and state['VBC_SRC_BT_DAC']=='16000'
    assert state['DSP VBC Profile Select']==(30<<24 | 30<<16 | 5)
    assert events.index(('VBC_SRC_BT_ADC','16000')) > events.index(('NXP Profile Select',30<<24 | 30<<16 | 5))
    events.clear();hw.set_route('receiver')
    assert events.index(('S_VOICE_P_CODEC SWITCH','on')) < events.index(('S_VOICE_P_BT SWITCH','off'))
    assert events.index(('S_VOICE_C_CODEC SWITCH','on')) < events.index(('S_VOICE_C_BT SWITCH','off'))
    assert state['S_VOICE_C_CODEC SWITCH']=='on' and not hw.bluetooth
    original=state.copy()
    failed=[False]
    def fail_once(name,value):
        if name=='VBC_MUX_ADC2' and not failed[0]: failed[0]=True;raise RuntimeError('test route failure')
        put(name,value)
    hw.put=fail_once
    try: hw.set_route('bluetooth',8000)
    except RuntimeError: pass
    else: raise AssertionError('failure swallowed')
    assert not hw.bluetooth and state==original, 'failed switch did not roll back'


def cancellation():
    import threading
    began,finish,cleaned=threading.Event(),threading.Event(),threading.Event()
    class SlowLease:
        def acquire(self): began.set();finish.wait(2);raise RuntimeError('canceled')
        def cancel(self): finish.set()
        def release(self): cleaned.set()
    with patch.object(voice,'SCOLease',SlowLease):
        bt=voice.BluetoothLink()
        before=time.monotonic()
        assert bt.acquire() is None and time.monotonic()-before<.1
        assert began.wait(1)
        bt.release()
        assert cleaned.wait(1), 'canceling a pending route leaked media suspension'
        bt.worker.shutdown(wait=True)


def completion_wake():
    import threading
    connected, wake = threading.Event(), threading.Event()
    class Lease:
        released=False
        def acquire(self): connected.wait(2); return 16000
        def cancel(self): connected.set()
        def release(self): self.released=True
    with patch.object(voice,'SCOLease',Lease):
        bt=voice.BluetoothLink(wake.set)
        assert bt.acquire() is None
        assert not wake.is_set()
        connected.set()
        assert wake.wait(1), 'SCO completion still waits for periodic poll'
        assert bt.acquire()==16000
        client=bt.client
        bt.release();bt.worker.shutdown(wait=True)
        assert client.released
    hw,bt=Hardware(),Bluetooth()
    def start():
        assert bt.acquisitions, 'SCO negotiation started after PCM setup'
        hw.events.append('start')
    hw.start=start
    ctl=voice.Controller(hw,lambda value:None,bt)
    assert ctl.update([{'id':'7','state':'active'}],{})['route']=='bluetooth'
    # PCM setup failure must release the negotiation started in parallel.
    def failed_start(): raise RuntimeError('PCM failed')
    hw,bt=Hardware(),Bluetooth();hw.start=failed_start
    ctl=voice.Controller(hw,lambda value:None,bt)
    assert ctl.update([{'id':'7','state':'active'}],{})['error']=='PCM failed'
    assert bt.releases==1


asyncio.run(protocol())
routes();mixers();cancellation();completion_wake()
print('PASS: HFP SLC/ring/answer/end/DTMF/codec negotiation, exact-call guards, route ownership/fallback/mute and DSP rollback')
