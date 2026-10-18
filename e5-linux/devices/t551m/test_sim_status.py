"""Per-card status parsing; mocked AT only, no RF or SIM switching."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('sims',Path(__file__).with_name('infoscreen')/'sim-status.py')
sims=importlib.util.module_from_spec(spec);spec.loader.exec_module(sims)

class SimsTest(unittest.TestCase):
    def setUp(self):self.sent=[];self.override={}
    def read(self,card,cmd):
        self.sent.append((card,cmd))
        return self.override.get(cmd, {'+CPIN?':'+CPIN: READY\nOK\n','+CFUN?':'+CFUN: 1\nOK\n',
            '+CSCS?;+COPS?':'+CSCS: "GSM"\n+COPS: 0,0,"CHN-UNICOM",7\nOK' if card==0 else '+CSCS: "UCS2"\n+COPS: 0,2,"46011",11\nOK',
            '+CEREG?':'OK\n','+C5GREG?':'OK\n',
            '+CESQ':'+CESQ: 99,99,255,255,14,50,255,255,255\nOK' if card==0 else '+CESQ: 99,99,255,255,255,255,74,53,67\nOK',
            '+SPENGMD=0,0,6':'255-255-400-0,1-0,0-4-0-3-600\nOK'}[cmd])
    def test_lte_and_nr_are_independent(self):
        a,b=sims.collect(0,self.read),sims.collect(1,self.read)
        self.assertEqual((a['tech'],a['signal']['rsrp']),('lte',-91))
        self.assertEqual((b['tech'],b['signal']['rsrp']),('5gnr',-104))
        self.assertEqual((a['registration'],b['registration']),('camped','camped'))
        self.assertIsNone(b['reg5g']) # Bare OK cannot establish registration.
        self.assertEqual(set(card for card,_ in self.sent),{0,1})
        self.assertEqual((a['signal']['snr'],b['signal']['snr']),(4,10.5))
        self.assertEqual([c for c in self.sent if c[1]=='+SPENGMD=0,0,6'],[(0,'+SPENGMD=0,0,6')])
    def test_lte_phy_values(self):
        for raw,expected in [('400',4),('-350',-3.5),('+350',-3.5),('0',0),
                             ('-2000',-20),('4000',40),('4001',None),('-2001',None),
                             ('NA',None),('N/A',None),('bad',None)]:
            with self.subTest(raw=raw):
                reply='AT+SPACTCARD=0;+SPENGMD=0,0,6\n255-255-'+raw+'-0,1-0,0-4-0\nOK'
                self.assertEqual(sims.lte_sinr(reply),expected)
        for reply in ['ERROR','+CME ERROR: 100','OK','255-255-400','']:
            self.assertIsNone(sims.lte_sinr(reply))
    def test_lte_phy_failure_keeps_other_readings(self):
        def read(card,cmd):
            if cmd=='+SPENGMD=0,0,6':raise RuntimeError('timeout')
            return self.read(card,cmd)
        row=sims.collect(0,read)
        self.assertEqual((row['tech'],row['signal']['rsrp'],row['registration']),('lte',-91,'camped'))
        self.assertIsNone(row['signal']['snr'])
        self.assertIsNone(row['error'])
    def test_no_lte_phy_without_lte_measurement(self):
        self.override['+CESQ']='+CESQ: 99,99,255,255,255,255,255,255,255\nOK'
        sims.collect(0,self.read)
        self.assertNotIn((0,'+SPENGMD=0,0,6'),self.sent)
    def test_registered_and_roaming(self):
        self.override['+CEREG?']='+CEREG: 2,5,"1234","5678",7\nOK'
        self.assertEqual(sims.collect(0,self.read)['registration'],'roaming')
        self.override['+C5GREG?']='+C5GREG: 2,1,"1234","5678",11\nOK'
        self.assertEqual(sims.collect(1,self.read)['registration'],'home')
    def test_ucs2_operator_keeps_registration_and_signal(self):
        self.override['+CSCS?;+COPS?']='+CSCS: "UCS2"\n+COPS: 0,0,"4E2D56FD8054901A",7\nOK'
        row=sims.collect(0,self.read)
        self.assertEqual(row['operator'],'中国联通')
        self.assertEqual((row['tech'],row['signal']['rsrp']),('lte',-91))
        self.assertEqual([cmd for _,cmd in self.sent if 'COPS' in cmd],['+CSCS?;+COPS?'])
        self.assertFalse(any('CSCS=' in cmd for _,cmd in self.sent))
    def test_absent_locked_off(self):
        for reply,state in [('+CME ERROR: 10','absent'),('+CPIN: SIM PIN\nOK','locked')]:
            self.override['+CPIN?']=reply;self.sent=[]
            self.assertEqual(sims.collect(0,self.read)['registration'],state)
            self.assertEqual(len(self.sent),1)
        self.override={'+CFUN?':'+CFUN: 4\nOK'}
        self.assertEqual(sims.collect(1,self.read)['registration'],'disabled')
        self.override={'+CPIN?':'+CME ERROR: 100'}
        self.assertEqual(sims.collect(1,self.read)['registration'],'unknown')
    def test_failure_does_not_reuse_signal(self):
        def fail(*_):raise RuntimeError('timeout')
        row=sims.collect(1,fail)
        self.assertEqual(row['signal'],{});self.assertIsNone(row['tech']);self.assertEqual(row['registration'],'unknown')
    def test_unknown_signal_stays_unknown(self):
        self.override['+CESQ']='+CESQ: 99,99,255,255,255,255,255,255,255\nOK'
        row=sims.collect(1,self.read)
        self.assertIsNone(row['signal']['rsrp']);self.assertEqual(row['registration'],'unknown')

if __name__=='__main__':unittest.main()
