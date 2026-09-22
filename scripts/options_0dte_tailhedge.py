"""options_0dte_tailhedge.py — Cycle 5: does a cheap far-OTM put hedge the crash tail?

Adds a long put at open - K*EM to the open/skip-up-gap/hold-to-expiry IC book, bought
at the open (pay ask = cross-conservative), settled at the close. On normal days it's a
small premium drag; on a crash it pays. Sweep K to see if the tail reduction beats the drag.

Run: .venv/Scripts/python.exe scripts/options_0dte_tailhedge.py
Out: console + data/options_0dte/tailhedge.csv
"""
from __future__ import annotations
import glob
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "databento" / "0dte_parsed"
D = ROOT / "data" / "options_0dte"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"
VIX = ROOT / "data" / "vix_daily_full.csv"
SQRT252 = math.sqrt(252)
COMM_LEG = 1.30
MULT = 100
KS = [2.0, 2.5, 3.0]         # hedge put distance in EM multiples below open


def main():
    spx = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["vix"]
    dd = spx.join(vix, how="inner"); dd["pc"] = dd["Close"].shift(1); dd["pv"] = vix.shift(1)
    ic = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    ic = ic[(ic.anchor == "open") & (ic.strat == "ic") & (ic.gap_pct <= 0.2)].set_index("date")

    hedge_px = {k: {} for k in KS}
    for f in sorted(glob.glob(str(PARSED / "*.parquet"))):
        date = pd.Timestamp(Path(f).stem)
        if date not in ic.index or date not in dd.index:
            continue
        r = dd.loc[date]; op, pc, pv = r["Open"], r["pc"], r["pv"]
        if any(pd.isna(x) for x in (op, pc, pv)):
            continue
        em = pc*(pv/100)/SQRT252
        day = pd.read_parquet(f); day["ts"] = pd.to_datetime(day["ts"], utc=True)
        et = pd.Timestamp(f"{date.date()} 09:30", tz="America/New_York").tz_convert("UTC")
        sub = day[day["ts"] >= et]
        if sub.empty:
            continue
        snapd = day[(day["ts"] == sub["ts"].iloc[0]) & (day["right"] == "P")]
        strikes = sorted(snapd["strike"].unique())
        if not strikes:
            continue
        for k in KS:
            tgt = op - k*em
            ks = min(strikes, key=lambda s: abs(s - tgt))
            row = snapd[snapd["strike"] == ks]
            if not row.empty:
                hedge_px[k][date] = (ks, float(row["ask"].iloc[0]))   # pay ask

    print("=== TAIL HEDGE on the IC book (open, skip up-gaps, hold-to-expiry) ===")
    print("K=EM mult below open |  hedge cost/day | crash days paid | net Sharpe | net maxDD | worst day")
    base = ic["pnl_mid"].to_numpy()
    def sh(x): return round(np.mean(x)/np.std(x)*np.sqrt(252), 2) if np.std(x) else 0
    def mdd(x): c = np.cumsum(x); return (np.maximum.accumulate(c)-c).max()
    print(f"  NO HEDGE            |        -        |       -        |   {sh(base):5} |  ${mdd(base):.0f} | ${base.min():.0f}")
    rows = [{"K": "none", "sharpe": sh(base), "maxdd": round(mdd(base)), "worst": round(base.min()),
             "mean": round(base.mean(), 1)}]
    for k in KS:
        net = []; costs = []; paid = 0
        for date, pnl in ic["pnl_mid"].items():
            if date not in hedge_px[k]:
                net.append(pnl); continue
            ks, ask = hedge_px[k][date]
            cl = dd.loc[date, "Close"]
            payoff = max(ks - cl, 0.0)
            cost = ask + COMM_LEG/MULT
            pl = pnl + (payoff - cost)*MULT
            if payoff > 0:
                paid += 1
            costs.append(cost*MULT); net.append(pl)
        net = np.array(net)
        print(f"  K={k} put ~{np.mean(costs):.0f}c/day   |     ${np.mean(costs):5.0f}      |     {paid:3}        |"
              f"   {sh(net):5} |  ${mdd(net):.0f} | ${net.min():.0f}")
        rows.append({"K": k, "sharpe": sh(net), "maxdd": round(mdd(net)), "worst": round(net.min()),
                     "mean": round(net.mean(), 1), "cost_day": round(np.mean(costs), 0), "days_paid": paid})
    pd.DataFrame(rows).to_csv(D / "tailhedge.csv", index=False)
    print(f"\nsaved {D/'tailhedge.csv'}")
    print("read: if net Sharpe rises / worst-day shrinks without gutting mean, the hedge earns its drag.")


if __name__ == "__main__":
    main()
