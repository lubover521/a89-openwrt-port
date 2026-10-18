import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("wcn_packet", Path(__file__).parents[1] / "wcn-packet-analyze.py")
wcn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcn)
SERVER = bytes([192, 168, 9, 1])


def record(destination=99, rate=98, timestamp=100, data_length=1448, source_port=5201):
    frame = bytearray(26)
    struct.pack_into("<H", frame, 0, 0x288)
    ip = bytearray(20)
    ip[0] = 0x45
    ip[9] = 6
    ip[12:16] = SERVER
    ip[16:20] = bytes([192, 168, 9, destination])
    struct.pack_into(">H", ip, 2, 40 + data_length)
    tcp = bytearray(20)
    struct.pack_into(">H", tcp, 0, source_port)
    tcp[12] = 0x50
    # Dump carries only the TCP header; original IPv4 total length is larger.
    body = wcn.RADIOTAP_PREFIX + bytes([4, rate]) + bytes(8)
    body += frame + bytes.fromhex("aaaa030000000800") + ip + tcp
    return struct.pack("<HHHH", 0x9101, 20 + len(body), 0xabcd, 0x10) + b"\xff" * 8 + struct.pack("<I", timestamp) + body


class WcnPacketTest(unittest.TestCase):
    def test_capture_prefix_truncation_and_false_matches(self):
        good = record()
        corrupt = bytearray(good)
        corrupt[8] = 0
        oversized = bytearray(good)
        struct.pack_into("<H", oversized, 2, 4096)
        records = list(wcn.packet_records(bytes(corrupt) + bytes(oversized) + good + good[:-1]))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["rate_byte"], 98)

    def test_residual_peer_and_control_ack_do_not_pollute_test_peer(self):
        blob = record() + record(122, timestamp=200) + record(122, timestamp=201)
        blob += record(122, data_length=0) + record(122, source_port=443)
        result = wcn.analyze(blob, SERVER, 5201)
        self.assertEqual(result["accepted_packet_records"], 5)
        peers = result["downlink_tcp_data_by_destination"]
        self.assertEqual(peers["192.168.9.99"]["records"], 1)
        self.assertEqual(peers["192.168.9.122"]["records"], 2)
        self.assertEqual(peers["192.168.9.122"]["timestamp_min"], 200)

    def test_invalid_ip_header_and_amsdu_body_are_excluded(self):
        bad_ihl = bytearray(record())
        bad_ihl[38 + 26 + 8] = 0x44
        amsdu = bytearray(record())
        amsdu[38 + 24] = 0x80
        fragmented = bytearray(record())
        struct.pack_into(">H", fragmented, 38 + 26 + 8 + 6, 0x2000)
        result = wcn.analyze(bytes(bad_ihl + amsdu + fragmented), SERVER, 5201)
        self.assertEqual(result["downlink_tcp_data_by_destination"], {})

    def test_rate_wrap_and_collisions_remain_explicit(self):
        firmware = bytearray(0x7e870 + 52 * 7)
        firmware[0x7e870 + 5 * 7:0x7e870 + 6 * 7] = bytes([251, 6, 1, 0, 6, 0, 4])
        firmware[0x7e870 + 43 * 7:0x7e870 + 44 * 7] = bytes([9, 9, 3, 0, 87, 97, 38])
        struct.pack_into("<HH", firmware, 0x7e780 + 9 * 12 + 2 * 4, 390, 433)
        with patch.object(wcn, "FIRMWARE_SHA256", hashlib.sha256(firmware).hexdigest()):
            candidates = wcn.firmware_rate_candidates(firmware)
        self.assertEqual(len(candidates[98]), 1)
        self.assertEqual(candidates[98][0]["firmware_rate_integer_mbps"], 433)
        self.assertEqual(candidates[98][0]["bandwidth_mhz"], 80)
        self.assertEqual({r["firmware_rate_integer_mbps"] for r in candidates[12]}, {6, 390})
        with self.assertRaisesRegex(ValueError, "Unsupported firmware"):
            wcn.firmware_rate_candidates(firmware)


if __name__ == "__main__":
    unittest.main()
