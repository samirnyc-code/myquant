"""flip_sar_backtest.py — climax-flip variant 1: STOP-AND-REVERSE + IBS direction (S117-tempo).

User rule (2026-09-12 screenshot): if an opposite-direction flip signal completes while
a trade is open, exit AT THAT BAR'S CLOSE and reverse into the new trade immediately
(instead of skipping signals until stop/3R). Also tests direction classification:
  COLOR  bull = close>=open (current indicator behavior)
  IBS    bull = IBS>=0.55, bear = IBS<=0.45, middle band = bar cannot be a signal bar
         (IBS = (close-low)/(high-low))

Grid: {COLOR, IBS} x {SKIP (baseline), SAR} on RR3 (target 3R, stop 1 tick beyond the
2-bar box, both-in-bar -> stop, one position, sessions independent, open at session
end marked to last close). Scopes: last 252 sessions + full history.

    python tempo/scripts/flip_sar_backtest.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25


def bar_dir(o, h, l, c, i, ibs_mode):
    if not ibs_mode:
        return 1 if c[i] >= o[i] else -1
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    ibs = (c[i] - l[i]) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def sim_day(g, ibs_mode, sar):
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    pos = None                       # dict: i, short, en, st, tg, rk, r1, r2, reach
    for i in range(1, n):
        if pos is not None:
            sh = pos["short"]
            hs = h[i] >= pos["st"] if sh else l[i] <= pos["st"]
            ht = l[i] <= pos["tg"] if sh else h[i] >= pos["tg"]
            if hs:
                trades.append({**pos, "res": "stop", "end": i, "pnl": -pos["rk"]}); pos = None
            elif ht:
                pos["reach"] = 3
                trades.append({**pos, "res": "target", "end": i, "pnl": 3 * pos["rk"]}); pos = None
            else:
                if pos["reach"] < 2 and (l[i] <= pos["r2"] if sh else h[i] >= pos["r2"]):
                    pos["reach"] = 2
                elif pos["reach"] < 1 and (l[i] <= pos["r1"] if sh else h[i] >= pos["r1"]):
                    pos["reach"] = 1
        if not (cx[i] and cx[i - 1]):
            continue
        d1 = bar_dir(o, h, l, c, i - 1, ibs_mode)
        d2 = bar_dir(o, h, l, c, i, ibs_mode)
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if pos is not None:
            if sar and sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "end": i,
                               "pnl": (c[i] - pos["en"]) * sgn})
                pos = None
            else:
                continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        pos = {"i": i, "short": sig_short, "en": en, "st": st, "rk": rk,
               "tg": en + sgn * 3 * rk, "r1": en + sgn * rk, "r2": en + sgn * 2 * rk,
               "reach": 0, "date": g["date"].iloc[0]}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "end": n - 1, "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())
    lines, rows = [], []
    for scope, dates in [("1yr", all_dates[-252:]), ("full", all_dates)]:
        sub = df[df["date"].isin(dates)]
        byday = {d: g.reset_index(drop=True) for d, g in sub.groupby("date")}
        for ibs in [False, True]:
            for sar in [False, True]:
                trades = []
                for d in byday:
                    trades += sim_day(byday[d], ibs, sar)
                t = pd.DataFrame(trades)
                t["variant"] = f"{'IBS' if ibs else 'COLOR'}-{'SAR' if sar else 'SKIP'}"
                t["scope"] = scope
                rows.append(t)
                rpt = t["pnl"] / t["rk"]
                cnt = t["res"].value_counts().to_dict()
                lines.append(f"{scope:>4} {'IBS' if ibs else 'COLOR':>5}-{'SAR' if sar else 'SKIP':<4} "
                             f"n={len(t):>4}  {cnt}  total {t['pnl'].sum():+8.2f} pt "
                             f"({rpt.sum():+7.1f}R)  avg {t['pnl'].mean():+.3f} pt/trade "
                             f"({rpt.mean():+.3f}R)")
    allt = pd.concat(rows, ignore_index=True)
    allt.to_csv(OUT / f"flip_sar_trades_{today}.csv", index=False)
    txt = "\n".join(lines)
    (OUT / f"flip_sar_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
