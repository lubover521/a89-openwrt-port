#!/usr/bin/python3
"""Authenticated LuCI wallpaper RPC; only fixed lock/desktop PNG destinations."""
import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib

STORE = Path('/etc/e5-infoscreen/wallpapers')
WEB = Path('/usr/share/e5-infoscreen/www/wallpapers')
MAX_PNG = 650000
CHUNK = 12288  # base64 is 16 KiB, below the HTTP/ubus request boundary
UPLOADS = Path('/tmp/t551m-wallpaper-uploads')
METHODS = {'wallpaper_get': {'target':'String'},
           'wallpaper_set': {'target':'String','png':'String'},
           'wallpaper_read': {'target':'String','offset':'String','revision':'String'},
           'wallpaper_upload': {'target':'String','token':'String','offset':'String','png':'String'},
           'wallpaper_finish': {'target':'String','token':'String'},
           'wallpaper_reset': {'target':'String'}}


def validate_png(data):
    if len(data) > MAX_PNG or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Expected a PNG image under 650 KB')
    pos, chunks, raw, ended = 8, [], bytearray(), False
    while pos + 12 <= len(data):
        size = struct.unpack_from('>I',data,pos)[0]
        kind = data[pos+4:pos+8]
        if size > MAX_PNG or pos+12+size > len(data):
            raise ValueError('Truncated PNG')
        body = data[pos+8:pos+8+size]
        crc = struct.unpack_from('>I',data,pos+8+size)[0]
        if binascii.crc32(kind+body) & 0xffffffff != crc:
            raise ValueError('Invalid PNG checksum')
        chunks.append(kind)
        if len(chunks)==1:
            if kind != b'IHDR' or size != 13:
                raise ValueError('Missing PNG header')
            w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',body)
            if (w,h)!=(320,480) or depth!=8 or color not in (2,6) or compression or filtering or interlace:
                raise ValueError('Expected a 320x480 RGB/RGBA non-interlaced image')
            expected = h*(1+w*(3 if color==2 else 4))
        elif kind==b'IHDR':
            raise ValueError('Duplicate PNG header')
        if kind==b'IDAT':raw.extend(body)
        if kind==b'IEND':
            if size or pos+12!=len(data):raise ValueError('Invalid PNG ending')
            ended=True
            break
        if kind[0]<97 and kind not in (b'IHDR',b'IDAT',b'PLTE'):
            raise ValueError('Unsupported PNG chunk')
        pos+=size+12
    if not ended or not raw:raise ValueError('Incomplete PNG')
    decoder=zlib.decompressobj()
    pixels=decoder.decompress(raw,expected+1)
    if len(pixels)!=expected or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid PNG pixel data')
    stride=expected//480
    if any(pixels[n]>4 for n in range(0,expected,stride)):
        raise ValueError('Invalid PNG filter')


def setup():
    STORE.mkdir(parents=True,exist_ok=True)
    STORE.chmod(0o755)
    if WEB.is_symlink():
        if WEB.resolve()!=STORE.resolve():raise ValueError('Unexpected wallpaper link')
    elif not WEB.exists():
        WEB.symlink_to(STORE,target_is_directory=True)
    else:raise ValueError('Wallpaper web path is already occupied')


def config(target,mode,revision=''):
    subprocess.run(['uci','set',f'e5-infoscreen.main.{target}_wallpaper={mode}'],check=True,capture_output=True)
    subprocess.run(['uci','set',f'e5-infoscreen.main.{target}_wallpaper_rev={revision}'],check=True,capture_output=True)
    subprocess.run(['uci','commit','e5-infoscreen'],check=True,capture_output=True)


def store_image(target, data):
    validate_png(data)
    revision=hashlib.sha256(data).hexdigest()[:16]
    temporary=STORE/(target+'.new')
    with temporary.open('wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o644)
    os.replace(temporary,STORE/(target+'.png'))
    config(target,'custom',revision)
    return {'ok':True,'revision':revision}


def offset_arg(args):
    value=args.get('offset','')
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,6}',value):
        raise ValueError('Invalid chunk offset')
    offset=int(value)
    if offset>MAX_PNG:raise ValueError('Image too large')
    return offset


