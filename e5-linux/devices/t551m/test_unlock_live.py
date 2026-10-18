"""On-device swipe regression through evdev -> compositor -> WPE.

Run with python3 on an idle device using standard swipe distance and enabled
screen lock/touch. Requires the current UI load message in logread (run shortly
after restarting e5-infoscreen). Toggles screen power and injects six gestures;
does not change saved settings. Does not test physical finger/sensor quality.
"""
import json,struct,subprocess,time
from pathlib import Path

def main():
    voice=Path('/run/e5-voice-audio/status.json')
    if voice.exists():
        state=json.loads(voice.read_text());assert not state.get('active') and not state.get('calls'),'Active call'
    assert subprocess.check_output(['uci','-q','get','e5-infoscreen.main.touch'],text=True).strip()=='1'
    mode=subprocess.run(['uci','-q','get','e5-infoscreen.main.unlock_distance'],capture_output=True,text=True).stdout.strip()
    assert mode in ('','standard'),'Select standard swipe distance before running this test'
    configs={str(p):p.read_bytes() for p in Path('/etc/config').iterdir() if p.is_file()}
    # procd's restart returns before cage/cog has actually loaded the page. A live
    # HTTP API alone is insufficient: wait for the current UI instance, never an
    # old process's load message, before injecting physical input events.
    deadline=time.monotonic()+45
    while True:
        service=json.loads(subprocess.check_output(['ubus','call','service','list',json.dumps({'name':'e5-infoscreen'})],text=True))
        pid=service.get('e5-infoscreen',{}).get('instances',{}).get('ui',{}).get('pid')
        logs=subprocess.check_output(['logread'],text=True)
        if pid and any(f'session[{pid}]:' in line and 'Loaded successfully.' in line for line in logs.splitlines()):break
        assert time.monotonic()<deadline,'No load confirmation for current screen UI in logread'
        time.sleep(.5)
    brightness=Path('/sys/class/backlight/sprd_backlight/brightness')
    was_awake=int(brightness.read_text())>0
    def emit(fd,kind,code,value):fd.write(struct.pack('@llHHi',0,0,kind,code,value))
    def sync(fd):emit(fd,0,0,0)
    def power():
        with open('/dev/input/event0','wb',buffering=0) as fd:
            emit(fd,1,116,1);sync(fd);time.sleep(.06);emit(fd,1,116,0);sync(fd)
    def wait_power(on):
        until=time.monotonic()+4
        while (int(brightness.read_text())>0)!=on:
            assert time.monotonic()<until,'Power event did not reach screen'
            time.sleep(.03)
    def relock():
        if int(brightness.read_text())>0:power();wait_power(False)
        power();wait_power(True);time.sleep(.55)
    def unlocked_since(marker):
        logs=subprocess.check_output(['logread'],text=True)
        assert marker in logs,'Test marker evicted from log'
        tail=logs.rsplit(marker,1)[1]
        return 'CONSOLE LOG t551m-screen: unlocked' in tail
    def swipe(points):
        with open('/dev/input/event1','wb',buffering=0) as fd:
            def position(x,y):
                for code,value in [(53,x),(54,y),(0,x),(1,y)]:emit(fd,3,code,value)
            emit(fd,3,47,0);emit(fd,3,57,1042)
            position(*points[0][1:]);emit(fd,1,330,1);sync(fd)
            previous=points[0][0]
            try:
                for t,x,y in points[1:]:
                    time.sleep(t-previous);position(x,y);sync(fd);previous=t
            finally:
                emit(fd,3,57,-1);emit(fd,1,330,0);sync(fd)
    cases=[
        ('middle-origin',[(0,160,220),(.05,160,195),(.10,160,165),(.16,160,140),(.22,160,110)],True),
        ('thumb-arc',[(0,110,410),(.05,130,370),(.10,150,340),(.15,175,300),(.20,195,260)],True),
        ('release-wobble',[(0,160,425),(.05,160,390),(.10,160,340),(.15,160,285),(.19,160,297)],True),
        ('short-flick',[(0,160,425),(.025,160,400),(.05,160,375),(.075,160,345)],True),
        ('tap',[(0,160,425),(.08,160,425)],False),
        ('short-slow',[(0,160,425),(.10,160,410),(.20,160,395),(.30,160,380)],False),
    ]
    try:
        for name,points,expected in cases:
            relock();marker='unlock-check-'+name+'-'+str(time.monotonic_ns())
            subprocess.run(['logger','-t','t551m-unlock-test',marker],check=True)
            swipe(points);time.sleep(.9)
            actual=unlocked_since(marker)
            print(name,'unlocked='+str(actual),flush=True)
            assert actual==expected,(name,actual,expected)
    finally:
        if not was_awake and int(brightness.read_text())>0:power();wait_power(False)
    for name,data in configs.items():assert Path(name).read_bytes()==data,name
    print('PASS: six gestures through real evdev / compositor / WPE; screen settings unchanged')


if __name__ == '__main__': main()
