#!/usr/bin/env python3
"""Decode a logic-analyzer capture of the Panasonic R1/R2 bus.

Same algorithm as rdbus.h: edges -> carrier bursts -> 8E1 bytes (burst = 0)
-> polls / E3 frames with the 7-bit sum checksum.

Input: CSV exported from PulseView/sigrok (time column in seconds, one column per
channel) or a 0/1 sample column with --samplerate. Lines starting with ';' or '#'
are ignored.

  python3 decode_capture.py capture.csv                 # first data channel
  python3 decode_capture.py capture.csv --channel D1 --bit-us 2020
  python3 decode_capture.py capture.csv --stats         # carrier and bit-time estimate
  python3 decode_capture.py --selftest
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass


@dataclass
class Burst:
    start: float  # microseconds
    end: float
    edges: int


def edges_from_csv(path: str, channel: str | None, samplerate: float | None) -> list[float]:
    with open(path, newline="") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].lstrip().startswith((";", "#"))]
    header = rows[0]
    has_header = any(not _is_number(c) for c in header)
    data = rows[1:] if has_header else rows
    if has_header:
        names = [h.strip() for h in header]
        if channel is None:
            col = 1 if samplerate is None else 0
        else:
            matches = [i for i, n in enumerate(names) if n == channel or n.startswith(channel)]
            if not matches:
                sys.exit(f"channel {channel!r} not in {names}")
            col = matches[0]
    else:
        col = 1 if samplerate is None and len(header) > 1 else 0

    edges: list[float] = []
    prev = None
    for i, r in enumerate(data):
        t = i / samplerate * 1e6 if samplerate else float(r[0]) * 1e6
        v = r[col].strip()
        if v != prev and prev is not None:
            edges.append(t)
        prev = v
    return edges


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def bursts_from_edges(edges: list[float], gap_us: float = 150, min_edges: int = 3) -> list[Burst]:
    out: list[Burst] = []
    start = last = None
    n = 0
    for t in edges:
        if last is not None and t - last > gap_us:
            if n >= min_edges:
                out.append(Burst(start, last, n))
            start, n = None, 0
        if start is None:
            start = t
        last = t
        n += 1
    if start is not None and n >= min_edges:
        out.append(Burst(start, last, n))
    return out


def decode_bytes(bursts: list[Burst], bit_us: float, parity: str = "even"):
    """Yields (t_us, value, parity_ok, stop_ok)."""
    frame_bits = 11 if parity != "none" else 10

    def level(t: float, window: list[Burst]) -> int:
        return 0 if any(b.start <= t <= b.end for b in window) else 1

    i = 0
    while i < len(bursts):
        t0 = bursts[i].start
        decide = t0 + frame_bits * bit_us - bit_us / 2
        window = [b for b in bursts[i : i + 12] if b.start < decide]
        s = [level(t0 + k * bit_us + bit_us / 2, window) for k in range(frame_bits)]
        if s[0] != 0:  # glitch shorter than half a bit: drop only it
            i += 1
            continue
        v = sum(s[1 + k] << k for k in range(8))
        ones = bin(v).count("1")
        if parity == "none":
            pok = True
        else:
            want = ones & 1 if parity == "even" else (~ones) & 1
            pok = s[9] == want
        yield t0, v, pok, s[-1] == 1
        i += len(window)


def checksum7_ok(b: list[int]) -> bool:
    return sum(b) & 0x7F == 0


def messages(byts, timeout_us: float = 60000):
    """Groups bytes into polls/tokens and E3 frames."""
    cur: list = []
    last_t = None
    for t, v, pok, sok in byts:
        err = not (pok and sok)
        if cur and last_t is not None and t - last_t > timeout_us:
            yield cur[0][0], "BAD", [c[1] for c in cur], any(c[2] for c in cur)
            cur = []
        last_t = t
        if not cur:
            if v == 0xE3:
                cur = [(t, v, err)]
                continue
            yield t, ("POLL" if 0x80 <= v <= 0x9F else "TOKEN"), [v], err
            continue
        cur.append((t, v, err))
        if len(cur) >= 2 and len(cur) == cur[1][1] + 3:
            data = [c[1] for c in cur]
            yield cur[0][0], ("FRAME" if checksum7_ok(data) else "BAD"), data, any(c[2] for c in cur)
            cur = []
    if cur:
        yield cur[0][0], "BAD", [c[1] for c in cur], any(c[2] for c in cur)


def stats(bursts: list[Burst]) -> tuple[float, float]:
    car = [(b.edges - 1) * 1e6 / (2 * (b.end - b.start)) for b in bursts if b.edges > 10 and b.end > b.start]
    carrier = sum(car) / len(car) if car else 0.0
    durs = [b.end - b.start for b in bursts if b.end - b.start > 300]
    if not durs:
        return carrier, 0.0
    pad = 1e6 / carrier / 2 if carrier else 0
    mn = min(durs) + pad
    est = [(d + pad) / round((d + pad) / mn) for d in durs if 1 <= round((d + pad) / mn) <= 10]
    return carrier, sum(est) / len(est)


# --------------------------------------------------------------------------- selftest


def synth_edges(frames: list[list[int]], carrier_hz=19200, bit_us=2020.0, gap_us=60000.0) -> list[float]:
    rnd = random.Random(1)
    t = 100000.0
    edges: list[float] = []
    half = 1e6 / carrier_hz / 2
    for fr in frames:
        bits: list[int] = []
        for v in fr:
            bits += [0] + [(v >> k) & 1 for k in range(8)] + [bin(v).count("1") & 1, 1]
        for b in bits:
            if b == 0:
                k = 0
                while k * half < bit_us:
                    edges.append(t + k * half + rnd.uniform(-2, 2))
                    k += 1
                if k % 2:
                    edges.append(t + bit_us - 0.5)
            t += bit_us
        t += gap_us
    edges.sort()
    return edges


def selftest() -> int:
    frames = [
        [0x90],
        [0xA6],
        [0xE3, 0x02, 0x60, 0x01, 0x3A],
        [0xE3, 0x0C, 0x60, 0x21, 0x61, 0x22, 0x62, 0x28, 0x63, 0x28, 0x64, 0x21, 0x49, 0x20, 0x0A],
        [0x00],
        [0xFF],
    ]
    got = [m[2] for m in messages(decode_bytes(bursts_from_edges(synth_edges(frames)), 2020))]
    ok = got == frames
    print("selftest", "passed" if ok else f"FAILED: {got}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--channel", help="column name, e.g. D0 (default: first data column)")
    ap.add_argument("--samplerate", type=float, help="Hz, when the CSV has samples instead of times")
    ap.add_argument("--bit-us", type=float, default=0, help="bit time; default = estimated from capture")
    ap.add_argument("--parity", choices=["even", "odd", "none"], default="even")
    ap.add_argument("--gap-us", type=float, default=150, help="silence that ends a carrier burst")
    ap.add_argument("--stats", action="store_true", help="only print carrier and bit-time estimates")
    ap.add_argument("--no-polls", action="store_true", help="hide single-byte polls")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.csv:
        ap.error("csv file required")

    bursts = bursts_from_edges(edges_from_csv(a.csv, a.channel, a.samplerate), a.gap_us)
    carrier, bit = stats(bursts)
    print(f"; {len(bursts)} bursts, carrier ~{carrier:.0f} Hz, bit ~{bit:.0f} us")
    if a.stats:
        return 0
    bit_us = a.bit_us or bit or 2020
    prev = None
    for t, kind, data, err in messages(decode_bytes(bursts, bit_us, a.parity)):
        if a.no_polls and kind == "POLL" and not err:
            continue
        dt = "" if prev is None else f"+{(t - prev) / 1000:7.1f}ms"
        prev = t
        flags = " [rx error]" if err else ""
        print(f"{t / 1000:10.3f} {dt:>11} {kind:5} {' '.join(f'{b:02X}' for b in data)}{flags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
