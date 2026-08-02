#!/usr/bin/env python
"""mm50_eth_engine.py — S92-EA: Halsey 50% MM on ETH (24H) bars, NT swings, TICK-THROUGH fills.

Fixes the two things that made the earlier version wrong:
  1. ETH / 24H structure — DH draws on the 24-hour chart (legs form overnight). Bars are built
     from data/bars/_db_es_1m_continuous_24h.parquet (1-min, 24H, back-adjusted continuous).
  2. TICK-THROUGH, never touch — a resting limit fills ONLY when price trades one tick PAST it:
       long 50% limit fills when a 1-min bar's LOW <= e50 - 1tick   (through, not ==)
       123% target (a limit) fills when HIGH >= tgt + 1tick
       61.8% stop is a MARKET stop: triggers on touch (low <= stop) + 1 tick slippage on the fill
     Outcomes are resolved on the 1-MINUTE bars (far finer than 15M; the 15M version created
     phantom targets). Same-minute stop+target -> stop first (conservative).

Swings: NT8 Swing(Strength) (nt_swing.py) on the 24H 15-MIN bars.
Entry window: RTH only (08:30-14:45 CT), flat by 15:00 CT (DH is an intraday, flat-EOD trader);
legs may form overnight but trades are taken and closed in the US session.

Reports win/expectancy/PF/per-year, net of $5 commission. No touch-fills, no 15M phantom targets.

Usage: python scripts/mm50_eth_engine.py [strengths=1,2,3,5] [start=2015-01-01]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars" / "_db_es_1m_continuous_24h.parquet"
OUT = ROOT / "data" / "nt_internals" / "master"
sys.path.insert(0, str(ROOT / "scripts"))
from nt_swing import nt_swing  # noqa: E402
from halsey_mm50_engine import legs_from_pivots  # noqa: E402

TICK = 0.25
COMM = 5.0
ES_PT = 50.0
RTH_START = (8, 30); RTH_ENTRY_END = (14, 45); RTH_FLAT = (15, 0)


def is_rth(ts, lo=RTH_START, hi=RTH_FLAT):
    h, m = ts.hour, ts.minute
    after = (h > lo[0]) or (h == lo[0] and m >= lo[1])
    before = (h < hi[0]) or (h == hi[0] and m <= hi[1])
    return after and before


def load(start):
    m1 = pd.read_parquet(BARS)[["DateTime", "Open", "High", "Low", "Close"]]
    m1 = m1[m1["DateTime"] >= pd.Timestamp(start)].reset_index(drop=True)
    g = m1.set_index("DateTime")
    o = g["Open"].resample("15min").first(); h = g["High"].resample("15min").max()
    l = g["Low"].resample("15min").min(); c = g["Close"].resample("15min").last()
    b15 = pd.DataFrame({"O": o, "H": h, "L": l, "C": c}).dropna().reset_index()
    b15 = b15.rename(columns={"DateTime": "dt"})
    return m1, b15


def run(m1, b15, strength):
    H = b15["H"].to_numpy(); L = b15["L"].to_numpy(); bt = b15["dt"].to_numpy()
    piv = nt_swing(H, L, strength)
    legs = legs_from_pivots(piv, H, L)
    t1 = m1["DateTime"].to_numpy(); h1 = m1["High"].to_numpy(); l1 = m1["Low"].to_numpy()
    c1 = m1["Close"].to_numpy(); n1 = len(m1)
    trades = []
    for jL, jH, kind in legs:
        conf = max(jL, jH) + strength
        if conf >= len(b15):
            continue
        if kind == 'up':
            Lp, Hp = L[jL], H[jH]; R = Hp - Lp
            if R <= 0:
                continue
            e50, stop, tgt, side = Lp + 0.5 * R, Lp + 0.382 * R, Lp + 1.236 * R, 1
        else:
            Hp, Lp = H[jL], L[jH]; R = Hp - Lp
            if R <= 0:
                continue
            e50, stop, tgt, side = Hp - 0.5 * R, Hp - 0.382 * R, Hp - 1.236 * R, -1
        # entry: from the close of the confirmation 15M bar (conf_t + 15min)
        conf_close = pd.Timestamp(bt[conf]) + pd.Timedelta(minutes=15)
        si = int(np.searchsorted(t1, np.datetime64(conf_close)))
        fill_i = None
        for i in range(si, n1):
            ts = pd.Timestamp(t1[i])
            if ts.date() != conf_close.date() and ts > conf_close:
                # only rest the limit through the conf day's RTH; re-draw next day
                if ts.normalize() > conf_close.normalize():
                    break
            if not is_rth(ts, RTH_START, RTH_ENTRY_END):
                continue
            # invalidation: 61.8% ticked through before the 50% fills -> no trade
            if side == 1:
                if l1[i] <= stop - TICK:
                    break
                if l1[i] <= e50 - TICK:      # tick THROUGH the limit
                    fill_i = i; break
            else:
                if h1[i] >= stop + TICK:
                    break
                if h1[i] >= e50 + TICK:
                    fill_i = i; break
        if fill_i is None:
            continue
        # manage: 1-min tick-through, flat by 15:00 CT of the fill day
        rr = (tgt - e50) / (e50 - stop) if side == 1 else (e50 - tgt) / (stop - e50)
        why, R = None, None
        fday = pd.Timestamp(t1[fill_i]).date()
        for k in range(fill_i, n1):
            ts = pd.Timestamp(t1[k])
            if ts.date() != fday or (ts.hour, ts.minute) > RTH_FLAT:
                R = side * (c1[k - 1] - e50) / abs(e50 - stop); why = "mtm"; break
            if side == 1:
                if l1[k] <= stop:                       # market stop on touch
                    R = -1.0 - TICK / (e50 - stop); why = "stop"; break   # + 1tk slippage
                if h1[k] >= tgt + TICK:                  # target limit: through
                    R = rr; why = "target"; break
            else:
                if h1[k] >= stop:
                    R = -1.0 - TICK / (stop - e50); why = "stop"; break
                if l1[k] <= tgt - TICK:
                    R = rr; why = "target"; break
        if why is None:
            R = side * (c1[n1 - 1] - e50) / abs(e50 - stop); why = "mtm"
        comm_R = COMM / (abs(e50 - stop) * ES_PT)
        trades.append({"dt": pd.Timestamp(t1[fill_i]), "year": pd.Timestamp(t1[fill_i]).year,
                       "side": side, "why": why, "R": R, "net_R": R - comm_R,
                       "risk_pts": abs(e50 - stop), "strength": strength})
    return pd.DataFrame(trades)


def stats(d, col="net_R"):
    if not len(d):
        return "n=0"
    w = d[d[col] > 0][col].sum(); l = -d[d[col] < 0][col].sum()
    pf = w / l if l else np.inf
    yr = d.groupby("year")[col].mean()
    return (f"n={len(d):5d}  win={100*(d[col]>0).mean():4.1f}%  exp={d[col].mean():+.3f}R  "
            f"PF={pf:4.2f}  years+={(yr>0).sum()}/{len(yr)}")


def main():
    strengths = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["1", "2", "3", "5"])]
    start = sys.argv[2] if len(sys.argv) > 2 else "2015-01-01"
    m1, b15 = load(start)
    print(f"ETH 1m bars: {len(m1):,} | 15M bars: {len(b15):,} | "
          f"{b15['dt'].min()} .. {b15['dt'].max()}")
    allt = []
    print("\n=== ETH 50% MM, NT swings, TICK-THROUGH fills, 1-min outcomes, net of $5 comm ===")
    for s in strengths:
        d = run(m1, b15, s); allt.append(d)
        vc = d["why"].value_counts()
        print(f"\nstrength {s}:  {stats(d)}")
        print(f"   outcomes: target={vc.get('target',0)} stop={vc.get('stop',0)} "
              f"mtm={vc.get('mtm',0)} | median risk {d['risk_pts'].median()*4:.0f}tk "
              f"(${d['risk_pts'].median()*ES_PT:.0f})")
    full = pd.concat(allt, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUT / "mm50_eth_trades.csv", index=False)
    print(f"\nwrote {(OUT / 'mm50_eth_trades.csv').relative_to(ROOT)}  ({len(full)} trades)")


if __name__ == "__main__":
    main()
