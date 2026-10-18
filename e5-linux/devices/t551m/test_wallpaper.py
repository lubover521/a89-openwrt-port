"""Validate real PNG framing, decompression bounds and image dimensions."""
import binascii
import base64
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import os
import zlib

spec=importlib.util.spec_from_file_location('wallpaper',Path(__file__).with_name('infoscreen')/'wallpaper-rpc.py')
wallpaper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wallpaper)


def png(width=320,height=480,body=None):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    raw=body if body is not None else (b'\0'+b'\x40\x90\xc0'*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


class WallpaperTest(unittest.TestCase):
    def test_accept_canvas_size_rgb(self):wallpaper.validate_png(png())
    def test_reject_nonimage(self):
        for data in (b'<svg onload="evil()"/>',b'<html/>',b''):
            with self.assertRaises(ValueError):wallpaper.validate_png(data)
    def test_reject_dimensions(self):
        with self.assertRaises(ValueError):wallpaper.validate_png(png(1,1))
    def test_reject_truncation_and_crc(self):
        data=png()
        for bad in (data[:-1], data[:50]+bytes([data[50]^1])+data[51:]):
            with self.assertRaises(ValueError):wallpaper.validate_png(bad)
    def test_reject_extra_pixel_data_and_bad_filters(self):
        for data in (png(body=b'\0'*1000000),png(body=(b'\x05'+b'\0'*960)*480)):
            with self.assertRaises(ValueError):wallpaper.validate_png(data)
    def test_reject_append_and_target_traversal(self):
        with self.assertRaises(ValueError):wallpaper.validate_png(png()+b'junk')
        with self.assertRaises(ValueError):wallpaper.call('wallpaper_set',{'target':'../system','png':''})

    def test_large_chunk_roundtrip_and_incomplete_upload_preserves_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=root/'images';store.mkdir()
            original=png();(store/'desktop.png').write_bytes(original)
            data=png(body=b''.join(b'\0'+os.urandom(960) for _ in range(480)))
            self.assertGreater(len(data),400000)
            lock=root/'lock'
            real_open=open
            def redirected(path,*args,**kwargs):
                return real_open(lock if path=='/run/t551m-wallpaper.lock' else path,*args,**kwargs)
            with patch.object(wallpaper,'STORE',store), patch.object(wallpaper,'UPLOADS',root/'uploads'), patch.object(wallpaper,'setup'), patch.object(wallpaper,'config') as config, patch('builtins.open',redirected):
                token=''
                for offset in range(0,len(data),wallpaper.CHUNK):
                    args={'target':'desktop','token':token,'offset':str(offset),'png':base64.b64encode(data[offset:offset+wallpaper.CHUNK]).decode()}
                    result=wallpaper.call('wallpaper_upload',args)
                    token=result['token']
                    self.assertEqual((store/'desktop.png').read_bytes(),original)
                    # Repeat a chunk (lost reply) without duplicating bytes.
                    self.assertEqual(wallpaper.call('wallpaper_upload',{**args,'token':token})['next'],result['next'])
                config.assert_not_called()
                result=wallpaper.call('wallpaper_finish',{'target':'desktop','token':token})
                self.assertTrue(result['ok']);config.assert_called_once()
                meta=wallpaper.call('wallpaper_get',{'target':'desktop'})
                self.assertIsNone(meta['png'])
                recovered=bytearray()
                while len(recovered)<meta['bytes']:
                    part=wallpaper.call('wallpaper_read',{'target':'desktop','offset':str(len(recovered)),'revision':meta['revision']})
                    recovered.extend(base64.b64decode(part['png']))
                self.assertEqual(recovered,data)
                with self.assertRaises(ValueError):
                    wallpaper.call('wallpaper_read',{'target':'desktop','offset':'0','revision':'old'})

    def test_reject_bad_chunk_inputs(self):
        for token in ['../etc/config','x'*32,'0'*33,None]:
            with self.assertRaises(ValueError):wallpaper.upload_path('lock',token)
        for offset in ['-1','1.2','x','650001',1]:
            with self.assertRaises(ValueError):wallpaper.offset_arg({'offset':offset})


if __name__=='__main__':unittest.main()
