#!/usr/bin/env python3
"""Per-session breakdown of two RegimeTracker exports, joined by bar index.

Splits every difference by CALENDAR DAY (A's CT date) and attributes it to a cause:
  - OHLC (tick) difference: the two exports saw different ticks on that bar.
  - regime difference on a byte-IDENTICAL bar: would be an engine/config diff,
    EXCEPT when it is stateful carry-forward from a tick diff earlier in the day.
    We flag whether the day has ANY pre-tick-diff regime split (the clean engine tell).

    python breakdown_by_day_20260924.py FILE_A FILE_B
"""
import csv
import sys
from collections import defaultdict


def load(path):
    bars, evt = {}, defaultdict(set)
    for r in csv.reader(open(path, newline="")):
        if not r:
            continue
        if r[0] == "BAR":
            bars[int(r[1])] = (r[3], r[4], r[5], r[6], r[7], r[2])  # o,h,l,c,reg,time
        elif r[0] == "EVT":
            evt[int(r[1])].add((r[8], r[9]))
    return bars, evt


def day(t):
    return t[:10]


def main():
    A, Ae = load(sys.argv[1])
    B, Be = load(sys.argv[2])
    overlap = sorted(set(A) & set(B))

    per = defaultdict(lambda: dict(bars=0, ohlc=0, maxd=0.0, reg=0, reg_ident=0,
                                   evt=0, first_ohlc=None, first_reg=None))
    for b in overlap:
        ao, ah, al, ac, areg, at = A[b]
        bo, bh, bl, bc, breg, _ = B[b]
        d = per[day(at)]
        d["bars"] += 1
        ohlc_diff = (ao, ah, al, ac) != (bo, bh, bl, bc)
        if ohlc_diff:
            d["ohlc"] += 1
            md = max(abs(float(x) - float(y)) for x, y in
                     ((ao, bo), (ah, bh), (al, bl), (ac, bc)))
            d["maxd"] = max(d["maxd"], md)
            if d["first_ohlc"] is None:
                d["first_ohlc"] = b
        if areg != breg:
            d["reg"] += 1
            if not ohlc_diff:
                d["reg_ident"] += 1
            if d["first_reg"] is None:
                d["first_reg"] = b
        if Ae.get(b, set()) != Be.get(b, set()):
            d["evt"] += 1

    # header
    print(f"{'date (CT)':<12} {'bars':>5} {'OHLCd':>6} {'maxΔ':>5} {'regd':>5} "
          f"{'r@ident':>8} {'evtd':>5}  cause")
    print("-" * 74)
    tot = dict(bars=0, ohlc=0, reg=0, reg_ident=0, evt=0)
    for d in sorted(per):
        x = per[d]
        for k in tot:
            tot[k] += x[k]
        # cause tag: is the first regime split BEFORE the first tick diff?
        if x["reg"] == 0:
            cause = "clean"
        elif x["first_ohlc"] is None:
            cause = "ENGINE (regime diff, no tick diff at all)"
        elif x["first_reg"] < x["first_ohlc"]:
            cause = f"ENGINE (reg@{x['first_reg']} < tick@{x['first_ohlc']})"
        else:
            cause = f"tick-data (tick@{x['first_ohlc']} first)"
        print(f"{d:<12} {x['bars']:>5} {x['ohlc']:>6} {x['maxd']:>5.2f} {x['reg']:>5} "
              f"{x['reg_ident']:>8} {x['evt']:>5}  {cause}")
    print("-" * 74)
    print(f"{'TOTAL':<12} {tot['bars']:>5} {tot['ohlc']:>6} {'':>5} {tot['reg']:>5} "
          f"{tot['reg_ident']:>8} {tot['evt']:>5}")


if __name__ == "__main__":
    main()
