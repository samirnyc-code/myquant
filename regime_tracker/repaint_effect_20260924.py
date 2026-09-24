#!/usr/bin/env python3
"""Does Lag-1 repainting change the TREND, or only minor pivots?

Runs the SAME bars/data through the engine at lag=1 (live chart) and lag=3
(finalised, non-repaint) and diffs the regime label. Because only the lag
differs, every difference is purely the repaint window (pivots MyWedge erases
up to 2 bars later that lag=1 acted on and lag>=2 did not).

Reports: bar-level disagreement, and the trend-SEGMENT timelines side by side so
we can see whether a whole trend appears/vanishes, flips direction, or merely
shifts its start/end by a few bars.

    python repaint_effect_20260924.py CSV --session eth|date
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mywedge import compute_mywedge
from regime_tracker import compute_regime
from diff_nt_vs_py import parse_nt_csv, new_session_flags


def regime_at(bars, ins, lag):
    O = [b[1] for b in bars]; H = [b[2] for b in bars]
    L = [b[3] for b in bars]; C = [b[4] for b in bars]
    w = compute_mywedge(O, H, L, C, tick_size=0.25, is_new_session=ins,
                        lookback=12, wedge_symmetry=4, ol_sensitivity=1,
                        ctsb_ignore=True, ib_ignore=True, signal_bar_ibs=66.0,
                        continue_mc=False, continue_on_gap=False, lag=lag)
    return compute_regime(w.swing_low_asof, w.swing_high_asof, L, H, bar_dir=w.bar_dir).regime


def segments(regime):
    """Contiguous non-Range runs -> list of (start, end, label)."""
    segs = []
    i, n = 0, len(regime)
    while i < n:
        if regime[i] != "Range":
            j = i
            while j + 1 < n and regime[j + 1] == regime[i]:
                j += 1
            segs.append((i, j, regime[i]))
            i = j + 1
        else:
            i += 1
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--session", choices=["date", "eth"], default="eth")
    a = ap.parse_args()

    bars, _, _ = parse_nt_csv(a.csv)
    ins = new_session_flags([b[0] for b in bars], a.session)
    times = [b[0] for b in bars]

    r1 = regime_at(bars, ins, 1)
    r3 = regime_at(bars, ins, 3)
    n = len(r1)

    diff = [i for i in range(n) if r1[i] != r3[i]]
    # classify each differing bar
    kinds = {"trend<->range": 0, "bull<->bear": 0}
    for i in diff:
        if "Range" in (r1[i], r3[i]):
            kinds["trend<->range"] += 1
        else:
            kinds["bull<->bear"] += 1

    print(f"file: {a.csv}   bars: {n}   session: {a.session}")
    print(f"bar-level regime diffs lag1 vs lag3: {len(diff)} ({100*len(diff)/n:.2f}%)")
    print(f"   trend<->range: {kinds['trend<->range']}   bull<->bear (direction flip): {kinds['bull<->bear']}")
    print()

    s1, s3 = segments(r1), segments(r3)
    print(f"TREND SEGMENTS  lag1={len(s1)}   lag3={len(s3)}")
    print()

    # match segments by overlap to see appear/vanish/shift/flip
    def overlaps(a1, a3):
        return not (a1[1] < a3[0] or a3[1] < a1[0])

    print("lag3 segment            -> matching lag1 segment(s)   verdict")
    print("-" * 78)
    used1 = set()
    for (s, e, lab) in s3:
        matches = [(i, seg) for i, seg in enumerate(s1) if overlaps((s, e), seg)]
        for i, _ in matches:
            used1.add(i)
        if not matches:
            print(f"  b{s}-{e} {lab:<5} ({times[s][:16]})  -> (none)                 VANISHES at lag1")
        else:
            for i, (a, b, l2) in matches:
                if l2 != lab:
                    v = f"DIRECTION FLIP {lab}->{l2}"
                elif (a, b) == (s, e):
                    v = "identical"
                else:
                    v = f"shift start {a-s:+d} end {b-e:+d}"
                print(f"  b{s}-{e} {lab:<5} ({times[s][:16]})  -> b{a}-{b} {l2:<5}         {v}")
    # lag1 segments with no lag3 match = appear only at lag1
    for i, (a, b, lab) in enumerate(s1):
        if i not in used1:
            print(f"  (none)                              -> b{a}-{b} {lab:<5} ({times[a][:16]})  APPEARS only at lag1")


if __name__ == "__main__":
    main()
