"""RECONCILE THE CONTRADICTION — 'we didn't curve-fit' vs 'edge collapses pre-2021'.
Two candidate ARTIFACTS that would fake a pre-2021 collapse, tested directly:

  A. FIXED-COST bias: $5 RT + $12.5 slip is fixed $; in low-vol (pre-2021, ADR~14) that eats a
     huge fraction of the gross move, in high-vol (2022, ADR~70) it's trivial. Compare GROSS
     (zero cost) vs NET edge in scale-free R, by era. If gross R is similar pre/post, the
     'collapse' is COSTS, not edge.

  B. PROXY VOL-BIAS: the 1-min pseudo-tick reconstruction was validated ONLY on 2021-26
     (all high-vol). The 6t retest + 0.30xADR stop are a big fraction of a low-vol bar, where a
     4-pts-per-minute path misprices worst. Compare REAL-tick vs PROXY on 2021-26 BY ADR BUCKET.
     If the real-vs-proxy PF gap BLOWS UP in the low-ADR bucket, the pre-2021 (all low-ADR)
     proxy result is downward-biased and can't be trusted.

Reads oos_pertrade_20260725.csv (proxy frozen book, mae/eod/adr) + durable_realtick_20260725.csv
(FROZEN spec = real ticks 2021-26) + _continuous.parquet (daily ADR).

  python scripts/regime_2e_reconcile.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def daily_adr():
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    d = b.groupby("Date").agg(dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date")
    d["adr10"] = (d.dH - d.dL).rolling(10).mean().shift(1)
    return d.set_index("Date")["adr10"]


def main():
    g = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_20260725.csv")
    g = g[g.with_trend].copy().reset_index(drop=True); g["pre21"] = g.yr <= 2020
    g["S"] = np.maximum(np.round(0.30 * g.adr.values / TICK) * TICK, FLOOR)
    S = g["S"].values
    move = np.where(g.mae_pts.values >= S, -S, g.eod_move.values)     # points
    g["gross"] = move * PT                                            # zero cost
    g["net"] = g.gross - 5.0 - 12.5
    g["Rg"] = g.gross / (S * PT)                                      # gross R (scale-free)
    g["Rn"] = g.net / (S * PT)                                        # net R

    print("========== A. GROSS vs NET edge in R, by era (is the collapse just COSTS?) ==========")
    print(f"{'era':<10}{'n':>5}{'grossR':>8}{'meanRg':>8}{'netR':>8}{'meanRn':>8}{'grossPF':>8}{'netPF':>7}{'medStop$':>9}")
    for era, sub in (("PRE-2021", g[g.pre21]), ("2021+", g[~g.pre21])):
        print(f"{era:<10}{len(sub):>5}{sub.Rg.sum():>+8.1f}{sub.Rg.mean():>+8.3f}"
              f"{sub.Rn.sum():>+8.1f}{sub.Rn.mean():>+8.3f}{pf(sub.gross):>8.2f}{pf(sub.net):>7.2f}"
              f"{np.median(sub.S) * PT:>9,.0f}")
    print("  -> if GROSS meanR is ~equal pre/post but NET collapses, the pre-2021 'collapse' is COSTS.")
    print(f"  cost as % of gross win: pre-2021 {17.5/g[g.pre21].gross[g[g.pre21].gross>0].mean()*100:.1f}%  "
          f"2021+ {17.5/g[~g.pre21].gross[g[~g.pre21].gross>0].mean()*100:.1f}%")

    print("\n========== B. REAL-tick vs PROXY on 2021-26, BY ADR bucket (proxy vol-bias?) ==========")
    adr = daily_adr()
    rt = pd.read_csv(WT / "data" / "regime" / "durable_realtick_20260725.csv")
    rt = rt[rt.spec == "FROZEN"].copy(); rt["adr"] = rt.Date.map(adr)
    px = g[~g.pre21].copy()   # proxy frozen book 2021+
    edges = [0, 25, 35, 50, 300]
    labs = [f"ADR {edges[i]}-{edges[i+1]}" for i in range(len(edges) - 1)]
    rt["b"] = pd.cut(rt.adr, edges, labels=False); px["b"] = pd.cut(px.adr, edges, labels=False)
    print(f"{'bucket':<12}{'REAL n/PF/$tr':<24}{'PROXY n/PF/$tr':<24}{'PF gap':>8}")
    for i, lab in enumerate(labs):
        r = rt[rt.b == i].net; p = px[px.b == i].net
        gap = pf(r) - pf(p) if len(r) and len(p) else float('nan')
        print(f"{lab:<12}"
              f"{f'{len(r)}/{pf(r)}/{r.mean():+.0f}' if len(r) else '-':<24}"
              f"{f'{len(p)}/{pf(p)}/{p.mean():+.0f}' if len(p) else '-':<24}"
              f"{gap:>+8.2f}")
    print("  -> if the PF gap (REAL - PROXY) BLOWS UP in the low-ADR bucket, the proxy under-reports")
    print("     the edge in low vol -> the pre-2021 (all low-ADR) proxy collapse is an ARTIFACT.")
    print("  -> if the gap is ~flat across ADR, the proxy is unbiased and the collapse is REAL.")


if __name__ == "__main__":
    main()
