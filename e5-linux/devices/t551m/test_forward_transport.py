"""OpenWrt integration: isolated inbox/config and stub transports, no real sends."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, urlsplit, unquote
import base64


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tools',type=Path,required=True)
    args=parser.parse_args(); tools=args.tools.resolve()
    with tempfile.TemporaryDirectory(prefix='forward-test-') as temp:
        root=Path(temp); bindir=root/'bin';bindir.mkdir()
        base=root/'config';base.mkdir();battery=root/'battery';battery.mkdir()
        (base/'native-v1').write_text('1\n')
        (battery/'capacity').write_text('40');(battery/'status').write_text('Discharging')
        (battery/'present').write_text('1')
        log=root/'deliveries'; inbox=root/'inbox.json';items=[]
        env=dict(os.environ,PATH=str(bindir)+':'+os.environ['PATH'],
                 MU300_FORWARD_DIR=str(base),MU300_FORWARD_RESULT=str(root/'result'),
                 MU300_FORWARD_RUNTIME=str(root),MU300_FORWARD_BATTERY=str(battery),
                 MU300_FORWARD_POLL='1',E5_SMS_DATA=str(root),
                 MU300_FORWARD_RENDERER=str(tools/'forward-template.uc'),
                 MU300_FORWARD_ANSWER=str(tools/'forward-answer.uc'),
                 E5_FORWARD_NATIVE=str(bindir/'native'),TEST_LOG=str(log),
                 TEST_NATIVE=str(tools/'forward-native'))
        def script(name,code):
            p=bindir/name;p.write_text(code);p.chmod(0o755)
        script('nslookup',"#!/bin/sh\nprintf 'Name: example.com\\nAddress: 8.8.8.8\\n'\n")
        script('curl','''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
assert a[a.index('--proto')+1]=='=https'
body=Path(a[a.index('--data-binary')+1][1:]).read_text() if '--data-binary' in a else ''
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps({'channel':'http','url':a[-1],'body':body,'args':a})+'\\n')
Path(a[a.index('-o')+1]).write_text('{"errcode":0}')
print('200',end='')
''')
        script('msmtp','''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:];cfg=Path(a[a.index('-C')+1]).read_text()
assert 'tls_certcheck on' in cfg and 'tls_host_override smtp.example.com' in cfg
assert 'passwordeval cat ' in cfg
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps({'channel':'smtp','body':sys.stdin.read()})+'\\n')
''')
        script('native','''#!/usr/bin/python3
import json,os,sys
if sys.argv[1]=='send':
 with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps({'channel':'sms','slot':os.environ.get('MU300_SIM_SLOT'),'to':sys.argv[2],'body':sys.argv[3]})+'\\n')
 print('{"ok":1}')
else:os.execv(os.environ['TEST_NATIVE'],[os.environ['TEST_NATIVE']]+sys.argv[1:])
''')
        def call(op,*values,payload=None):
            r=subprocess.run([str(tools/'sms-forward'),op,*map(str,values)],env=env,
                             input=json.dumps(payload) if payload is not None else '',
                             text=True,capture_output=True,timeout=15)
            assert r.returncode==0,(op,r.stderr,r.stdout)
            return json.loads(r.stdout) if r.stdout.strip() else {}
        def config(profile='shared',mode='shared',**changes):
            p=dict(profile=profile,mode=mode,enabled=1,method='webhook',template_language='en',
                   webhook_url='https://example.com/'+profile,webhook_method='POST',
                   webhook_body='{"from":"{from}","text":"{text}","sim":"{sim}"}',
                   webhook_content_type='application/json',webhook_timeout=12)
            p.update(changes);r=call('set',payload=p);assert r.get('ok'),r;return p
        def records():return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        def event(card=0,**changes):
            item=dict(id=1000000000+len(items),card=card,number='+8610000',text='验证码 "quote"\n$(reboot)',
                      time='2026-10-10T10:00:00+08:00',direction='in',state='received',
                      historical=False,first_seen=int(time.time())+2)
            item.update(changes);items.append(item);inbox.write_text(json.dumps({'version':1,'messages':items}))
            call('event',item['id']);return item
        config();event(1)
        assert len(records())==1 and json.loads(records()[0]['body'])['sim']=='SIM2'
        assert json.loads(records()[0]['body'])['text']==items[0]['text']
        call('event',items[0]['id']);assert len(records())==1
        late=event(0,state='receiving');assert len(records())==1
        event(1);late['state']='received';inbox.write_text(json.dumps({'version':1,'messages':items}))
        call('event',late['id']);assert len(records())==3
        event(historical=True);event(direction='out');event(first_seen=0);assert len(records())==3
        config(blacklist_keywords='验证码');event();assert len(records())==3
        config(blacklist_phone='+8610000');event();assert len(records())==3
        config('sim0','per_sim');config('sim1','per_sim');event(0);event(1)
        assert [x['url'] for x in records()[-2:]]==['https://example.com/sim0','https://example.com/sim1']
        config('sim1','per_sim',method='dingtalk',dingtalk_webhook='https://oapi.dingtalk.com/robot/send?access_token=TEST',dingtalk_secret='SECRET')
        event(1);q=parse_qs(urlsplit(records()[-1]['url']).query)
        expected=base64.b64encode(hmac.new(b'SECRET',(q['timestamp'][0]+'\nSECRET').encode(),hashlib.sha256).digest()).decode()
        assert q['sign'][0]==expected
        config('sim1','per_sim',method='smtp',smtp_host='smtp.example.com',smtp_port=465,
               smtp_username='from@example.com',smtp_to='to@example.com',smtp_password='PASSWORD')
        event(1);assert records()[-1]['channel']=='smtp'
        c=call('get','sim1')['config'];assert c['smtp']['password_configured'] and 'PASSWORD' not in json.dumps(c)
        config('sim1','per_sim',method='sms',sms_to_phone='+86123456789',clear_smtp_password=1)
        event(1,text='short');assert records()[-1]['channel']=='sms' and records()[-1]['slot']=='1'
        n=len(records());event(1,text='x'*80);assert len(records())==n
        status=call('status','sim1');assert status['status']['last_result']=='message_too_long'
        assert not any(x in json.dumps(status) for x in ['SECRET','PASSWORD','86123456789','验证码'])
        # Power worker establishes a baseline, then sends exactly once on transition.
        config('shared','shared',power_forward_enabled=1)
        worker=subprocess.Popen([str(tools/'sms-forward'),'run'],env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            time.sleep(1.2);n=len(records());(battery/'status').write_text('Charging')
            for _ in range(25):
                if len(records())>n:break
                time.sleep(.1)
            assert len(records())==n+1
            time.sleep(1.1);assert len(records())==n+1
        finally:os.killpg(worker.pid,signal.SIGTERM);worker.wait(timeout=5)
        for _ in range(32):event()
        assert len(call('status')['status']['history'])==30
        assert not list(root.glob('unisoc-modem-forward.*.pass'))
        assert call('get','sim1')['sim_slots']==2
        print('PASS: native events, dedup, multipart, history barrier, both SIMs, blacklists, HTTPS templates, DingTalk HMAC, SMTP, source-slot SMS, power transitions and bounded private history')


if __name__=='__main__':main()