def upload_path(target,token):
    if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f]{32}',token):
        raise ValueError('Invalid upload token')
    return UPLOADS/(target+'-'+token+'.part')


def call(method,args):
    target=args.get('target')
    if target not in ('lock','desktop'):raise ValueError('Invalid wallpaper target')
    path=STORE/(target+'.png')
    if method in ('wallpaper_get','wallpaper_read'):
        if not path.exists():return {'ok':True,'custom':False}
        data=path.read_bytes()
        validate_png(data)
        revision=hashlib.sha256(data).hexdigest()[:16]
        if method=='wallpaper_read':
            if args.get('revision')!=revision:raise ValueError('Wallpaper changed; reload the preview')
            offset=offset_arg(args)
            if offset>=len(data) or offset%CHUNK:raise ValueError('Invalid chunk offset')
            part=data[offset:offset+CHUNK]
            return {'ok':True,'png':base64.b64encode(part).decode(),'next':offset+len(part),'done':offset+len(part)==len(data)}
        return {'ok':True,'custom':True,'png':base64.b64encode(data).decode() if len(data)<=CHUNK else None,
                'bytes':len(data),'revision':revision}
    setup()
    with open('/run/t551m-wallpaper.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if method=='wallpaper_upload':
            offset=offset_arg(args)
            encoded=args.get('png')
            if not isinstance(encoded,str) or not encoded or len(encoded)>CHUNK*4//3:
                raise ValueError('Invalid image chunk')
            part=base64.b64decode(encoded,validate=True)
            if not part or len(part)>CHUNK or offset+len(part)>MAX_PNG:raise ValueError('Image too large')
            UPLOADS.mkdir(mode=0o700,parents=True,exist_ok=True)
            token=args.get('token')
            if not token:
                if offset:raise ValueError('Invalid initial chunk offset')
                for old in UPLOADS.glob('*.part'):
                    if re.fullmatch(r'(lock|desktop)-[0-9a-f]{32}\.part',old.name) and time.time()-old.stat().st_mtime>600:
                        old.unlink()
                if len(list(UPLOADS.glob('*.part')))>=8:raise ValueError('Too many pending uploads; retry later')
                token=os.urandom(16).hex()
                upload_path(target,token).touch(mode=0o600,exist_ok=False)
            path=upload_path(target,token)
            with path.open('r+b') as stream:
                size=path.stat().st_size
                if offset!=size:
                    # Retrying an acknowledged chunk is safe; never duplicate it.
                    stream.seek(offset)
                    if offset+len(part)==size and stream.read()==part:
                        return {'ok':True,'token':token,'next':size}
                    raise ValueError('Out-of-order image chunk')
                stream.seek(offset);stream.write(part)
            return {'ok':True,'token':token,'next':offset+len(part)}
        if method=='wallpaper_finish':
            path=upload_path(target,args.get('token'))
            data=path.read_bytes()
            result=store_image(target,data)
            path.unlink()
            return result
        if method=='wallpaper_set':
            encoded=args.get('png')
            if not isinstance(encoded,str) or len(encoded)>870000:raise ValueError('Image too large')
            data=base64.b64decode(encoded,validate=True)
            return store_image(target,data)
        if method=='wallpaper_reset':
            config(target,'default')
            path.unlink(missing_ok=True)
            return {'ok':True}
        raise ValueError('Unknown method')


def main():
    os.umask(0o077)
    if sys.argv[1:] == ['setup']:
        setup();return
    if sys.argv[1:] == ['list']:
        print(json.dumps(METHODS));return
    try:
        if len(sys.argv)!=3 or sys.argv[1]!='call' or sys.argv[2] not in METHODS:
            raise ValueError('Unknown RPC')
        raw=sys.stdin.buffer.read(900001)
        if len(raw)>900000:raise ValueError('Request too large')
        args=json.loads(raw)
        if not isinstance(args,dict):raise ValueError('Expected an object')
        result=call(sys.argv[2],args)
    except (ValueError,OSError,KeyError,subprocess.SubprocessError,zlib.error) as error:
        result={'ok':False,'error':str(error)}
    print(json.dumps(result))


if __name__=='__main__':main()
