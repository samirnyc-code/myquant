"""options_0dte_regime_diag.py — WHY does the 0DTE IC P&L accelerate in 2025-26?

Breaks the open-anchored iron condor down by year to see what actually changed:
credit collected, EM width, VIX, win rate, loss frequency/size, trade count, and
strike-density / spread-width (data-quality) proxies. Distinguishes a real edge from
a favorable-regime tailwind or an early-data artifact.

Run: .venv/Scripts/python.exe scripts/options_0dte_regime_diag.py
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"


def main():
    t = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    ic = t[(t.anchor == "open") & (t.strat == "ic")].copy()
    ic["yr"] = ic.date.dt.year
    ic["spot"] = ic["open"]
    ic["em_pct"] = ic["em"] / ic["open"] * 100
    ic["realized_pct"] = (ic["close"] - ic["open"]).abs() / ic["open"] * 100
    ic["loss"] = ic["pnl_mid"] < 0
    ic["maxloss"] = ic["pnl_mid"] < -2000

    print("OPEN iron condor by year (unfiltered):\n")
    g = ic.groupby("yr").agg(
        n=("pnl_mid", "size"),
        win_pct=("pnl_mid", lambda x: round((x > 0).mean() * 100, 1)),
        credit=("credit_mid", lambda x: round(x.mean() * 100, 0)),
        mean_pnl=("pnl_mid", lambda x: round(x.mean(), 1)),
        vix=("vix_prior", lambda x: round(x.mean(), 1)),
        spot=("spot", lambda x: round(x.mean(), 0)),
        em_pts=("em", lambda x: round(x.mean(), 1)),
        em_pct=("em_pct", lambda x: round(x.mean(), 2)),
        realized_pct=("realized_pct", lambda x: round(x.mean(), 2)),
        loss_freq=("loss", lambda x: round(x.mean() * 100, 1)),
        avg_loss=("pnl_mid", lambda x: round(x[x < 0].mean(), 0)),
        maxloss_n=("maxloss", "sum"),
    )
    print(g.to_string())

    print("\nKEY RATIOS by year:")
    for y, r in g.iterrows():
        # credit collected vs EM width; realized vs implied (EM); loss drag
        rv_iv = r["realized_pct"] / r["em_pct"]
        print(f"  {y}: credit ${r['credit']:.0f}/contract  |  realized/EM = {rv_iv:.2f} "
              f"(<1 = market stayed inside band)  |  maxloss days {int(r['maxloss_n'])}/{int(r['n'])}"
              f" ({r['maxloss_n']/r['n']*100:.0f}%)")

    print("\nINTERPRETATION GUIDE:")
    print("  - credit rising  -> fatter premium (VIX / 0DTE demand); regime tailwind")
    print("  - realized/EM falling -> market stayed inside band more; calmer -> premium-seller heaven")
    print("  - maxloss% falling -> fewer blowups; the real driver of premium-selling P&L")
    print("  - n rising -> more 0DTE expiries listed (structural, more shots)")


if __name__ == "__main__":
    main()
