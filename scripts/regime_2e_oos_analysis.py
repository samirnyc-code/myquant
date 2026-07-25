"""OOS DEEP-DIVE ANALYSIS — consumes oos_pertrade_20260725.csv (every filled 2E entry
2010-2026 with regime/ADR/VIX). Answers: is the pre-2021 null a DEAD edge or a
VOLATILITY-CONDITIONAL edge, and does any vol threshold generalize across eras (=not overfit)?

Cuts:
  1. Gated (with-trend) book: PF/net by ERA (pre-2021 / 2021+) and by YEAR.
  2. Long vs short split by era.
  3. Vol conditioning: PF of the gated book by ADR bucket x era, and by VIX bucket x era.
  4. Cross-era generalization (the honest test): derive a vol threshold on ONE era,
     apply to the OTHER era out-of-sample. If a threshold fit on 2021+ also profits pre-2021
     (and vice versa), the edge is conditional-but-real, not overfit.
  5. Counter-trend book (is the gate the thing failing?).

  python scripts/regime_2e_oos_analysis.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_20260725.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def line(name, s):
    s = np.asarray(s, float)
    if not len(s):
        return f"{name:<22} (empty)"
    return (f"{name:<22} n={len(s):5d}  net {s.sum():+9,.0f}  $/tr {s.mean():+6.1f}  "
            f"PF {pf(s):4.2f}  win {100*(s>0).mean():4.1f}%")


def main():
    df = pd.read_csv(CSV)
    df["pre21"] = df.yr <= 2020
    g = df[df.with_trend].copy()      # the frozen gated book
    ct = df[~df.with_trend].copy()    # counter-trend

    print("========== 1. GATED (with-trend) BOOK by ERA ==========")
    print(line("PRE-2021 (2010-20)", g[g.pre21].net))
    print(line("2021+     (2021-26)", g[~g.pre21].net))
    print(line("FULL", g.net))

    print("\n========== 2. LONG vs SHORT by era ==========")
    for era, sub in (("PRE-2021", g[g.pre21]), ("2021+", g[~g.pre21])):
        print(f"-- {era} --")
        print(line("  long (2EL)", sub[sub.dir == "L"].net))
        print(line("  short (2ES)", sub[sub.dir == "S"].net))

    print("\n========== 3a. GATED BOOK by ADR bucket x era ==========")
    # global ADR bucket edges (so buckets mean the same across eras)
    qs = g.net  # placeholder
    edges = np.quantile(g.adr, [0, .2, .4, .6, .8, 1.0])
    lab = [f"ADR[{edges[i]:.0f}-{edges[i+1]:.0f}]" for i in range(5)]
    g["adrb"] = pd.cut(g.adr, bins=np.unique(edges), labels=False, include_lowest=True)
    print(f"{'bucket':<16}{'PRE-2021 (n/PF/net)':<28}{'2021+ (n/PF/net)':<28}")
    for i in range(len(lab)):
        pre = g[(g.adrb == i) & g.pre21].net; pos = g[(g.adrb == i) & ~g.pre21].net
        print(f"{lab[i]:<16}"
              f"{f'{len(pre)}/{pf(pre)}/{pre.sum():+,.0f}':<28}"
              f"{f'{len(pos)}/{pf(pos)}/{pos.sum():+,.0f}':<28}")

    print("\n========== 3b. GATED BOOK by VIX bucket x era ==========")
    gv = g[g.vix_prev.notna()].copy()
    vedges = np.quantile(gv.vix_prev, [0, .2, .4, .6, .8, 1.0])
    vlab = [f"VIX[{vedges[i]:.0f}-{vedges[i+1]:.0f}]" for i in range(5)]
    gv["vb"] = pd.cut(gv.vix_prev, bins=np.unique(vedges), labels=False, include_lowest=True)
    print(f"{'bucket':<16}{'PRE-2021 (n/PF/net)':<28}{'2021+ (n/PF/net)':<28}")
    for i in range(len(vlab)):
        pre = gv[(gv.vb == i) & gv.pre21].net; pos = gv[(gv.vb == i) & ~gv.pre21].net
        print(f"{vlab[i]:<16}"
              f"{f'{len(pre)}/{pf(pre)}/{pre.sum():+,.0f}':<28}"
              f"{f'{len(pos)}/{pf(pos)}/{pos.sum():+,.0f}':<28}")

    print("\n========== 4. CROSS-ERA THRESHOLD GENERALIZATION (the honest test) ==========")
    # derive ADR threshold on 2021+ (its 25th pctile of traded ADR), apply to pre-2021 OOS
    T_post = np.quantile(g[~g.pre21].adr, 0.25)
    T_pre = np.quantile(g[g.pre21].adr, 0.75)
    print(f"threshold A: ADR >= {T_post:.1f} (=25th pctile of 2021+ ADR)")
    print(line("   pre-2021 with ADR>=T_post", g[g.pre21 & (g.adr >= T_post)].net))
    print(line("   2021+    with ADR>=T_post", g[~g.pre21 & (g.adr >= T_post)].net))
    print(f"threshold B: ADR >= {T_pre:.1f} (=75th pctile of PRE-2021 ADR, fit on pre only)")
    print(line("   pre-2021 with ADR>=T_pre", g[g.pre21 & (g.adr >= T_pre)].net))
    print(line("   2021+    with ADR>=T_pre", g[~g.pre21 & (g.adr >= T_pre)].net))
    for vt in (18, 20, 22, 25, 30):
        sub = g[g.pre21 & (g.vix_prev >= vt)].net
        print(line(f"   pre-2021 VIX>={vt}", sub))

    print("\n========== 5. COUNTER-TREND book by era (is the gate failing?) ==========")
    print(line("PRE-2021 counter-trend", ct[ct.pre21].net))
    print(line("2021+     counter-trend", ct[~ct.pre21].net))

    print("\n========== 6. WALK-FORWARD annual PF (gated book) ==========")
    yt = g.groupby("yr").agg(n=("net", "size"), net=("net", "sum"), PF=("net", pf))
    print(yt.round({"net": 0}).to_string())


if __name__ == "__main__":
    main()
