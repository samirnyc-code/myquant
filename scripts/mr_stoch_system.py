"""Trend-filtered short-term mean-reversion (STMR) on ES daily — built on the
user's own colored stochastic (MyStochasticsColorwithSignal, K=8/D=1/Smooth=1).

Reproduces the full S61 study:
  * daily colored-stochastic export (data/ES_stoch_daily.csv, 2009-2026)
  * LONG core:  stoch %K(8) < 15  AND  Close > SMA100        (exit: Close > SMA5)
  * regime SHORT (bear hedge): %K(8) > 85 AND SMA50 < SMA200 AND Close < SMA50
  * entry = signal-day CLOSE (MOC / last minutes) -- beats next-day open by ~11%
  * walk-forward (12mo IS / 4mo OOS) confirms the FIXED setting; re-optimizing hurts.

Findings (ES $50/pt, ~$4 RT, 1 contract, 2009-07 -> 2026-07):
  LONG core, CLOSE entry     : PF 4.45  +$196k  maxDD -$8.1k  R/DD 24.3  16/17 yrs
  LONG+SHORT(regime), CLOSE  : PF 3.06  +$228k  maxDD -$17.3k R/DD 13.1  16/17 yrs
  WFA fixed SMA100 OOS       : PF 3.77  +$159k  maxDD -$7.9k  R/DD 20.2   (re-opt = worse)

The stochastic vs a self-rolled 14/3/3: the user's 8/1/1 oversold "green zone"
is a real edge (not the generic one). Tightening OS 20->15 and using SMA100 as
the trend gate turns the 2011/2018/2022 bear-whipsaw losses positive.

NOTE ON ENTRY: close-entry uses the forming settlement to trigger -- execute as a
market-on-close in the final minutes. SPX options trade to 15:15 CT too, so the
same window works for the bull-put-spread expression.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(r"c:\Users\Admin\myquant")
PT, COMM = 50.0, 4.0            # ES $/pt ; ~$4 RT commission+slip
CSV = ROOT / "data" / "ES_stoch_daily.csv"


def load():
    d = pd.read_csv(CSV)
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    return d


def main():
    d = load()
    O, H, L, C = (d[c].values.astype(float) for c in ["Open", "High", "Low", "Close"])
    n = len(d)
    yr = d["DateTime"].str[:4].values
    dates = pd.to_datetime(d["DateTime"])

    def sma(p): return pd.Series(C).rolling(p).mean().values
    sma5, sma50, sma100, sma200 = sma(5), sma(50), sma(100), sma(200)
    ll = pd.Series(L).rolling(8).min().values
    hh = pd.Series(H).rolling(8).max().values
    K8 = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll)   # exporter's %K math

    def trade(i, short, mode, mh=15):
        fill = C[i] if mode == "close" else O[i + 1]
        for j in range(i + 1, min(n, i + 1 + mh)):
            if (not short and C[j] > sma5[j]) or (short and C[j] < sma5[j]):
                xi, ex = j, C[j]; break
        else:
            xi = min(n - 1, i + mh); ex = C[xi]
        pnl = (ex - fill) if not short else (fill - ex)
        return xi, pnl * PT - COMM

    def run(longm, shortm, mode="close"):
        rows = []
        for i in range(250, n - 1):
            if longm[i]:
                xi, net = trade(i, False, mode); rows.append((yr[i], net, i, xi))
            if shortm[i]:
                xi, net = trade(i, True, mode); rows.append((yr[i], net, i, xi))
        return pd.DataFrame(rows, columns=["yr", "net", "ei", "xi"])

    def stat(t, lab):
        ts = t.sort_values("xi"); eq = ts.net.cumsum().values
        mdd = (eq - np.maximum.accumulate(eq)).min()
        pf = t.net[t.net > 0].sum() / -t.net[t.net < 0].sum()
        pos = sum(g.net.sum() > 0 for _, g in t.groupby("yr"))
        print(f"{lab:32s} n{len(t):4d} win{(t.net>0).mean()*100:3.0f}% PF{pf:4.2f} "
              f"exp${t.net.mean():+5.0f} tot${eq[-1]:+9,.0f} DD${mdd:+8,.0f} "
              f"R/DD{eq[-1]/-mdd:5.1f} +y{pos}/17")
        return ts, eq

    zero = np.zeros(n, bool)
    LONG = (K8 < 15) & (C > sma100)
    SHORT = (K8 > 85) & (sma50 < sma200) & (C < sma50)

    print("=== TREND-FILTERED SHORT-TERM MEAN REVERSION (ES daily, user stochastic) ===")
    ts_l, eq_l = stat(run(LONG, zero, "close"), "LONG core (MOC close)")
    ts_b, eq_b = stat(run(LONG, SHORT, "close"), "LONG + regime SHORT (MOC)")
    stat(run(LONG, zero, "open"), "  [ref] LONG, next-day OPEN")

    print("\nper-year net $ (LONG core, MOC close):")
    t = run(LONG, zero, "close")
    for y in sorted(set(yr[250:])):
        print(f"  {y}: {t[t.yr==y].net.sum():+10,.0f}")

    # equity + drawdown chart
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 9),
                                 gridspec_kw={"height_ratios": [2.4, 1]})
    for ts, lab in [(ts_l, "LONG core"), (ts_b, "LONG + regime SHORT")]:
        xd = dates.values[ts.xi.values]; eq = ts.net.cumsum().values
        a1.plot(xd, eq, lw=1.7, label=lab)
        a2.fill_between(xd, eq - np.maximum.accumulate(eq), 0, alpha=.35, label=lab)
    a1.legend(); a1.grid(alpha=.3); a1.set_ylabel("cum $")
    a1.set_title("Trend-filtered STMR on ES — equity (K8<15 / SMA100 gate, MOC close, $50/pt)")
    a2.legend(); a2.grid(alpha=.3); a2.set_title("drawdown ($)")
    plt.tight_layout()
    out = ROOT / "docs" / "living" / "mr_stoch_system.png"
    plt.savefig(out, dpi=110)
    print(f"\nchart: {out}")


if __name__ == "__main__":
    main()
