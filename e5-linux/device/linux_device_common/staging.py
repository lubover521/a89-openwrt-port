"""Read deployment assets without applying text conversions to binary data."""
from pathlib import Path


def source_bytes(path):
    data = Path(path).read_bytes()
    # Binary assets (WAV, ELF, archives, images, translations, etc.) must
    # retain every byte, including any coincidental CRLF sample values.
    if b'\0' in data:
        return data
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    return data.replace(b'\r\n', b'\n')
