"""R-MULTIPLE vs DOLLAR equity — is the 2021 'explosion' a real regime edge-shift, or just
ES dollar-volatility scaling up? The frozen book's $ equity is flat pre-2021 and steep post,
BUT the stop is 0.30xADR and ADR ~tripled 2010->2024, so identical trade QUALITY pays ~3-4x
more dollars late. Normalizing each trade by its own risk (R = net / stop_$) removes that.

Single data source throughout (Databento 1-min pseudo-ticks) — no NT/massive splice at 2021.

Reads oos_pertrade_20260725.csv (with_trend book, cols net/wide/adr/yr). Plots $-equity vs
R-equity, and reports mean-R + PF by year (scale-free). Output: docs/living/requity_20260725.png
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_20260725.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    d = pd.read_csv(CSV)
    g = d[d.with_trend].sort_values("Date").reset_index(drop=True)
    risk_usd = g.wide.values * 50.0                       # stop distance in $ (1 ES)
    g["R"] = g.net.values / risk_usd                      # each trade normalized by its own risk
    g["pre21"] = g.yr <= 2020

    print("========== $ vs R by ERA (frozen with-trend book) ==========")
    for era, sub in (("PRE-2021", g[g.pre21]), ("2021+", g[~g.pre21]), ("FULL", g)):
        print(f"{era:<9} n={len(sub):5d}  net ${sub.net.sum():+9,.0f}  totalR {sub.R.sum():+7.1f}  "
              f"meanR {sub.R.mean():+.3f}  PF {pf(sub.net):.2f}  medianRisk ${np.median(sub.wide*50):,.0f}")

    print("\n========== per-year: mean-R (scale-free) vs $/trade ==========")
    yt = g.groupby("yr").agg(n=("R", "size"), meanR=("R", "mean"), totalR=("R", "sum"),
                             dpt=("net", "mean"), medADRstop=("wide", "median"))
    yt["stop$"] = yt["medADRstop"] * 50
    print(yt[["n", "meanR", "totalR", "dpt", "stop$"]].round({"meanR": 3, "totalR": 1, "dpt": 1, "stop$": 0}).to_string())

    print("\nKEY: if meanR is ~0 pre-2021 and positive post, the edge really is regime-dependent")
    print("(scale-free). If meanR is steady, the $ explosion was mostly vol-scaling, not edge.")

    # chart: $-equity vs R-equity
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.5), dpi=115)
    noos = int((g.yr <= 2020).sum())
    for a, col, ylab, ttl in ((a1, g.net.cumsum().values, "cumulative $", "DOLLAR equity — flat then 'explodes'"),
                              (a2, g.R.cumsum().values, "cumulative R (risk-normalized)", "R-MULTIPLE equity — the scale-free truth")):
        a.plot(range(len(g)), col, lw=1.7, color="#2a78d6")
        a.axvline(noos, color="#c0392b", ls="--", lw=1.2); a.axhline(0, color="#8b8f96", lw=0.8)
        a.set_ylabel(ylab); a.set_title(ttl, fontweight="bold", fontsize=11)
        a.set_xlabel("trade #  (dashed = 2021 boundary)")
        for s_ in ("top", "right"): a.spines[s_].set_visible(False)
        a.grid(axis="y", color="#eceeed", lw=0.7)
    a1.annotate(f"pre-2021 +${g[g.pre21].net.sum():,.0f}\npost +${g[~g.pre21].net.sum():,.0f}",
                (noos*0.4, g.net.cumsum().max()*0.6), fontsize=9, color="#555")
    a2.annotate(f"pre-2021 {g[g.pre21].R.sum():+.1f}R\npost {g[~g.pre21].R.sum():+.1f}R",
                (noos*0.4, g.R.cumsum().max()*0.6), fontsize=9, color="#555")
    fig.suptitle("Is the 2021 'explosion' a regime edge-shift or just $-vol scaling? "
                 "(same edge pays 3-4x more $ as ES ADR tripled)", fontweight="bold", fontsize=12)
    fig.tight_layout()
    p = WT / "docs" / "living" / "requity_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
