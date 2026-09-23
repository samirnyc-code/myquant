#!/usr/bin/env python3
"""Full bar-by-bar comparison of two RegimeTracker CSV exports, joined by bar index.

Both files share the same bar-number field, so we join on it (timezone/time
differences are ignored on purpose). For every bar present in BOTH files we
compare OHLC and the regime label; we also compare the BOS/ChoCh event set over
the overlapping bar range. Reports every mismatch, not a sample.

    python compare_two_exports.py FILE_A FILE_B
"""
import csv
import sys


def load(path):
    bars = {}   # bar -> (o,h,l,c,regime,time)
    events = {} # bar -> set of (kind,dir)
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or row[0] == "type":
                continue
            t = row[0]
            if t == "BAR":
                b = int(row[1])
                bars[b] = (row[3], row[4], row[5], row[6], row[7], row[2])
            elif t == "EVT":
                b = int(row[1])
                events.setdefault(b, set()).add((row[8], row[9]))
    return bars, events


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    A_bars, A_evt = load(a_path)
    B_bars, B_evt = load(b_path)

    overlap = sorted(set(A_bars) & set(B_bars))
    lo, hi = (overlap[0], overlap[-1]) if overlap else (None, None)

    regime_mismatch = []
    ohlc_mismatch = []
    for b in overlap:
        ao, ah, al, ac, areg, _ = A_bars[b]
        bo, bh, bl, bc, breg, _ = B_bars[b]
        if areg != breg:
            regime_mismatch.append((b, areg, breg))
        if (ao, ah, al, ac) != (bo, bh, bl, bc):
            ohlc_mismatch.append((b, (ao, ah, al, ac), (bo, bh, bl, bc)))

    # events over the overlapping bar range only
    evt_mismatch = []
    for b in overlap:
        ea = A_evt.get(b, set())
        eb = B_evt.get(b, set())
        if ea != eb:
            evt_mismatch.append((b, sorted(ea), sorted(eb)))

    n = len(overlap)
    print(f"FILE A: {a_path}")
    print(f"  bars {min(A_bars)}..{max(A_bars)}  ({len(A_bars)} bars, {sum(len(v) for v in A_evt.values())} events)")
    print(f"FILE B: {b_path}")
    print(f"  bars {min(B_bars)}..{max(B_bars)}  ({len(B_bars)} bars, {sum(len(v) for v in B_evt.values())} events)")
    print()
    print(f"OVERLAP: bars {lo}..{hi}  ({n} bars compared)")
    print()
    print(f"REGIME label:  {n - len(regime_mismatch)}/{n} match  ({len(regime_mismatch)} differ)")
    print(f"OHLC (all 4):  {n - len(ohlc_mismatch)}/{n} match  ({len(ohlc_mismatch)} differ)")
    print(f"EVENTS/bar:    {n - len(evt_mismatch)}/{n} bars match  ({len(evt_mismatch)} differ)")
    print()

    if ohlc_mismatch:
        first = ohlc_mismatch[0][0]
        print(f"first OHLC divergence at bar {first}")
        print(f"  A time {A_bars[first][5]}  OHLC {A_bars[first][:4]}")
        print(f"  B time {B_bars[first][5]}  OHLC {B_bars[first][:4]}")
        print(f"  ({len(ohlc_mismatch)} bars have any OHLC diff; range {ohlc_mismatch[0][0]}..{ohlc_mismatch[-1][0]})")
        print()

    if regime_mismatch:
        print(f"ALL {len(regime_mismatch)} regime-label mismatches (bar | A | B | A_time | B_time):")
        for b, ra, rb in regime_mismatch:
            print(f"  {b:>6} | A={ra:<6} B={rb:<6} | {A_bars[b][5]} | {B_bars[b][5]}")
    else:
        print("regime labels: NO mismatches across the entire overlap.")
    print()

    if evt_mismatch:
        print(f"ALL {len(evt_mismatch)} bars with event differences (bar | A-only | B-only):")
        for b, ea, eb in evt_mismatch:
            aonly = [e for e in ea if e not in eb]
            bonly = [e for e in eb if e not in ea]
            print(f"  {b:>6} | A-only={aonly} | B-only={bonly}")
    else:
        print("events: NO differences across the overlapping bar range.")


if __name__ == "__main__":
    main()
