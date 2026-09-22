"""options_0dte_monthly.py — monthly equity / drawdown / income for the 0DTE IC.

Strategy: open-anchored iron condor, skip up-gaps > +0.2%, 1 contract.
Produces monthly P&L, cumulative equity + underwater drawdown (mid AND worst-case
cross fills), ROI on the sized account, and a monthly-income distribution.

Run: .venv/Scripts/python.exe scripts/options_0dte_monthly.py
Out: data/options_0dte/monthly_equity_dd.png + console
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
ACCOUNT = 20000        # sized earlier: margin ~2.3k + 2x maxDD ~8.7k


def main():
    t = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    f = t[(t.anchor == "open") & (t.strat == "ic") & (t.gap_pct <= 0.2)].copy()
    f = f.sort_values("date").set_index("date")

    m_mid = f["pnl_mid"].resample("ME").sum()
    m_cross = f["pnl_cross"].resample("ME").sum()
    n_months = len(m_mid)
    years = (f.index.max() - f.index.min()).days / 365.25

    # ---- monthly income stats ----
    print(f"OPEN IC, skip up-gaps, 1 contract  |  {f.index.min().date()} -> {f.index.max().date()}"
          f"  ({n_months} months, {len(f)} trades)\n")
    for lbl, s in [("MID fill", m_mid), ("CROSS (worst)", m_cross)]:
        tot = s.sum(); avg = s.mean(); pos = (s > 0).mean() * 100
        ann = avg * 12
        print(f"{lbl:13}: total ${tot:,.0f}  avg/mo ${avg:,.0f}  best ${s.max():,.0f}  "
              f"worst ${s.min():,.0f}  %+mo {pos:.0f}%")
        print(f"{'':13}  annualized ${ann:,.0f}/yr  ->  ROI on ${ACCOUNT:,} = {ann/ACCOUNT*100:.1f}%/yr\n")

    # ---- per-year ----
    print("per calendar year (MID):")
    yr = f["pnl_mid"].groupby(f.index.year).agg(["sum", "count"])
    for y, r in yr.iterrows():
        print(f"  {y}: ${r['sum']:,.0f}  ({int(r['count'])} trades)")

    # ---- equity + drawdown curves (monthly) ----
    eq_mid = m_mid.cumsum(); eq_cross = m_cross.cumsum()
    dd_mid = eq_mid - eq_mid.cummax()
    dd_cross = eq_cross - eq_cross.cummax()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1], sharex=True)
    ax1.plot(eq_mid.index, eq_mid.values, color="#1f77b4", lw=2, label="mid fill")
    ax1.plot(eq_cross.index, eq_cross.values, color="#7f7f7f", lw=1.6, ls="--", label="cross (worst-case)")
    ax1.axhline(0, color="#bbb", lw=0.6)
    ax1.set_ylabel("cumulative P&L ($/contract)"); ax1.legend(); ax1.grid(alpha=0.25)
    ax1.set_title("0DTE open-anchored iron condor (skip up-gaps) — monthly equity, 1 contract")
    ax2.fill_between(dd_mid.index, dd_mid.values, 0, color="#1f77b4", alpha=0.4, label="mid")
    ax2.fill_between(dd_cross.index, dd_cross.values, 0, color="#7f7f7f", alpha=0.3, label="cross")
    ax2.set_ylabel("drawdown ($)"); ax2.grid(alpha=0.25); ax2.legend()
    fig.tight_layout()
    png = D / "monthly_equity_dd.png"
    fig.savefig(png, dpi=115); plt.close(fig)
    print(f"\nmonthly maxDD: mid ${-dd_mid.min():,.0f}  cross ${-dd_cross.min():,.0f}")
    print(f"saved {png}")


if __name__ == "__main__":
    main()
