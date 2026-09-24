#!/usr/bin/env python3
"""Cross-tabulate regime-label mismatches against OHLC mismatches for two exports.

The forensic question (S123): a regime flip on a byte-IDENTICAL OHLC bar can only
come from an engine/config/build difference. A regime flip where the OHLC ALSO
differs is explainable by the tick data. This splits the 91 regime mismatches
into those two buckets and reports the first regime split relative to the first
OHLC divergence.

    python crosstab_regime_vs_ohlc_20260924.py FILE_A FILE_B
"""
import csv
import sys


def load(path):
    bars = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row or row[0] != "BAR":
                continue
            b = int(row[1])
            bars[b] = (row[3], row[4], row[5], row[6], row[7], row[2])  # o,h,l,c,regime,time
    return bars


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    A = load(a_path)
    B = load(b_path)
    overlap = sorted(set(A) & set(B))

    first_ohlc = None
    regime_on_identical = []   # engine/config difference — the smoking gun
    regime_on_diff_ohlc = []   # explainable by tick data
    for b in overlap:
        ao, ah, al, ac, areg, at = A[b]
        bo, bh, bl, bc, breg, bt = B[b]
        ohlc_diff = (ao, ah, al, ac) != (bo, bh, bl, bc)
        if ohlc_diff and first_ohlc is None:
            first_ohlc = b
        if areg != breg:
            (regime_on_diff_ohlc if ohlc_diff else regime_on_identical).append((b, areg, breg, at))

    print(f"overlap bars {overlap[0]}..{overlap[-1]}  ({len(overlap)} compared)")
    print(f"first OHLC divergence at bar {first_ohlc}")
    print()
    print(f"regime mismatches on IDENTICAL OHLC (=> engine/config diff): {len(regime_on_identical)}")
    for b, ra, rb, t in regime_on_identical:
        print(f"    bar {b:>6} | A={ra:<6} B={rb:<6} | A_time {t}")
    print()
    print(f"regime mismatches where OHLC ALSO differs (=> tick data):    {len(regime_on_diff_ohlc)}")
    if regime_on_diff_ohlc:
        lo = regime_on_diff_ohlc[0][0]
        hi = regime_on_diff_ohlc[-1][0]
        print(f"    range bars {lo}..{hi}")

    print()
    if not regime_on_identical:
        print("VERDICT: zero regime flips on byte-identical bars — the engines now AGREE.")
        print("         all remaining regime diffs sit in the tick-data-different zone.")
    else:
        print("VERDICT: engine/config STILL differs — see the identical-OHLC flips above.")


if __name__ == "__main__":
    main()
