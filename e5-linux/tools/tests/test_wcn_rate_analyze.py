import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("wcn_rate", Path(__file__).parents[1] / "wcn-rate-analyze.py")
wcn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wcn)


def record(ident, *fields):
    data = "\x01".join(map(str, fields)).encode("ascii")
    return b"\x21\x91" + struct.pack("<HI", 8 + len(data), ident) + data


class WcnRateTest(unittest.TestCase):
    def test_binary_false_matches_and_truncated_records_are_excluded(self):
        valid = record(0x05400068, 6, 12, 43)
        binary = b"\x21\x91" + struct.pack("<HI", 9, 99) + b"\xff"
        truncated = b"\x21\x91" + struct.pack("<HI", 4096, 100)
        self.assertEqual(list(wcn.text_records(binary + truncated + valid)),
                         [(0x05400068, ["6", "12", "43"])])

    def test_peer_boundaries_and_distinct_bw_factor(self):
        blob = record(0x054000C0, 1, 1, 6)
        blob += record(0x05400027, 12, 95, 94, 94)
        blob += record(0x05400023, 12, 43, 36472, 97, 1)
        blob += record(0x054000C0, 2, 1, 7)
        blob += record(0x05400027, 12, 93, 92, 92)
        blob += record(0x05400023, 12, 43, 17848, 97, 1)
        peers = wcn.analyze(blob)["peers"]
        self.assertEqual(peers[6]["inferred_algorithm_bw_factors"], {"4": 1})
        self.assertEqual(peers[7]["inferred_algorithm_bw_factors"], {"2": 1})

    def test_incomplete_counter_cycle_does_not_pollute_totals(self):
        blob = record(0x054000C0, 1, 1, 6)
        blob += record(0x054000C1, 1, 0, 100, 101, 12, 0, 0, 12)
        blob += record(0x054000C0, 2, 1, 6)
        for slot in range(8):
            blob += record(0x054000C1, 2, slot, 4, 5, 12, 1, 2, 10)
        peer = wcn.analyze(blob)["peers"][6]
        self.assertEqual(peer["complete_counter_cycles"], 1)
        self.assertEqual(peer["counter_success"], 40)
        self.assertEqual(peer["counter_attempts"], 56)

    def test_pm_peer_is_not_inferred_from_last_active_rate_peer(self):
        blob = record(0x054000C0, 1, 1, 6)
        blob += record(0x03000077, 1, "pm_ap_handle_one_peer_status_change", "80", "92", 7, 0, 1)
        self.assertEqual(wcn.analyze(blob)["power_state_transitions_by_peer"], {7: 1})


if __name__ == "__main__":
    unittest.main()
