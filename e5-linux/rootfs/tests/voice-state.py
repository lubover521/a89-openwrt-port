#!/usr/bin/env python3
"""Check voice setup/rollback without hardware or a modem."""
import importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'overlay/opt/e5/e5-call-audio.py'
spec=importlib.util.spec_from_file_location('voice_backend',p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Hardware(module.VoiceHardware):
    def __init__(self):
        self.values={name:'before-'+name for name in self.controls()}
        self.original=dict(self.values)
        self.events=[]
        self.saved={}; self.handles=[]; self.card=0; self.device=5
        self.speaker=False; self.band=0
        self.bluetooth=False; self.bt_rate=8000
        self.volume=15; self.remote_volume=False
        self.volume_curves={}
        self.codec_gains={}; self.applied_volume=None
    def get(self,name):return self.values[name]
    def put(self,name,value):self.values[name]=value; self.events.append(('put',name,value))
class Pcm:
    opened=[]
    def __init__(self,card,device,stream):
        self.closed=False; self.stream=stream; self.opened.append(self)
        hardware.events.append(('prepare',stream))
    def start(self):hardware.events.append(('start',self.stream))
    def close(self):self.closed=True
module.VoicePcm=Pcm
hardware=Hardware()
hardware.start()
assert len(hardware.handles)==2
assert hardware.values['VBC_VOLUME']==7
assert hardware.values['NXP Profile Select']==5
assert hardware.values['Speaker Function']=='off'
assert hardware.values['Earpiece Function']=='on'
assert hardware.values['EAR_HPL Mixer DACHPL Switch']=='on'
assert hardware.values['EAR Gain EAR Playback Volume']==2
assert hardware.values['VBC_DL_MUTE']=='disable'
assert hardware.values['VBC DAC1 DSP MDG Set']=='0,1024'
assert hardware.events.index(('prepare',1)) < hardware.events.index(('start',0))
assert hardware.events.index(('start',1)) < hardware.events.index(('put','VBC_DL_MUTE','disable'))
hardware.network(0x10,1)
assert hardware.values['NXP Profile Select']==0x02020005
hardware.start()
assert len(hardware.handles)==2
hardware.mute(True)
assert hardware.values['VBC ADC2 DG Set']=='0,0'
handles=list(hardware.handles)
hardware.set_speaker(True)
assert hardware.speaker
assert hardware.values['NXP Profile Select']==0x09090005
assert hardware.values['Speaker Function']=='on'
assert hardware.values['Earpiece Function']=='off'
assert hardware.values['EAR_HPL Mixer DACHPL Switch']=='off'
assert hardware.values['VBC ADC2 DG Set']=='0,0', 'speaker change lost mic mute'
hardware.set_route('bluetooth',16000)
assert hardware.bluetooth and hardware.values['VBC ADC2 DG Set']=='0,0'
bt_events=len(hardware.events)
hardware.set_speaker(False)
assert not hardware.bluetooth and hardware.values['VBC ADC2 DG Set']=='0,0'
assert ('put','VBC ADC2 DG Set','24,24') not in hardware.events[bt_events:], 'route change briefly unmuted mic'
assert not hardware.speaker
assert hardware.values['Speaker Function']=='off'
assert hardware.values['Earpiece Function']=='on'
assert hardware.values['NXP Profile Select']==0x02020005
assert hardware.handles==handles, 'output switch unnecessarily reopened voice'
# A route failure must restore the previous live output, including DSP mute.
before=dict(hardware.values)
put=hardware.put
failed=False
def fail_route_once(name,value):
    global failed
    if name=='HPL EAR Sel' and value=='HPL' and not failed:
        failed=True
        raise RuntimeError('route write failed')
    put(name,value)
hardware.put=fail_route_once
try:hardware.set_speaker(True)
except RuntimeError:pass
else:raise AssertionError('route failure was hidden')
assert hardware.values==before
assert not hardware.speaker
assert hardware.handles==handles
hardware.put=put
# Nonzero volume updates must not reissue DSP mute/unmute or analog switches.
hardware.set_volume(15)
hardware.events.clear()
hardware.set_volume(4)
assert hardware.events==[('put','VBC_VOLUME',2)], hardware.events
hardware.events.clear()
hardware.set_volume(5)  # same native step, no DSP command at all
assert not hardware.events, hardware.events
hardware.set_volume(15)
# Volume must change downlink only, without reopening PCM or resetting routes.
for route in ('receiver', 'speaker', 'bluetooth'):
    hardware.set_route(route)
    before_events=len(hardware.events)
    gains=[]; steps=[]
    for level in range(16):
        hardware.set_volume(level)
        gains.append(int(hardware.values['VBC DAC1 DG Set'].split(',')[0]))
        steps.append(hardware.values['VBC_VOLUME'])
        assert hardware.values['VBC ADC2 DG Set']=='0,0'
        assert hardware.values['VBC_DL_MUTE']==('disable' if level else 'enable')
    if route=='bluetooth':
        assert gains==[0]+list(range(10,25)) and set(steps)=={7}
    else:
        assert set(gains)=={24} and steps==sorted(steps) and set(steps)==set(range(1,8))
    assert all(e[1] in ('VBC_VOLUME','VBC DAC1 DG Set','VBC DAC1 DSP MDG Set','VBC_DL_MUTE')
               for e in hardware.events[before_events:])
    hardware.set_volume(0)
    hardware.network(0x10,2)
    assert hardware.values['VBC_DL_MUTE']=='enable', 'bandwidth change lost downlink mute'
    hardware.set_volume(4)
    assert hardware.handles==handles
# Remote HFP volume attenuates at the headset once, but zero still mutes DSP.
hardware.set_volume(4,remote=True)
assert hardware.values['VBC DAC1 DG Set']=='24,24'
hardware.set_speaker(False)
assert hardware.values['VBC DAC1 DG Set']=='24,24'
assert hardware.values['VBC_VOLUME']<7
hardware.set_volume(0,remote=True)
hardware.set_route('bluetooth',16000)
assert hardware.values['VBC_DL_MUTE']=='enable'
hardware.set_volume(15)
hardware.mute(False)
hardware.set_speaker(True)
hardware.stop()
assert not hardware.speaker, 'next call would retain speaker preference'
assert hardware.values==hardware.original
assert all(pcm.closed for pcm in Pcm.opened)
# Use this unit's analog gains, and restore codec framing after SCO/profile
# transitions; profile reapplication must not lose the native volume choice.
hardware=Hardware()
hardware.codec_gains={9:{'dacs_playback_volume':0,'ao_playback_volume':2},
                      2:{'dacl_playback_volume':3,'ear_playback_volume':1}}
hardware.band=1;hardware.set_volume(4);hardware.start()
assert hardware.values['EAR Gain EAR Playback Volume']==1
hardware.set_speaker(True)
assert hardware.values['AO Gain AO Playback Volume']==2
hardware.set_route('bluetooth',16000)
assert hardware.values['VBC_IIS_TX0_WD_SEL']=='WD_16BIT'
hardware.set_speaker(True)
assert hardware.values['VBC_IIS_TX0_WD_SEL']=='WD_24BIT'
assert hardware.values['VBC_IIS_RX2_WD_SEL']=='WD_24BIT'
assert hardware.values['DSP_DAC0_LR_EXCHANGE']=='enable'
assert hardware.values['VBC_VOLUME']==2
hardware.stop()
assert hardware.values==hardware.original
# An explicit pre-call choice may be recorded without changing media routing.
hardware=Hardware()
hardware.set_speaker(True)
assert hardware.values==hardware.original
hardware.start()
assert hardware.values['Speaker Function']=='on'
hardware.stop()
assert hardware.values==hardware.original and not hardware.speaker
# Shared hardware keeps the quieter handset DSP curve, the real amplifier's
# codec gains, logical phone selection, and microphone mute.
hardware=Hardware()
hardware.receiver_output='speaker'
hardware.band=1
hardware.codec_gains={9:{'dacs_playback_volume':0,'ao_playback_volume':2}}
hardware.set_volume(4)
hardware.start()
assert not hardware.speaker and hardware.speaker_path
assert hardware.values['Speaker Function']=='on'
assert hardware.values['Earpiece Function']=='off'
assert hardware.values['NXP Profile Select']==0x02020005
assert hardware.values['AO Gain AO Playback Volume']==2
assert hardware.values['VBC_VOLUME']==2
hardware.mute(True)
hardware.set_route('bluetooth',16000)
assert not hardware.speaker_path
assert hardware.values['Speaker Function']=='off'
assert hardware.values['NXP Profile Select']==0x1e1e0005
hardware.set_route('receiver')
assert not hardware.speaker and hardware.speaker_path
assert hardware.values['Speaker Function']=='on'
assert hardware.values['VBC ADC2 DG Set']=='0,0'
hardware.set_volume(0)
assert hardware.values['VBC_DL_MUTE']=='enable'
hardware.set_volume(4)
assert hardware.values['VBC_DL_MUTE']=='disable'
hardware.set_speaker(True)
assert hardware.values['NXP Profile Select']==0x09090005
hardware.stop()
assert hardware.values==hardware.original

class FailingPcm(Pcm):
    def __init__(self,card,device,stream):
        if stream==1:raise RuntimeError('capture setup failed')
        super().__init__(card,device,stream)
module.VoicePcm=FailingPcm
hardware=Hardware()
try:hardware.start()
except RuntimeError:pass
else:raise AssertionError('failure was hidden')
assert hardware.values==hardware.original
assert not hardware.handles
class FailingStartPcm(Pcm):
    def start(self):
        super().start()
        if self.stream==1:raise RuntimeError('capture start failed')
module.VoicePcm=FailingStartPcm
hardware=Hardware()
try:hardware.start()
except RuntimeError:pass
else:raise AssertionError('start failure was hidden')
assert hardware.values==hardware.original
assert not hardware.handles
assert ('put','VBC_DL_MUTE','disable') not in hardware.events
print('Voice state checks passed')
