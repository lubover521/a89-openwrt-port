#!/usr/bin/env python3
from pathlib import Path
import json, os, subprocess

top=Path(__file__).resolve().parents[2]
helper=top/'openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/wifi-hostapd-clients'
clients={'02:AA:BB:CC:DD:01':{'assoc':True},'02:aa:bb:cc:dd:02':{'assoc':False,'auth':True},
         'ff:ff:ff:ff:ff:ff':{'assoc':True},'00:00:00:00:00:00':{'assoc':True},
         'invalid':{'assoc':True},'02:aa:bb:cc:dd:03':{'assoc':1}}
for data,status,expected in (({'clients':clients},0,'02:aa:bb:cc:dd:01||||\n02:aa:bb:cc:dd:03||||\n'),
                             ({'clients':{}},0,''),({},1,''),(None,1,''),([],1,''),({'clients':[]},1,'')):
    p=subprocess.run([os.environ.get('UCODE','ucode'),str(helper)],input=json.dumps(data),text=True,capture_output=True)
    assert p.returncode==status,(p.returncode,p.stderr)
    assert p.stdout==expected,p.stdout
print('PASS: hostapd JSON, associated-only counting, valid empty list vs unavailable, no lease/metric fabrication')
