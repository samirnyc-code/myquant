"""options_0dte_gapfilter.py — apply a gap filter to the 0DTE backtest and compare.

The gap analysis showed open-anchored condor/bull-put bleed on UP gaps and profit on
down/flat opens. Here we apply the principled cut gap_pct <= THRESH (skip up-gaps
beyond the sign-change boundary ~+0.2%) and compare filtered vs unfiltered, per
strategy, WITH a year-by-year view (the real robustness check, since the filter is
in-sample). Also sweeps a few thresholds so the result isn't a single cherry-picked cut.

Run: .venv/Scripts/python.exe scripts/options_0dte_gapfilter.py
Out: console + data/options_0dte/gapfilter.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
STRATS = ["ic", "bps", "bcs", "ifly"]


def stats(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return dict(n=0, win=np.nan, mean=np.nan, total=np.nan, sharpe=np.nan, pf=np.nan)
    w = x[x > 0].sum(); l = -x[x < 0].sum()
    return dict(n=len(x), win=round((x > 0).mean() * 100, 1), mean=round(x.mean(), 1),
                total=round(x.sum(), 0), sharpe=round(x.mean() / x.std() * np.sqrt(252), 2) if x.std() else 0,
                pf=round(w / l, 2) if l else np.inf)


def main():
    t = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    t["yr"] = t.date.dt.year
    o = t[t.anchor == "open"].copy()

    print("=== OPEN anchor: UNFILTERED vs gap<=+0.2% (skip up-gaps), MID fill ===\n")
    rows = []
    for s in STRATS:
        base = o[o.strat == s]
        filt = base[base.gap_pct <= 0.2]
        b, f = stats(base.pnl_mid), stats(filt.pnl_mid)
        print(f"{s:5} UNFILT  n={b['n']:4} win={b['win']:5} mean=${b['mean']:7} "
              f"total=${b['total']:8.0f} sharpe={b['sharpe']:5} pf={b['pf']}")
        print(f"{s:5} gap<=.2 n={f['n']:4} win={f['win']:5} mean=${f['mean']:7} "
              f"total=${f['total']:8.0f} sharpe={f['sharpe']:5} pf={f['pf']}\n")
        rows.append({"strat": s, "cut": "unfilt", **b})
        rows.append({"strat": s, "cut": "gap<=0.2", **f})

    print("=== THRESHOLD SWEEP (open anchor, mean $/trade, mid) — not cherry-picked ===")
    thr = [99, 1.0, 0.5, 0.2, 0.0, -0.2]
    hdr = "strat  " + "".join(f"<= {x:>5}" for x in thr)
    print(hdr)
    for s in STRATS:
        base = o[o.strat == s]
        cells = "".join(f"{base[base.gap_pct <= x].pnl_mid.mean():>8.1f}" for x in thr)
        print(f"{s:5} {cells}")

    print("\n=== YEAR-BY-YEAR, gap<=+0.2% filter (mean $/trade, mid) — robustness ===")
    print("strat   2023   2024   2025   2026   |  cross-fill total")
    for s in STRATS:
        f = o[(o.strat == s) & (o.gap_pct <= 0.2)]
        yr = f.groupby("yr").pnl_mid.mean().round(1)
        cells = "".join(f"{yr.get(y, float('nan')):>7.1f}" for y in (2023, 2024, 2025, 2026))
        print(f"{s:5} {cells}   |  ${f.pnl_cross.sum():>8.0f}")

    pd.DataFrame(rows).to_csv(D / "gapfilter.csv", index=False)
    print(f"\nsaved {D/'gapfilter.csv'}")


if __name__ == "__main__":
    main()
