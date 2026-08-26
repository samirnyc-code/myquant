"""wedge_signal_stats.py — stop-size + frequency reality of the MyWedge signals.

Uses ONLY the exported signal CSV (no forward prices needed), so every number
here is exact. The trade's stop distance is fully determined by the signal bar:

    long (BL):  entry = SB.High + off ,  stop = SB.Low  - off
    short (BR): entry = SB.Low  - off ,  stop = SB.High + off
    => stop distance (entry->stop) = (SB.High - SB.Low) + 2*off  [off = StopBeyondSBTicks]

So the signal-bar RANGE is the risk per trade. This tells us the natural stop,
and lets us judge the +4t scalp's reward:risk before we ever touch tick data.

    python research/wedge/wedge_signal_stats.py
        [--csv data/wedge/wedge_signals_ES_2000t_6mo.csv] [--off 1] [--scalp 4]

Outputs (dated): research/wedge/wedge_signal_stats_<stamp>.txt (+ per-signal CSV
with the derived stop-distance column).
"""
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICK = 0.25
TICK_USD = 12.5


def pct(a, q):
    return round(float(np.percentile(a, q)), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"))
    ap.add_argument("--off", type=int, default=1, help="StopBeyondSBTicks (entry/stop offset beyond SB)")
    ap.add_argument("--scalp", type=int, default=4, help="scalp target ticks, for R:R context")
    a = ap.parse_args()

    df = pd.read_csv(a.csv)
    df["SignalTime"] = pd.to_datetime(df["SignalTime"])
    df["range_t"] = ((df["High"] - df["Low"]) / TICK).round().astype(int)
    df["stop_t"] = df["range_t"] + 2 * a.off          # entry->stop distance in ticks
    df["stop_usd"] = df["stop_t"] * TICK_USD
    df["scalp_R"] = a.scalp / df["stop_t"]            # reward:risk of the 4t scalp leg
    df["hour"] = df["SignalTime"].dt.hour
    df["body_t"] = ((df["Close"] - df["Open"]).abs() / TICK).round().astype(int)

    n = len(df)
    days = df["Date"].nunique()
    out = []
    def P(s=""): out.append(s); print(s)

    P(f"MyWedge signal stats — {Path(a.csv).name}")
    P(f"{n} signals over {days} days  ({df['Date'].min()} -> {df['Date'].max()})  "
      f"= {n/days:.1f}/day")
    P(f"offset beyond SB = {a.off}t   scalp target = {a.scalp}t\n")

    P("side split:")
    for s, g in df.groupby("Signal"):
        P(f"  {s} ({'long' if s=='BL' else 'short'}): {len(g)}  ({len(g)/n*100:.1f}%)")

    P("\nSTOP DISTANCE (entry->stop = SB range + 2t), in ticks:")
    st = df["stop_t"].to_numpy()
    P(f"  mean {st.mean():.1f}  median {np.median(st):.0f}  "
      f"p10 {pct(st,10):.0f}  p25 {pct(st,25):.0f}  p75 {pct(st,75):.0f}  "
      f"p90 {pct(st,90):.0f}  max {st.max()}")
    P(f"  in $:  mean ${st.mean()*TICK_USD:,.0f}  median ${np.median(st)*TICK_USD:,.0f}  "
      f"p90 ${pct(st,90)*TICK_USD:,.0f}   (per contract, ${TICK_USD}/tick)")

    P("\nstop-distance histogram (ticks):")
    bins = [0, 4, 6, 8, 10, 12, 16, 20, 30, 10_000]
    lab = ["<=4", "5-6", "7-8", "9-10", "11-12", "13-16", "17-20", "21-30", ">30"]
    cats = pd.cut(df["stop_t"], bins=bins, labels=lab, right=True)
    for l, c in cats.value_counts().reindex(lab).items():
        P(f"  {l:>6}t : {int(c):5d}  ({c/n*100:4.1f}%)")

    P(f"\n+{a.scalp}t SCALP reward:risk  (scalp_R = {a.scalp} / stop_t):")
    sr = df["scalp_R"].to_numpy()
    P(f"  mean {sr.mean():.2f}R  median {np.median(sr):.2f}R  "
      f"share with R>=1: {(sr>=1).mean()*100:.1f}%   R>=0.5: {(sr>=0.5).mean()*100:.1f}%")
    be = 1 / (1 + np.median(sr))    # breakeven win-rate at median R (win +scalp, lose -stop)
    P(f"  breakeven win-rate for the scalp leg at median R:R = {be*100:.0f}%")

    P("\nby hour-of-day (signal bar close, chart/exchange tz):")
    for h, g in df.groupby("hour"):
        P(f"  {h:02d}:00  n={len(g):4d}  medStop={g['stop_t'].median():.0f}t")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = ROOT / "research" / "wedge" / f"wedge_signal_stats_{stamp}.txt"
    txt.write_text("\n".join(out), encoding="utf-8")
    csv = ROOT / "research" / "wedge" / f"wedge_signal_stats_{stamp}.csv"
    df.to_csv(csv, index=False)
    print(f"\nsaved: {txt.relative_to(ROOT)}\nsaved: {csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
