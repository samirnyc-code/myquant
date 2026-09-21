#!/usr/bin/env python3
"""Run the ported MyWedge indicator on a NinjaTrader bar export and write a signals CSV.

Input file format (whitespace-separated, thousands commas OK) — either:
  Date Time O H L C                          (plain bar export)
  Date Time O H L C SwingLow SwingHigh       (Pivots export; extra cols ignored for signals,
                                              used for --validate-swings)
Date is dd/mm/yyyy, Time HH:MM:SS. Header/dashes lines are skipped automatically.

Usage:
  python3 run_mywedge.py BARS.txt [--out signals.csv]
                         [--tz Europe/Berlin] [--session eth|rth-cash]
                         [--no-w2l] [--validate SIGNAL_EXPORT.txt] [--validate-swings]

Defaults reproduce Thomas's ETH exports: tz=Europe/Berlin, ETH sessions (17:00 CT roll),
ShowW2L on, and the MyWedge indicator defaults (lookback 12, symmetry 4, OL 1,
Ignore SB/IB on, SignalBarIBS 66). ES tick size 0.25.
"""
import sys, csv, math, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from mywedge import compute_mywedge, is_new_session_cme_eth, bars_since_new_session

CT = ZoneInfo("America/Chicago")


def parse_bars(path, tz):
    z = ZoneInfo(tz)
    rows = []
    swings = []
    for line in open(path).readlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        p = line.split()
        # need at least Date Time O H L C, with a parseable date in p[0]
        if len(p) < 6 or "/" not in p[0]:
            continue
        try:
            dt = datetime.strptime(f"{p[0]} {p[1]}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=z)
            o, h, l, c = (float(p[i].replace(",", "")) for i in range(2, 6))
        except ValueError:
            continue
        rows.append((dt, o, h, l, c))
        if len(p) >= 8:
            sl = None if p[6] == "n/a" else float(p[6].replace(",", ""))
            sh = None if p[7] == "n/a" else float(p[7].replace(",", ""))
            swings.append((sl, sh))
        else:
            swings.append((None, None))
    rows.sort(key=lambda r: r[0])
    return rows, swings


def parse_signals(path):
    """Author signal export -> set of (Direction, Date, Time)."""
    out = set()
    import re
    for line in open(path).readlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        p = re.split(r"\s+", line)
        if len(p) >= 4 and p[1] in ("W_Long", "W_Short"):
            out.add((p[1], p[2], p[3]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tz", default="Europe/Berlin")
    ap.add_argument("--session", default="eth", choices=["eth", "rth-cash"])
    ap.add_argument("--no-w2l", action="store_true")
    ap.add_argument("--tick-size", type=float, default=0.25)
    ap.add_argument("--validate", default=None, help="author signal export to compare against")
    ap.add_argument("--validate-swings", action="store_true", help="compare swing map vs Pivots cols")
    a = ap.parse_args()

    rows, swings = parse_bars(a.bars, a.tz)
    if not rows:
        sys.exit(f"no bars parsed from {a.bars}")
    ts = [r[0] for r in rows]
    O = [r[1] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]; C = [r[4] for r in rows]

    if a.session == "eth":
        ins = is_new_session_cme_eth(ts)          # 17:00 CT roll
    else:  # rth-cash: new session each 08:30 CT weekday
        ins = []
        prev = None
        for t in ts:
            ct = t.astimezone(CT); day = ct.date()
            ins.append(day != prev); prev = day

    w = compute_mywedge(O, H, L, C, tick_size=a.tick_size, is_new_session=ins,
                        lookback=12, show_w2l=not a.no_w2l, wedge_symmetry=4, ol_sensitivity=1,
                        ctsb_ignore=True, ib_ignore=True, show_wedge_sb=True,
                        signal_bar_ibs=66.0, continue_mc=False, continue_on_gap=False)

    out = a.out or (a.bars.rsplit(".", 1)[0] + "_signals.csv")
    n = len(rows); cnt = 0
    with open(out, "w", newline="") as fo:
        wr = csv.writer(fo)
        wr.writerow(["Counter", "Direction", "Date", "Time", "O", "H", "L", "C", "WedgeSB", "MC_Bull", "MC_Bear"])
        for i in range(n):
            for side, arr in (("W_Long", w.wedge_bl_sb), ("W_Short", w.wedge_br_sb)):
                if not math.isnan(arr[i]):
                    cnt += 1
                    wr.writerow([cnt, side, ts[i].strftime("%d/%m/%Y"), ts[i].strftime("%H:%M:%S"),
                                 O[i], H[i], L[i], C[i], round(arr[i], 2),
                                 "" if math.isnan(w.mc_bull[i]) else int(w.mc_bull[i]),
                                 "" if math.isnan(w.mc_bear[i]) else int(w.mc_bear[i])])
    longs = sum(1 for x in w.wedge_bl_sb if not math.isnan(x))
    shorts = sum(1 for x in w.wedge_br_sb if not math.isnan(x))
    print(f"{n:,} bars | {longs} long + {shorts} short = {cnt} signals -> {out}")

    if a.validate_swings:
        tp = tn = fp = fn = 0
        for i in range(n):
            for ref, arr in ((swings[i][0], w.swing_low), (swings[i][1], w.swing_high)):
                rp = ref is not None; pp = not math.isnan(arr[i])
                if rp and pp: tp += 1
                elif not rp and not pp: tn += 1
                elif rp: fn += 1
                else: fp += 1
            # note: counts both SL and SH together per bar
        agree = tp + tn
        print(f"swings: {agree}/{2*n} agree ({100*agree/(2*n):.3f}%)  set:{tp}  missed:{fn}  extra:{fp}")

    if a.validate:
        author = parse_signals(a.validate)
        idx = {(ts[i].strftime("%d/%m/%Y"), ts[i].strftime("%H:%M:%S")): i for i in range(n)}
        port = set()
        for i in range(n):
            if not math.isnan(w.wedge_bl_sb[i]): port.add(("W_Long",) + tuple(ts[i].strftime("%d/%m/%Y %H:%M:%S").split()))
            if not math.isnan(w.wedge_br_sb[i]): port.add(("W_Short",) + tuple(ts[i].strftime("%d/%m/%Y %H:%M:%S").split()))

        def is_rth(i):
            t = ts[i].astimezone(CT); m = t.hour * 60 + t.minute
            return 8 * 60 + 30 <= m < 15 * 60 + 15 and t.weekday() < 5
        def sub(S): return {k for k in S if (k[1], k[2]) in idx and is_rth(idx[(k[1], k[2])])}
        print(f"validate ETH: match {len(author & port)}  miss {len(author - port)}  extra {len(port - author)}  (author {len(author)})")
        aR, pR = sub(author), sub(port)
        pct = 100 * len(aR & pR) / len(aR) if aR else 0
        print(f"validate RTH: match {len(aR & pR)}/{len(aR)} ({pct:.3f}%)  miss {len(aR - pR)}  extra {len(pR - aR)}")


if __name__ == "__main__":
    main()
