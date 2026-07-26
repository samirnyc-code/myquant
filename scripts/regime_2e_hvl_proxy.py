"""GAMMA-REGIME PROXY — replace the HVL gate with price/vol/location features we already have
(no options data). The 2E trades are labeled above/below HVL; find what the above-HVL (winning-
regime) trades have in common, and whether a non-gamma feature reproduces the HVL gate's edge.

Two questions:
  1. Which features SEPARATE above-HVL vs below-HVL trades? (what IS the positive-gamma regime,
     in price terms)
  2. Does gating the 2E book on that feature reproduce the above-HVL edge (PF ~1.6-1.9)?

Features (all causal, panama frame = same as entry_px): trend (px vs SMA10/20/50, slope, multi-
day returns), vol (ADR, VIX, realized vol), location (px vs prior close/high/low, position in
prior-day range, distance from N-day high), efficiency (ER10), time.

Reads hvl_2e_realtick_20260725.csv (2E trades: entry_px, net, above) + _continuous.parquet + VIX.

  python scripts/regime_2e_hvl_proxy.py
Output: data/regime/hvl_proxy_features_20260725.csv + rankings.
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    d = pd.read_csv(WT / "data" / "regime" / "hvl_2e_realtick_20260725.csv").dropna(subset=["prior_hvl_es"])
    # daily features (panama, causal via shift)
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    g = b.groupby("Date").agg(O=("Open", "first"), H=("High", "max"), L=("Low", "min"), C=("Close", "last")).reset_index().sort_values("Date")
    c = g["C"]
    for w in (10, 20, 50):
        g[f"sma{w}"] = c.rolling(w).mean()
    g["slope20"] = g["sma20"] - g["sma20"].shift(5)
    for k in (1, 5, 10, 20):
        g[f"ret{k}"] = c.pct_change(k)
    g["adr10"] = (g.H - g.L).rolling(10).mean()
    chg = c.diff().abs(); g["er10"] = (c - c.shift(10)).abs() / chg.rolling(10).sum()
    g["rvol10"] = c.pct_change().rolling(10).std()
    g["hi20"] = g.H.rolling(20).max(); g["lo20"] = g.L.rolling(20).min()
    feat = ["O", "H", "L", "C", "sma10", "sma20", "sma50", "slope20", "ret1", "ret5", "ret10", "ret20",
            "adr10", "er10", "rvol10", "hi20", "lo20"]
    for f in feat:
        g[f] = g[f].shift(1)                 # causal: prior day's values
    g = g.rename(columns={"O": "pO", "H": "pH", "L": "pL", "C": "pC"})
    d = d.merge(g[["Date"] + ["pO", "pH", "pL", "pC", "sma10", "sma20", "sma50", "slope20",
                              "ret1", "ret5", "ret10", "ret20", "adr10", "er10", "rvol10", "hi20", "lo20"]],
                on="Date", how="left")
    vix = pd.read_csv(DATA / "vix_daily.csv"); vix["date"] = vix["date"].astype(str)
    vix["vix_prev"] = vix["close"].shift(1)
    d = d.merge(vix[["date", "vix_prev"]].rename(columns={"date": "Date"}), on="Date", how="left")

    # trade-location features (entry_px vs prior levels, same panama frame)
    e = d.entry_px
    d["px_vs_pC"] = e - d.pC
    d["px_vs_sma20"] = e - d.sma20
    d["px_vs_sma50"] = e - d.sma50
    d["px_vs_pH"] = e - d.pH
    d["px_vs_pL"] = e - d.pL
    d["pos_prangeD"] = (e - d.pL) / (d.pH - d.pL)          # position in prior-day range (0=low,1=high)
    d["dist_hi20"] = (d.hi20 - e) / d.adr10                # how far below 20d high (in ADR)
    d["above_sma20"] = (e > d.sma20).astype(int)
    d["above_sma50"] = (e > d.sma50).astype(int)
    d.to_csv(WT / "data" / "regime" / "hvl_proxy_features_20260725.csv", index=False)

    cand = ["px_vs_pC", "px_vs_sma20", "px_vs_sma50", "px_vs_pH", "px_vs_pL", "pos_prangeD",
            "dist_hi20", "ret1", "ret5", "ret10", "ret20", "slope20", "er10", "adr10", "rvol10", "vix_prev"]
    ab = d[d.above]; be = d[~d.above]
    print("=== 1) what distinguishes ABOVE-HVL from BELOW-HVL trades? (feature medians) ===")
    print(f"{'feature':<14}{'above-HVL':>12}{'below-HVL':>12}{'corr w/above':>14}")
    corrs = {}
    for f in cand:
        av, bv = ab[f].median(), be[f].median()
        cc = d[f].corr(d.above.astype(float))
        corrs[f] = cc
        print(f"{f:<14}{av:>12.2f}{bv:>12.2f}{cc:>14.3f}")

    print("\n=== 2) each feature as a GATE — does it reproduce the above-HVL edge? ===")
    print(f"  (baseline: 2E above-HVL PF {pf(ab.net):.2f} +${ab.net.sum():,.0f} n={len(ab)} | below-HVL PF {pf(be.net):.2f})")
    print(f"{'gate rule':<26}{'n':>5}{'PF':>6}{'net':>9}{'win%':>6}{'overlap w/above-HVL':>20}")
    # test top-correlated features as gates (split at median, direction by corr sign)
    for f in sorted(cand, key=lambda x: -abs(corrs[x]))[:10]:
        thr = d[f].median()
        gate = (d[f] >= thr) if corrs[f] > 0 else (d[f] <= thr)
        gd = d[gate]
        overlap = 100 * (gate & d.above).sum() / max(gate.sum(), 1)
        print(f"{f + (' >=' if corrs[f]>0 else ' <=') + 'med':<26}{len(gd):>5}{pf(gd.net):>6.2f}{gd.net.sum():>+9,.0f}{100*(gd.net>0).mean():>6.0f}{overlap:>19.0f}%")


if __name__ == "__main__":
    main()
