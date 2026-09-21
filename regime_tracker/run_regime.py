#!/usr/bin/env python3
"""Run compute_mywedge() + compute_regime() and export data for charting.

Usage:
  python run_regime.py [BARS.txt] [--out regime_data.json]
                        [--tz Europe/Berlin] [--session eth|rth-cash]

Same bar file format as run_mywedge.py (Date Time O H L C, dd/mm/yyyy HH:MM:SS).
If BARS.txt is omitted, generates a synthetic demo series (bull -> range -> bear)
so the regime tracker can be demoed without a real NinjaTrader export.

Writes a JSON file with bars, mywedge swing pivots, and the regime timeline,
consumed by the chart artifact / PNG renderer.
"""
import sys, os, json, math, argparse, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mywedge import compute_mywedge, is_new_session_cme_eth
from regime_tracker import compute_regime

CT = ZoneInfo("America/Chicago")


def parse_bars(path, tz):
    z = ZoneInfo(tz)
    rows = []
    for line in open(path).readlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        p = line.split()
        if len(p) < 6 or "/" not in p[0]:
            continue
        try:
            dt = datetime.strptime(f"{p[0]} {p[1]}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=z)
            o, h, l, c = (float(p[i].replace(",", "")) for i in range(2, 6))
        except ValueError:
            continue
        rows.append((dt, o, h, l, c))
    rows.sort(key=lambda r: r[0])
    return rows


def synthetic_demo(seed=7):
    """Bull trend -> trading range -> bear trend, daily bars, so the regime
    tracker's HH/HL vs LH/LL classification has clean, visually obvious phases
    to demonstrate against."""
    random.seed(seed)
    rows = []
    px = 4200.0
    start = datetime(2025, 1, 6, tzinfo=CT)  # a Monday

    def add_bar(drift, vol, d):
        nonlocal px
        op = px
        cl = px + drift + random.uniform(-vol, vol)
        hi = max(op, cl) + random.uniform(0, vol * 0.6)
        lo = min(op, cl) - random.uniform(0, vol * 0.6)
        px = cl
        rows.append((d, op, hi, lo, cl))

    d = start
    n_bull, n_range, n_bear = 90, 60, 90
    for _ in range(n_bull):
        add_bar(drift=random.uniform(2, 9), vol=6.0, d=d)
        d += timedelta(days=1)
    for _ in range(n_range):
        add_bar(drift=random.uniform(-4, 4), vol=7.0, d=d)
        d += timedelta(days=1)
    for _ in range(n_bear):
        add_bar(drift=random.uniform(-9, -2), vol=6.0, d=d)
        d += timedelta(days=1)

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bars", nargs="?", default=None)
    ap.add_argument("--out", default="regime_data.json")
    ap.add_argument("--tz", default="Europe/Berlin")
    ap.add_argument("--session", default="eth", choices=["eth", "rth-cash"])
    ap.add_argument("--tick-size", type=float, default=0.25)
    a = ap.parse_args()

    demo = a.bars is None
    rows = synthetic_demo() if demo else parse_bars(a.bars, a.tz)
    if not rows:
        sys.exit(f"no bars parsed from {a.bars}")

    ts = [r[0] for r in rows]
    O = [r[1] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]; C = [r[4] for r in rows]

    if demo:
        ins = [False] * len(ts)
        prev = None
        for i, t in enumerate(ts):
            ins[i] = t.date() != prev
            prev = t.date()
    elif a.session == "eth":
        ins = is_new_session_cme_eth(ts)
    else:
        ins = []
        prev = None
        for t in ts:
            day = t.astimezone(CT).date()
            ins.append(day != prev)
            prev = day

    w = compute_mywedge(O, H, L, C, tick_size=a.tick_size, is_new_session=ins,
                         lookback=12, show_w2l=True, wedge_symmetry=4, ol_sensitivity=1,
                         ctsb_ignore=True, ib_ignore=True, show_wedge_sb=True,
                         signal_bar_ibs=66.0, continue_mc=False, continue_on_gap=False)

    r = compute_regime(w.swing_low, w.swing_high, L, H, bar_dir=w.bar_dir)

    n = len(rows)
    segments = []
    for k, (idx, label) in enumerate(r.change_points):
        end = r.change_points[k + 1][0] if k + 1 < len(r.change_points) else n
        segments.append({"start": idx, "end": end, "regime": label})

    data = {
        "bars": [
            {"t": ts[i].isoformat(), "o": O[i], "h": H[i], "l": L[i], "c": C[i]}
            for i in range(n)
        ],
        "regime": r.regime,
        "segments": segments,
        "pivot_lows": [{"i": i, "price": p, "major": m} for i, p, m in r.pivot_lows],
        "pivot_highs": [{"i": i, "price": p, "major": m} for i, p, m in r.pivot_highs],
    }
    with open(a.out, "w") as f:
        json.dump(data, f)

    counts = {}
    for lbl in r.regime:
        counts[lbl] = counts.get(lbl, 0) + 1
    print(f"{n:,} bars ({'synthetic demo' if demo else a.bars}) -> {a.out}")
    print(f"{len(segments)} regime segments: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
