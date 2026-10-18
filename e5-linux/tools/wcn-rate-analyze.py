#!/usr/bin/env python3
"""Offline evidence summary for MARLIN3_20A_RLS2_W24.13.3 text logs.

Scans bounded 0x9121 text records, not the enclosing transport/checksum.
This is not an air capture decoder. Firmware counters/rates must not be
reported as TCP loss, measured throughput, or each packet's PHY bandwidth.
No device access, writes to firmware, or third-party dependencies.
"""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct


FIRMWARE_SHA256 = "ac8f2d97278cfff1aa5dce29ba5a0c3366767f7d0bcf3e9f03b194c361aa4f5a"


def text_records(blob):
    position = 0
    while True:
        start = blob.find(b"\x21\x91", position)
        if start < 0:
            return
        position = start + 2
        if start + 8 > len(blob):
            continue
        length, ident = struct.unpack_from("<HI", blob, start + 2)
        if not 8 <= length <= 4096 or start + length > len(blob):
            continue
        payload = blob[start + 8:start + length]
        if any(byte != 1 and not 32 <= byte <= 126 for byte in payload):
            continue
        position = start + length
        yield ident, payload.decode("ascii").split("\x01")


def analyze(blob):
    counts = Counter()
    chosen = Counter()
    pm = Counter()
    updates = Counter()
    groups = []
    group = None
    for ident, fields in text_records(blob):
        counts[f"0x{ident:08x}"] += 1
        if ident == 0x05400068:
            chosen[tuple(map(int, fields))] += 1
        elif ident == 0x03000077:
            pm[int(fields[4])] += 1
        elif ident == 0x054000AD:
            updates[tuple(map(int, fields))] += 1
        elif ident == 0x054000C0:
            timestamp, context, peer = map(int, fields)
            group = dict(peer=peer, timestamp=timestamp, rows=[], counters=[],
                         probability={}, ba_updates=0)
            groups.append(group)
        elif group is not None:
            if ident == 0x05400023:
                group["rows"].append(list(map(int, fields)))
            elif ident == 0x054000C1:
                group["counters"].append(list(map(int, fields)))
            elif ident == 0x05400027:
                index, old, instant, smoothed = map(int, fields)
                group["probability"][index] = smoothed
            elif ident == 0x054000BA:
                group["ba_updates"] += 1

    peers = {}
    for peer in sorted({g["peer"] for g in groups}):
        selected = [g for g in groups if g["peer"] == peer]
        sums = defaultdict(lambda: [0, 0])
        factors = Counter()
        complete = 0
        for g in selected:
            # Exclude incomplete or duplicated eight-slot counter snapshots.
            if sorted(row[1] for row in g["counters"]) == list(range(8)):
                complete += 1
                for timestamp, slot, success, attempts, index, success2, attempts2, index2 in g["counters"]:
                    if success > attempts or success2 > attempts2:
                        raise ValueError("Firmware success count exceeds attempt count")
                    for rate, a, b in ((index, success, attempts), (index2, success2, attempts2)):
                        sums[rate][0] += a
                        sums[rate][1] += b
            for index, code, score, normalized, sgi in g["rows"]:
                probability = g["probability"].get(index, 0)
                if normalized * probability:
                    factors[str(Fraction(score, normalized * probability))] += 1
        success = sum(pair[0] for pair in sums.values())
        attempts = sum(pair[1] for pair in sums.values())
        peers[peer] = dict(
            rate_cycles=len(selected), complete_counter_cycles=complete,
            counter_success=success, counter_attempts=attempts,
            counter_success_percent=round(100 * success / attempts, 3) if attempts else None,
            counters_by_candidate=dict(sorted(sums.items())),
            inferred_algorithm_bw_factors=dict(factors),
            ba_control_updates=sum(g["ba_updates"] for g in selected),
        )
    return dict(
        sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob),
        accepted_text_records=sum(counts.values()), record_ids=dict(sorted(counts.items())),
        chosen_candidates=[dict(peer=p, candidate=i, code=c, count=n)
                           for (p, i, c), n in sorted(chosen.items())],
        power_state_transitions_by_peer=dict(sorted(pm.items())),
        ba_classifier_records=[dict(peer=p, kind=k, candidate=i, code=c,
                                    threshold=t, flag=f, count=n)
                               for (p, k, i, c, t, f), n in sorted(updates.items())],
        peers=peers,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", required=True, type=Path,
                        help="Local, unmodified firmware; hash gates the decoded schema")
    parser.add_argument("--output", type=Path, help="Write summary JSON here; otherwise stdout")
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()
    firmware = args.firmware.read_bytes()
    if hashlib.sha256(firmware).hexdigest() != FIRMWARE_SHA256:
        parser.error("Unsupported firmware hash; do not apply this field mapping to another build")
    # The init function at VA 0x126616 copies 52 seven-byte entries from here.
    table = [list(firmware[0x7e870 + i * 7:0x7e870 + (i + 1) * 7]) for i in range(52)]
    result = dict(firmware_sha256=FIRMWARE_SHA256, static_rate_table=table,
                  logs={str(path): analyze(path.read_bytes()) for path in args.logs})
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.resolve() in {path.resolve() for path in [args.firmware, *args.logs]}:
            parser.error("Output must not overwrite an input")
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
