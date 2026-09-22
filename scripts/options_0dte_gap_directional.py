"""options_0dte_gap_directional.py — Cycle 6: is the gap a DIRECTIONAL signal?

The gap analysis showed premium-selling profits after down/flat opens and bleeds after
up-gaps. That implies a directional move: does an open gap predict the intraday
(open->close) return? Tested on the FULL SPX cash history 1990-2026 (~9200 days) — 36
years across every regime — NOT just the 3-year 0DTE era. This is the one angle here
with real out-of-sample history.

Strategies on the underlying (open->close, 1 SPX unit):
  MR  (mean-revert): position = -sign(gap)   (down-gap -> long, up-gap -> short)
  MOM (momentum):    position = +sign(gap)
Conditioned on |gap| thresholds. Reports by decade + hit rate + Sharpe.

Run: .venv/Scripts/python.exe scripts/options_0dte_gap_directional.py
Out: console + data/options_0dte/gap_directional.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"


def sh(x):
    x = np.asarray(x, float)
    return round(x.mean() / x.std() * np.sqrt(252), 2) if len(x) > 1 and x.std() else 0


def main():
    d = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    d["pc"] = d["Close"].shift(1)
    d = d.dropna()
    d["gap"] = (d["Open"] - d["pc"]) / d["pc"] * 100          # overnight gap %
    d["intra"] = (d["Close"] - d["Open"]) / d["Open"] * 100    # open->close %
    d["decade"] = (d.index.year // 5 * 5)

    print(f"SPX 1990-2026: {len(d)} sessions\n")
    print("=== gap -> intraday(open->close) correlation (neg = mean-reversion) ===")
    print(f"  overall corr: {d['gap'].corr(d['intra']):.3f}")
    for dec, g in d.groupby("decade"):
        print(f"  {int(dec)}s: corr {g['gap'].corr(g['intra']):+.3f}  (n={len(g)})")

    print("\n=== MEAN-REVERSION strategy: position = -sign(gap), pnl = -sign(gap)*intra (in %) ===")
    print(f"{'filter':16}{'n':>6}{'mean%':>8}{'hit%':>7}{'Sharpe':>8}{'ann%':>8}")
    rows = []
    for name, mask in [("all days", d.gap.abs() >= 0),
                       ("|gap|>0.15%", d.gap.abs() > 0.15),
                       ("|gap|>0.3%", d.gap.abs() > 0.3),
                       ("|gap|>0.5%", d.gap.abs() > 0.5),
                       ("down-gaps only", d.gap < -0.15),
                       ("up-gaps only", d.gap > 0.15)]:
        g = d[mask]
        pos = -np.sign(g["gap"])
        pnl = pos * g["intra"]
        rows.append({"filter": name, "n": len(g), "mean_pct": round(pnl.mean(), 4),
                     "hit_pct": round((pnl > 0).mean()*100, 1), "sharpe": sh(pnl),
                     "ann_pct": round(pnl.mean()*252, 1)})
        print(f"{name:16}{len(g):>6}{pnl.mean():>8.3f}{(pnl>0).mean()*100:>7.1f}{sh(pnl):>8}{pnl.mean()*252:>8.1f}")

    print("\n=== MR (|gap|>0.3%) by decade — robustness across 36 years ===")
    g = d[d.gap.abs() > 0.3]
    pos = -np.sign(g["gap"]); pnl = pos * g["intra"]
    tmp = pd.DataFrame({"decade": g["decade"], "pnl": pnl})
    for dec, gg in tmp.groupby("decade"):
        print(f"  {int(dec)}s: n={len(gg):4} mean {gg.pnl.mean():+.3f}%  hit {(gg.pnl>0).mean()*100:.0f}%  Sharpe {sh(gg.pnl)}")

    print("\n=== DOWN-gap vs UP-gap asymmetry (mean intraday move, %) ===")
    for name, mask in [("down-gap <-0.3%", d.gap < -0.3), ("up-gap >+0.3%", d.gap > 0.3)]:
        g = d[mask]
        print(f"  {name}: n={len(g):4} mean intra {g['intra'].mean():+.3f}%  "
              f"P(up)={{(g['intra']>0).mean()*100:.0f}}%  median {g['intra'].median():+.3f}%")

    pd.DataFrame(rows).to_csv(D / "gap_directional.csv", index=False)
    print(f"\nsaved {D/'gap_directional.csv'}")


if __name__ == "__main__":
    main()
