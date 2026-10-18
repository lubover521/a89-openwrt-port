"""Native DSP volume selection uses the loaded calibration, not DAC readback."""
import importlib.util
from pathlib import Path
import struct
import tempfile

source=Path(__file__).resolve().parents[1]/'overlay/opt/e5/e5-call-audio.py'
spec=importlib.util.spec_from_file_location('hardware',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    profile=Path(directory)/'audio_structure'
    blob=bytearray(struct.pack('<16sII',b'audio_profile',12,0x2da)+bytes(12*0x2da))
    # Deliberately nonmonotonic SWB entry and duplicate levels. The previous
    # maximum is index7; selecting the louder index4 would invert the volume UI.
    curve=(649,817,1154,10289,2053,2584,4096)
    struct.pack_into('<7H',blob,24+11*0x2da+0x244,*curve)
    profile.write_bytes(blob)
    hw=module.VoiceHardware.__new__(module.VoiceHardware)
    hw.volume_curves=hw.load_volume_curves(profile)
    hw.band=2;hw.speaker=True;hw.bluetooth=False
    steps=[]
    for level in range(1,16):
        hw.volume=level;steps.append(hw.dsp_volume())
    assert 4 not in steps and steps[0]==1 and steps[-1]==7
    audible=[curve[s-1] for s in steps]
    assert audible==sorted(audible) and max(audible)==curve[-1]
    assert len(set(audible))>=6, 'volume remained fixed at maximum'
    hw.bluetooth=True
    for level in range(16):
        hw.volume=level
        assert hw.dsp_volume()==7, 'changed the acoustically confirmed HFP path'
    profile.write_bytes(blob[:-2])
    assert hw.load_volume_curves(profile)=={}
    profile.write_bytes(struct.pack('<16sII',b'audio_profile',12,0x100)+bytes(12*0x100))
    assert hw.load_volume_curves(profile)=={}, 'guessed offsets in unknown AS layout'
print('PASS: native DSP gain varies, calibrated curve monotonic/capped, Bluetooth unchanged, invalid layout rejected')
with tempfile.TemporaryDirectory() as directory:
    codec=Path(directory)/'codec.xml'
    codec.write_text('''<codec><Audio><Handset><WB1 mode="2">
        <dacl_playback_volume><volume6 val="0x3"/></dacl_playback_volume>
        <ear_playback_volume><volume6 val="0x1"/></ear_playback_volume>
        </WB1></Handset><Handsfree><WB1 mode="9">
        <dacs_playback_volume><volume6 val="0x0"/></dacs_playback_volume>
        <ao_playback_volume><volume6 val="0x2"/></ao_playback_volume>
        </WB1></Handsfree></Audio></codec>''')
    gains=module.VoiceHardware.load_codec_gains(codec)
    assert gains[2]['ear_playback_volume']==1 and gains[9]['ao_playback_volume']==2
    codec.write_text('<!DOCTYPE codec [<!ENTITY bad "3">]><codec/>')
    assert module.VoiceHardware.load_codec_gains(codec)=={}
print('PASS: per-unit codec calibration and XML validation')
with tempfile.TemporaryDirectory() as directory:
    wiring=Path(directory)/'receiver-output'
    assert module.VoiceHardware.load_receiver_output(wiring)=='receiver'
    for value, expected in [('speaker\n','speaker'),('receiver\n','receiver'),('invalid','receiver')]:
        wiring.write_text(value)
        assert module.VoiceHardware.load_receiver_output(wiring)==expected
print('PASS: receiver wiring capability and legacy default')
hw=module.VoiceHardware.__new__(module.VoiceHardware)
hw.receiver_output='speaker';hw.speaker=False;hw.bluetooth=False;hw.band=1;hw.volume=1
hw.volume_curves={2:(20,10,30,40,50,60,70),9:(10,20,30,40,50,60,70)}
assert hw.speaker_path and hw.dsp_volume()==2, 'phone used the handsfree DSP curve'
hw.speaker=True
assert hw.dsp_volume()==1
print('PASS: shared transducer retains independent handset/handfree DSP curves')
hw.volume_curves={2:(4,10,26,65,205,579,1029),9:(7,29,103,365,1295,12953,23034)}
hw.speaker=False;hw.volume=5
reference=hw.dsp_volume()
hw.receiver_volume_ceiling=5;hw.volume=15
assert hw.dsp_volume()==reference, 'phone maximum exceeded equivalent level 5'
steps=[]
for level in range(1,16):
    hw.volume=level;steps.append(hw.dsp_volume())
assert steps==sorted(steps) and steps[-1]==reference
hw.speaker=True;hw.volume=15
assert hw.dsp_volume()==7, 'phone ceiling restricted handsfree'
hw.speaker=False;hw.bluetooth=True
assert hw.dsp_volume()==7, 'phone ceiling restricted Bluetooth'
with tempfile.TemporaryDirectory() as directory:
    ceiling=Path(directory)/'ceiling'
    assert module.VoiceHardware.load_receiver_volume_ceiling(ceiling)==15
    ceiling.write_text('5\n')
    assert module.VoiceHardware.load_receiver_volume_ceiling(ceiling)==5
    for value in ('0','16','invalid'):
        ceiling.write_text(value)
        try: module.VoiceHardware.load_receiver_volume_ceiling(ceiling)
        except ValueError: pass
        else: raise AssertionError('invalid phone ceiling accepted')
print('PASS: phone ceiling, monotonic range, full handsfree/Bluetooth and unchanged board defaults')
