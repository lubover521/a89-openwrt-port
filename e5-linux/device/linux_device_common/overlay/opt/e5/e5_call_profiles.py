"""Opt-in local-call gain range, loaded into DSP RAM from this unit's profile."""
import os
from pathlib import Path
import stat
import struct

LOCAL_MODES = (0, 2, 4, 5, 7, 9, 11, 12)
HEADER = struct.Struct('<16sII')


def quieter_low_steps(original, attenuation):
    if not 0 <= attenuation <= 36:
        raise ValueError('call low-volume attenuation must be 0..36 dB')
    if len(original) < HEADER.size:
        raise ValueError('truncated audio profile')
    magic, count, size = HEADER.unpack_from(original)
    if (magic.rstrip(b'\0') != b'audio_profile' or size != 0x2da or
            not 13 <= count <= 256 or len(original) != HEADER.size + count * size):
        raise ValueError('unsupported audio structure layout')
    result = bytearray(original)
    for mode in LOCAL_MODES:
        offset = HEADER.size + mode * size + 0x244
        gains = struct.unpack_from('<7H', original, offset)
        if not all(gains):
            raise ValueError('invalid local-call gain table')
        # Taper the extra attenuation to zero at the existing maximum.
        adjusted = [min(gains[i], gains[-1], max(1, round(
            gains[i] * 10 ** (-attenuation * (6 - i) / 120)))) for i in range(7)]
        # Some factory tables are not monotonic. Only lower outliers; never
        # raise a factory step or modify uplink/DTMF/Bluetooth coefficients.
        for i in range(5, -1, -1):
            adjusted[i] = min(adjusted[i], adjusted[i + 1])
        struct.pack_into('<7H', result, offset, *adjusted)
    return bytes(result)


def prepare(config=Path('/etc/e5/call-low-volume-attenuation-db'),
            firmware=Path('/lib/firmware/audio_structure'),
            device=Path('/dev/vbc_turning0')):
    try:
        attenuation = int(config.read_text().strip())
    except FileNotFoundError:
        return None  # Existing boards keep their calibrated behavior.
    original = firmware.read_bytes()
    desired = quieter_low_steps(original, attenuation)
    # This vendor interface consumes one complete blob per write, not a
    # stream. Validate the live allocation before sending any bytes to it.
    if not stat.S_ISCHR(device.stat().st_mode):
        raise ValueError('audio tuning interface is not a character device')
    fd = os.open(device, os.O_RDWR | os.O_CLOEXEC)
    try:
        current = os.read(fd, len(original))
        if current == desired:
            return desired  # No repeated attenuation after service restarts.
        if current != original:
            raise ValueError('live audio profile differs from this unit\'s factory profile')
        if os.write(fd, desired) != len(desired):
            raise OSError('short audio tuning write')
        if os.read(fd, len(desired)) != desired:
            raise OSError('audio tuning readback mismatch')
    finally:
        os.close(fd)
    return desired
