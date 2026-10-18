#!/usr/bin/env python3
"""Offline packet-log evidence for the verified W24.13.3 WCN image.

These are firmware-generated, often truncated/reconstructed packet records,
not an independent air capture. The legacy rate byte wraps at 128 Mbps.
Retain all firmware-table candidates; never silently choose one bandwidth.
No device access, firmware writes, packet payload export or dependencies.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import ipaddress
import json
from pathlib import Path
import struct


FIRMWARE_SHA256 = "ac8f2d97278cfff1aa5dce29ba5a0c3366767f7d0bcf3e9f03b194c361aa4f5a"
RADIOTAP_PREFIX = bytes.fromhex("00001200ee000000")


def firmware_rate_candidates(firmware):
    if hashlib.sha256(firmware).hexdigest() != FIRMWARE_SHA256:
        raise ValueError("Unsupported firmware hash; rate tables and packet schema are build-specific")
    result = defaultdict(list)
    # VA 0x1292cc: type 0/1 uses entry[1]; HT uses 4 halfwords/MCS;
    # VHT uses 6 halfwords/MCS and separate NSS tables. Base VA 0x100000.
    for code in range(52):
        entry = firmware[0x7e870 + code * 7:0x7e870 + (code + 1) * 7]
        mcs, mode, nss_index = entry[1:4]
        if mode < 2:
            variants = [(None, None, mcs)]
        else:
            variants = []
            base = 0x7e6f8 if mode == 2 else 0x7e780 + nss_index * 120
            stride = 8 if mode == 2 else 12
            for bw_index in range(2 if mode == 2 else 3):
                for sgi in range(2):
                    rate = struct.unpack_from("<H", firmware,
                                              base + mcs * stride + bw_index * 4 + sgi * 2)[0]
                    variants.append((20 << bw_index, bool(sgi), rate))
        for width, sgi, rate in variants:
            # VA 0x125da0 ends in LSL #25; LSR #24. This discards bit 7+.
            result[(rate & 0x7f) * 2].append(dict(
                code=code, mode=("DSSS", "OFDM", "HT", "VHT")[mode],
                mcs=mcs if mode >= 2 else None,
                nss=nss_index + 1 if mode >= 2 else None,
                bandwidth_mhz=width, short_gi=sgi, firmware_rate_integer_mbps=rate))
    return dict(result)


def packet_records(blob):
    """Scan strongly bounded inner 0x9101 records; no outer checksum validation."""
    position = 0
    while (start := blob.find(b"\x01\x91", position)) >= 0:
        position = start + 2
        if start + 38 > len(blob):
            continue
        length = struct.unpack_from("<H", blob, start + 2)[0]
        # 0x1042b6 caps the embedded dump at 250 bytes; header is 20 bytes.
        if not 38 <= length <= 270 or start + length > len(blob):
            continue
        if blob[start + 6:start + 16] != b"\x10\x00" + b"\xff" * 8:
            continue
        if blob[start + 20:start + 28] != RADIOTAP_PREFIX:
            continue
        position = start + length
        yield dict(timestamp=struct.unpack_from("<I", blob, start + 16)[0],
                   flags=blob[start + 28], rate_byte=blob[start + 29],
                   frame=blob[start + 38:start + length])


def downlink_ipv4_tcp(packet, server, port):
    frame = packet["frame"]
    if len(frame) < 26:
        return None
    fc = struct.unpack_from("<H", frame)[0]
    # Ordinary three-address QoS data, from DS, no protected payload/fragment.
    if fc & 0xfc != 0x88 or (fc >> 8) & 3 != 2 or fc & 0x4400:
        return None
    if struct.unpack_from("<H", frame, 22)[0] & 0xf:
        return None
    # Reconstructed A-MSDU bodies are not parsed as ordinary LLC/IP.
    if frame[24] & 0x80:
        return None
    offset = 26 + (4 if fc & 0x8000 else 0)
    if frame[offset:offset + 8] != bytes.fromhex("aaaa030000000800"):
        return None
    ip = frame[offset + 8:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return None
    ihl = (ip[0] & 15) * 4
    total = struct.unpack_from(">H", ip, 2)[0]
    if ihl < 20 or len(ip) < ihl + 20 or total < ihl + 20:
        return None
    if struct.unpack_from(">H", ip, 6)[0] & 0x3fff:
        return None
    if ip[12:16] != server:
        return None
    tcp = ip[ihl:]
    thl = (tcp[12] >> 4) * 4
    if thl < 20 or len(tcp) < thl or total <= ihl + thl:
        return None
    if struct.unpack_from(">H", tcp)[0] != port:
        return None
    return str(ipaddress.IPv4Address(ip[16:20]))


def analyze(blob, server, port):
    peers = {}
    count = 0
    for packet in packet_records(blob):
        count += 1
        destination = downlink_ipv4_tcp(packet, server, port)
        if destination is None:
            continue
        row = peers.setdefault(destination, dict(records=0, rate_bytes=Counter(),
                                                 flags=Counter(), timestamp_min=None,
                                                 timestamp_max=None))
        row["records"] += 1
        row["rate_bytes"][packet["rate_byte"]] += 1
        row["flags"][packet["flags"]] += 1
        timestamp = packet["timestamp"]
        for name, fn in (("timestamp_min", min), ("timestamp_max", max)):
            row[name] = timestamp if row[name] is None else fn(row[name], timestamp)
    return dict(sha256=hashlib.sha256(blob).hexdigest(), accepted_packet_records=count,
                downlink_tcp_data_by_destination=peers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--server", default="192.168.9.1", type=ipaddress.IPv4Address)
    parser.add_argument("--port", default=5201, type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        candidates = firmware_rate_candidates(args.firmware.read_bytes())
    except ValueError as exc:
        parser.error(str(exc))
    logs = {str(path): analyze(path.read_bytes(), args.server.packed, args.port)
            for path in args.logs}
    observed = {rate for log in logs.values()
                for peer in log["downlink_tcp_data_by_destination"].values()
                for rate in peer["rate_bytes"]}
    result = dict(firmware_sha256=FIRMWARE_SHA256,
                  scope="Firmware packet dumps; incomplete coverage, not an air capture",
                  rate_candidates={byte: candidates.get(byte, []) for byte in sorted(observed)},
                  logs=logs)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.resolve() in {p.resolve() for p in [args.firmware, *args.logs]}:
            parser.error("Output must not overwrite an input")
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
