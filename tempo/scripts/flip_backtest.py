"""flip_backtest.py — climax-flip setup backtest, exact NT indicator rules (S117-tempo).

Data: tempo_engine_bars.parquet (bar-exact port of the v2 indicators). Default window:
last 252 sessions; full history added as context.

=== FROZEN SPEC (mirrors TempoSpeedometer.RenderClimaxFlips / SimFlipSession) ===
Signal: adjacent opposite-direction CLIMAX bars (engine climax flag; bull = close>=open).
  bull->bear = SHORT, bear->bull = LONG. Entry = close of bar 2.
Stop: 1 tick (0.25) beyond the 2-bar extreme. ONE TRADE AT A TIME per session:
  signals during an open trade are skipped; open at session end -> marked to last close.
Exit variants:
  RR3   : target = entry +/- 3 x risk;   both-in-bar -> STOP (conservative)
  SCALP6: target = entry +/- 6 ticks (1.5 pt), same stop; both-in-bar -> STOP
Reach (RR3 only): max of 1R/2R/3R touched before exit.
CAVEAT: intrabar path unknown on 2000t OHLC (median bar range ~4pt vs 1.5pt scalp
target) -> both-in-bar cases resolve to STOP, so results are conservative lower
bounds; the scalp variant is the more affected one.

Outputs: flip_backtest_trades_<date>.csv + summary txt + inline.
    python tempo/scripts/flip_backtest.py [--days 252]
"""
from __future__ import annotations
import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
SCALP = 1.5


def sim_day(g: pd.DataFrame, variant: str) -> list:
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    busy_until = -1
    for i in range(1, n):
        if i <= busy_until or not (cx[i] and cx[i - 1]):
            continue
        u1, u2 = c[i - 1] >= o[i - 1], c[i] >= o[i]
        if u1 == u2:
            continue
        short = u1 and not u2
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        tgt = (en - 3 * rk if short else en + 3 * rk) if variant == "RR3" else \
              (en - SCALP if short else en + SCALP)
        r1v = en - rk if short else en + rk
        r2v = en - 2 * rk if short else en + 2 * rk
        res, end, reach = 0, n - 1, 0
        for j in range(i + 1, n):
            hs = h[j] >= st if short else l[j] <= st
            ht = (l[j] <= tgt if short else h[j] >= tgt)
            if hs:
                res, end = 1, j; break
            if ht:
                res, end, reach = 2, j, 3; break
            if reach < 2 and (l[j] <= r2v if short else h[j] >= r2v):
                reach = 2
            elif reach < 1 and (l[j] <= r1v if short else h[j] >= r1v):
                reach = 1
        if res == 1:
            pnl = -rk
        elif res == 2:
            pnl = 3 * rk if variant == "RR3" else SCALP
        else:
            pnl = (en - c[n - 1]) if short else (c[n - 1] - en)   # marked to session close
        trades.append({"date": g["date"].iloc[0], "bar": int(g["bar"].iloc[i]),
                       "time": str(g["start"].iloc[i])[11:19], "side": "S" if short else "L",
                       "risk": rk, "res": ["open", "stop", "target"][res],
                       "reach": reach, "pnl_pts": pnl,
                       "pnl_R": pnl / rk if rk > 0 else 0,
                       "session_min": float(g["session_min"].iloc[i])})
        busy_until = n if res == 0 else end
    return trades


def summarize(t: pd.DataFrame, name: str) -> str:
    lines = [f"--- {name}: n={len(t)} over {t['date'].nunique()} sessions "
             f"({len(t)/max(1,t['date'].nunique()):.2f}/day) ---"]
    for res, g in t.groupby("res"):
        lines.append(f"  {res:>6}: {len(g):>4} ({len(g)/len(t):.1%})")
    wr = (t["res"] == "target").mean()
    lines.append(f"  win rate {wr:.1%}   total {t['pnl_pts'].sum():+.2f} pts "
                 f"({t['pnl_R'].sum():+.1f}R)   avg/trade {t['pnl_pts'].mean():+.3f} pts "
                 f"({t['pnl_R'].mean():+.3f}R)   avg risk {t['risk'].mean():.2f} pts")
    for s, g in t.groupby("side"):
        lines.append(f"  {'short' if s=='S' else 'long':>6}: n={len(g)} win {(g['res']=='target').mean():.1%} "
                     f"avg {g['pnl_pts'].mean():+.3f} pts")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=252)
    a = ap.parse_args()
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())
    last = all_dates[-a.days:]

    out_rows, lines = [], []
    for scope, dates in [("1yr", last), ("full", all_dates)]:
        sub = df[df["date"].isin(dates)]
        for variant in ["RR3", "SCALP6"]:
            trades = []
            for _, g in sub.groupby("date"):
                trades += sim_day(g.reset_index(drop=True), variant)
            t = pd.DataFrame(trades)
            t["variant"] = variant; t["scope"] = scope
            out_rows.append(t)
            lines.append(summarize(t, f"{scope} {variant}"))
            if scope == "1yr" and variant == "RR3":
                rr = t[t["res"] != "open"]
                lines.append("  reach (before exit): >=1R {:.1%}  >=2R {:.1%}  3R {:.1%}".format(
                    (rr["reach"] >= 1).mean(), (rr["reach"] >= 2).mean(), (rr["reach"] >= 3).mean()))
                t["month"] = t["date"].str[:7]
                lines.append("  by month (pts): " + "  ".join(
                    f"{m}:{g['pnl_pts'].sum():+.1f}" for m, g in t.groupby("month")))
                t["hour"] = (t["session_min"] // 60).astype(int)
                lines.append("  by session hour (n / avg pts): " + "  ".join(
                    f"h{hh}:{len(g)}/{g['pnl_pts'].mean():+.2f}" for hh, g in t.groupby("hour")))
    allt = pd.concat(out_rows, ignore_index=True)
    allt.to_csv(OUT / f"flip_backtest_trades_{today}.csv", index=False)
    txt = "\n\n".join(lines)
    (OUT / f"flip_backtest_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
