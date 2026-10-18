"""Real HTTP stream, change deduplication, origin isolation and bounded shutdown."""
import http.client,sys,json,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'overlay/usr/lib/e5'))
from e5_call_events import CallEvents, ORIGIN

events=CallEvents(port=0)
state={'available':True,'calls':[],'updated':1,'bluetooth':{'updated':1,'connected':False}}
events.publish(state)
def connect(origin=ORIGIN):
    client=http.client.HTTPConnection('127.0.0.1',events.port,timeout=2)
    client.request('GET','/events',headers={'Origin':origin})
    return client,client.getresponse()
try:
    bad,reply=connect('http://example.org');assert reply.status==403;bad.close()
    client,reply=connect();assert reply.status==200
    def read_event():
        line=reply.fp.readline();assert line.startswith(b'data: '),line
        assert reply.fp.readline()==b'\n'
        return json.loads(line[6:])
    assert read_event()['calls']==[]
    revision=events.revision
    for i in range(10000):events.publish({**state,'updated':i,'bluetooth':{'updated':i,'connected':False}})
    assert events.revision==revision,'idle timestamps generated network events'
    call={'id':'fixture','state':'ringing-in','number':'test'}
    started=time.monotonic();events.publish({**state,'calls':[call]},wake=False)
    message=read_event();assert message['calls']==[call] and message['wake'] is False
    assert time.monotonic()-started<1,'notification delayed by polling'
    events.publish({**state,'calls':[]});assert read_event()['calls']==[]
    client.close()
    # A fresh connection receives current state, not history.
    client,reply=connect();assert read_event()['calls']==[]
    started=time.monotonic();events.close()
    assert time.monotonic()-started<1 and not events.thread.is_alive()
    client.close()
    print('SSE initial/current state, change-only delivery, wake preference, origin and shutdown PASS')
finally:
    if not events.closed:events.close()
