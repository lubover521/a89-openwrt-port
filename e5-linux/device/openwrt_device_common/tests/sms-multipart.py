#!/usr/bin/env python3
"""Persistent dual-SIM multipart regression; no AT, modem or webhooks."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

fixture = runpy.run_path(str(Path(__file__).with_name('dual-sms.py')))
sms_pdu, receiver = fixture['sms_pdu'], fixture['receiver']


def part(text, ref=42, sequence=1, total=2, wide=False,
         stamp='62017021436500', pid=0, smsc='00', index=None):
    header = (bytes([6, 8, 4, ref >> 8, ref & 255, total, sequence]) if wide else
              bytes([5, 0, 3, ref, total, sequence])) if total else b''
    payload = header + text.encode('utf-16-be')
    pdu = (bytes.fromhex(smsc) + bytes([0x40 if header else 0, 4, 0x81, 0x21, 0x43, pid, 8])
           + bytes.fromhex(stamp) + bytes([len(payload)]) + payload)
    return {**sms_pdu.decode(pdu.hex()), 'storage_index': index or sequence, 'storage_status': 0}


class Multipart(unittest.TestCase):
    def setUp(self):
        self.data = {'version': 1, 'next_id': receiver.MIN_ID, 'initialized': [], 'messages': [], 'slots': {}}
        receiver.ingest(self.data, 0, 'card0', [], 0)
        receiver.ingest(self.data, 1, 'card1', [], 0)

    def receive(self, *parts, card=0, now=1):
        return receiver.ingest(self.data, card, 'card' + str(card), sms_pdu.assemble(parts), now)

    def texts(self):
        return sorted(m['text'] for m in self.data['messages'] if not m.get('deleted'))

    def test_reverse_order_and_disjoint_scans(self):
        self.assertEqual(self.receive(part('tail', sequence=2)), ([], []))
        self.assertEqual(self.texts(), []); self.assertEqual(self.data['next_id'], receiver.MIN_ID)
        alerts, forwards = self.receive(part('head'))
        self.assertEqual(alerts, forwards); self.assertEqual(len(alerts), 1)
        self.assertEqual(self.texts(), ['headtail']); self.assertEqual(self.data['pending'], {})

    def test_three_interleaved_same_sender_same_second(self):
        for text, ref, seq in [('B2', 2, 2), ('A3', 1, 3), ('C1', 3, 1), ('A1', 1, 1),
                               ('B1', 2, 1), ('C3', 3, 3), ('A2', 1, 2), ('B3', 2, 3), ('C2', 3, 2)]:
            self.receive(part(text, ref, seq, 3))
        self.assertEqual(self.texts(), ['A1A2A3', 'B1B2B3', 'C1C2C3'])

    def test_repeated_pending_and_completed_parts(self):
        for seq in [2, 2, 1, 1, 2]:
            self.receive(part('A' if seq == 1 else 'B', sequence=seq))
        self.assertEqual(self.texts(), ['AB']); self.assertEqual(self.data['next_id'], receiver.MIN_ID + 1)

    def test_same_pdu_at_multiple_storage_indices(self):
        self.receive(part('A'), part('A', index=3), part('B', sequence=2))
        self.assertEqual(self.texts(), ['AB'])

    def test_8_and_16_bit_references_do_not_mix(self):
        self.receive(part('8a'), part('16b', sequence=2, wide=True))
        self.receive(part('8b', sequence=2), part('16a', wide=True))
        self.assertEqual(self.texts(), ['16a16b', '8a8b'])

    def test_pid_and_smsc_separate_groups(self):
        for options in [dict(pid=1), dict(smsc='03912143')]:
            self.setUp()
            self.receive(part('A'), part('Y', sequence=2, **options))
            self.receive(part('B', sequence=2), part('X', **options))
            self.assertEqual(self.texts(), ['AB', 'XY'])

    def test_scts_cross_minute_and_ref_reuse_next_day(self):
        self.receive(part('B', sequence=2, stamp='62017022530000'))
        self.receive(part('A', stamp='62017022439500'))
        self.receive(part('D', sequence=2, stamp='62018022439500'))
        self.receive(part('C', stamp='62018022439500'))
        self.assertEqual(self.texts(), ['AB', 'CD'])

    def test_missing_parts_survive_empty_scan_and_restart(self):
        self.receive(part('C', sequence=3, total=3), part('A', total=3))
        self.receive()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(receiver, 'DATA', root / 'data'), patch.object(receiver, 'RUN', root / 'run'), \
                    patch.object(receiver, 'INBOX', root / 'data/inbox.json'):
                with receiver.locked(): receiver.save(self.data)
                self.assertEqual(receiver.inbox()['messages'], [])
                self.assertEqual((root / 'run/unread').read_text(), '')
                self.data = receiver.load()
        self.receive(part('B', sequence=2, total=3))
        self.assertEqual(self.texts(), ['ABC'])

    def test_two_sim_pools_do_not_mix(self):
        self.receive(part('A')); self.receive(part('Y', sequence=2), card=1)
        self.assertEqual(self.texts(), [])
        self.receive(part('B', sequence=2)); self.receive(part('X'), card=1)
        self.assertEqual(self.texts(), ['AB', 'XY'])

    def test_historical_partial_remains_silent(self):
        self.data['initialized'].remove('0:card0')
        self.receive(part('A'))
        self.assertEqual(self.receive(part('B', sequence=2)), ([], []))
        self.assertTrue(self.data['messages'][0]['historical'])
        self.assertFalse(self.data['messages'][0]['unread'])

    def test_deleted_message_never_reappears(self):
        self.receive(part('A'), part('B', sequence=2))
        self.data['messages'][0]['deleted'] = True
        self.receive(part('B', sequence=2)); self.receive(part('A'))
        self.assertEqual(self.texts(), []); self.assertEqual(self.data['pending'], {})

    def test_ambiguous_collision_retains_all_raw_fragments(self):
        self.receive(part('first A')); self.receive(part('first B'))
        self.receive(part('unknown tail', sequence=2))
        self.assertEqual(self.texts(), [])
        self.assertEqual(len(self.data['pending']['0:card0']), 3)
        self.assertTrue(all(p['pdu'] for p in self.data['pending']['0:card0']))
        self.data = json.loads(json.dumps(self.data))
        self.receive(part('unknown tail', sequence=2))
        self.assertEqual(self.texts(), [])

    def test_same_second_single_messages_are_independent(self):
        self.receive(part('first', total=0), part('second', total=0))
        self.assertEqual(self.texts(), ['first', 'second'])

    def test_legacy_partial_migrates_to_pending(self):
        message = sms_pdu.assemble([part('A')])[0]
        self.data['messages'].append(dict(id=receiver.MIN_ID, card=0, identity='card0',
             historical=False, first_seen=1, unread=True, **message))
        self.data['next_id'] += 1
        self.receive()
        self.assertEqual(self.texts(), [])
        alerts, forwards = self.receive(part('B', sequence=2))
        self.assertEqual(self.texts(), ['AB']); self.assertEqual(alerts, forwards)


if __name__ == '__main__': unittest.main()
