#!/usr/bin/env python3
"""Exercise real libasound value marshalling with a fake control device."""
import ctypes as C
import importlib.util
from pathlib import Path
import threading

source = Path(__file__).resolve().parents[1] / 'overlay/opt/e5/e5-call-audio.py'
spec = importlib.util.spec_from_file_location('audio', source)
audio = importlib.util.module_from_spec(spec); spec.loader.exec_module(audio)
mixer = audio.AlsaControl.__new__(audio.AlsaControl)
mixer.lib = C.CDLL('libasound.so.2')
mixer.handle, mixer.lock, mixer.elements = None, threading.RLock(), {}
lib = mixer.lib
lib.snd_ctl_elem_value_malloc.argtypes = [C.POINTER(C.c_void_p)]
lib.snd_ctl_elem_value_malloc.restype = C.c_int
lib.snd_ctl_elem_value_free.argtypes = [C.c_void_p]
lib.snd_ctl_elem_value_free.restype = None
mixer.ctl_elem_value_free = lib.snd_ctl_elem_value_free
lib.snd_strerror.argtypes = [C.c_int]; lib.snd_strerror.restype = C.c_char_p
mixer.strerror = lib.snd_strerror
for name, result, arg in [('boolean', C.c_int, C.c_long),
                           ('integer', C.c_long, C.c_long),
                           ('enumerated', C.c_uint, C.c_uint)]:
    get = getattr(lib, 'snd_ctl_elem_value_get_' + name)
    get.argtypes, get.restype = [C.c_void_p, C.c_uint], result
    set_ = getattr(lib, 'snd_ctl_elem_value_set_' + name)
    set_.argtypes, set_.restype = [C.c_void_p, C.c_uint, arg], None
    setattr(mixer, 'ctl_elem_value_get_' + name, get)
    setattr(mixer, 'ctl_elem_value_set_' + name, set_)
states = {}; pointers = {}; writes = []; failure = [False]
def control(name, kind, values, choices=()):
    value = C.c_void_p()
    assert lib.snd_ctl_elem_value_malloc(C.byref(value)) == 0
    mixer.elements[name] = kind, len(values), choices, value
    states[name] = values
    pointers[value.value] = name
def transfer(handle, value, write=False):
    name = pointers[value.value]
    kind, count, choices, _ = mixer.elements[name]
    suffix = {1:'boolean', 2:'integer', 3:'enumerated'}[kind]
    if write:
        if failure[0]: return -5
        states[name] = [getattr(mixer, 'ctl_elem_value_get_' + suffix)(value, i) for i in range(count)]
        writes.append(name)
    else:
        for i, number in enumerate(states[name]):
            getattr(mixer, 'ctl_elem_value_set_' + suffix)(value, i, number)
    return 0
mixer.ctl_elem_read = transfer
mixer.ctl_elem_write = lambda handle, value: transfer(handle, value, True)
control('switch', 1, [0]); control('gain', 2, [24, 24])
control('profile', 2, [0]); control('enum', 3, [0], ['off', 'codec', 'bt'])
try:
    mixer.put('switch', 'on'); assert mixer.get('switch') == 'on'
    mixer.put('switch', '0'); assert mixer.get('switch') == 'off'
    mixer.put('gain', '4,8'); assert mixer.get('gain') == '4,8'
    mixer.put('gain', '0'); assert mixer.get('gain') == '0,0'
    states['gain'] = [7, 9]; assert mixer.get('gain') == '7,9', 'read used cached values'
    mixer.put('enum', 'bt'); assert mixer.get('enum') == '2'
    mixer.put('enum', '1'); assert mixer.get('enum') == '1'
    mixer.put('profile', 0x1e1e0005); assert mixer.get('profile') == str(0x1e1e0005)
    mixer.put('profile', -1); assert mixer.get('profile') == '-1'
    count = len(writes)
    for name, value in [('switch','2'), ('enum','3'), ('enum','missing'), ('gain','1,2,3')]:
        try: mixer.put(name, value)
        except ValueError: pass
        else: raise AssertionError('invalid value accepted')
    assert len(writes) == count
    failure[0] = True
    try: mixer.put('profile', 7)
    except RuntimeError: pass
    else: raise AssertionError('driver failure was hidden')
finally:
    mixer.close(); mixer.close()
print('PASS: native ALSA boolean/enum/multiple integers, raw profile values, fresh reads, validation, write failure and cleanup')
