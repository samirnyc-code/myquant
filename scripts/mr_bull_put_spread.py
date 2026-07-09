"""Full 2010-2023 backtest of the STMR signal expressed as a BULL PUT SPREAD on SPX.

Signal: %K8<15 & Close>SMA100 (ES daily).  Structure: sell ~SHORT_D put / buy
~LONG_D put, ~DTE days out, real SPX bid/ask fills (slip 0.25).  Exit: on the
futures rule's exit date (first Close>SMA5); if past expiry, settle intrinsic.

Outputs per-trade, per-year table, totals (win% / PF / return-on-collateral),
equity curve + drawdown, saved chart + parquet.
"""
import glob, argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import importlib.util

ROOT = Path(r"c:\Users\Admin\myquant"); OPT = ROOT/"data"/"optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT/"scripts"/"mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)


def fp(b, a, s, slip):
    mid = (b+a)/2; half = (a-b)/2
    return mid - slip*half if s == "sell" else mid + slip*half


def signals(warm=110):
    d = pd.read_csv(ROOT/"data"/"ES_stoch_daily.csv"); d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["date"] = pd.to_datetime(d["DateTime"]).dt.date.astype(str)
    C = d["Close"].values.astype(float); H = d["High"].values.astype(float); L = d["Low"].values.astype(float); n = len(d)
    sma5 = pd.Series(C).rolling(5).mean().values; sma100 = pd.Series(C).rolling(100).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K8 = 100*(C-ll)/np.where(hh-ll == 0, 1, hh-ll)
    out = []
    for i in range(warm, n-1):
        if K8[i] < 15 and C[i] > sma100[i] and "2010" <= d["date"].iloc[i][:4] <= "2023":
            j = next((jj for jj in range(i+1, min(n, i+41)) if C[jj] > sma5[jj]), min(n-1, i+40))
            out.append((d["date"].iloc[i], d["date"].iloc[j]))
    return out


def spx_closes():
    px = {}
    for f in sorted(glob.glob(str(OPT/"*.txt"))):
        df = pd.read_csv(f, skipinitialspace=True, usecols=lambda c: c.strip().strip("[]").upper() in ("QUOTE_DATE", "UNDERLYING_LAST"))
        df.columns = [c.strip().strip("[]").upper() for c in df.columns]
        for dt, g in df.groupby("QUOTE_DATE"):
            px[str(dt).strip()] = float(g["UNDERLYING_LAST"].iloc[0])
    return px


def okrow(r):
    return (not r.empty) and np.isfinite(r.iloc[0].P_BID) and np.isfinite(r.iloc[0].P_ASK) and r.iloc[0].P_ASK > 0


def run(a):
    sig = signals()
    print(f"signals 2010-2023: {len(sig)}   (loading chains, ~1-2 min)...")
    dates = set()
    for e, x in sig:
        dates.update([e, x])
    ch = mm.load(dates, a.dte, sorted(glob.glob(str(OPT/"*.txt"))))
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = spx_closes()
    rows = []
    for e, x in sig:
        en = by.get(e); ex = by.get(x)
        if en is None:
            continue
        exp = en.iloc[(en["DTE"]-a.dte).abs().argmin()]["EXPIRE_DATE"]
        leg = en[(en["EXPIRE_DATE"] == exp) & en["P_DELTA"].notna() & (en["P_BID"] > 0) & (en["P_ASK"] > 0)]
        if len(leg) < 4:
            continue
        sp = leg.iloc[(leg["P_DELTA"].abs()-a.short_d).abs().argmin()]
        lp = leg.iloc[(leg["P_DELTA"].abs()-a.long_d).abs().argmin()]
        if lp["STRIKE"] >= sp["STRIKE"]:
            continue
        credit = fp(sp.P_BID, sp.P_ASK, "sell", a.slip) - fp(lp.P_BID, lp.P_ASK, "buy", a.slip)
        if credit <= 0:
            continue
        if pd.to_datetime(x) > pd.to_datetime(exp):          # held past expiry -> settle intrinsic
            S = px.get(exp)
            if S is None:
                continue
            cost = max(0, sp.STRIKE - S) - max(0, lp.STRIKE - S)
        else:
            undx = float(ex.iloc[0].UNDERLYING_LAST) if ex is not None else float(sp.UNDERLYING_LAST)
            def xv(K, side):
                if ex is None:
                    return None
                r = ex[(ex["EXPIRE_DATE"] == exp) & (ex["STRIKE"] == K)]
                return fp(float(r.iloc[0].P_BID), float(r.iloc[0].P_ASK), side, a.slip) if okrow(r) else None
            xs = xv(sp.STRIKE, "buy"); xl = xv(lp.STRIKE, "sell")
            cost = (xs-xl) if (xs is not None and xl is not None) else (max(0, sp.STRIKE-undx)-max(0, lp.STRIKE-undx))
        if not (np.isfinite(credit) and np.isfinite(cost)):
            continue
        pnl = (credit-cost)*100 - 4
        ml = (sp.STRIKE-lp.STRIKE-credit)*100
        rows.append((e, x, (pd.to_datetime(x)-pd.to_datetime(e)).days, int(sp.STRIKE), int(lp.STRIKE), credit*100, pnl, ml))
    t = pd.DataFrame(rows, columns=["entry", "exit", "days", "Ks", "Kl", "credit", "pnl", "ml"])
    t["yr"] = t.entry.str[:4]; t["roc"] = t.pnl/t.ml
    eq = t.pnl.cumsum().values; mdd = (eq-np.maximum.accumulate(eq)).min()
    pf = t.pnl[t.pnl > 0].sum()/-t.pnl[t.pnl < 0].sum()
    print(f"\n=== BULL PUT SPREAD (short~{a.short_d:.0%}/long~{a.long_d:.0%}, {a.dte}DTE, slip {a.slip}) 2010-2023 ===")
    print(f"trades {len(t)}  win {(t.pnl>0).mean()*100:.0f}%  PF {pf:.2f}  total ${t.pnl.sum():+,.0f}  maxDD ${mdd:+,.0f}")
    print(f"avg P&L ${t.pnl.mean():+.0f}  avg collateral ${t.ml.mean():,.0f}  avg RoC {t.roc.mean()*100:+.1f}%  worst ${t.pnl.min():+,.0f}  avg {t.days.mean():.1f} days")
    print(f"\n{'year':6}{'n':>4}{'win%':>6}{'total$':>10}{'avgRoC':>8}")
    for y, g in t.groupby("yr"):
        print(f"{y:6}{len(g):>4}{(g.pnl>0).mean()*100:>5.0f}%{g.pnl.sum():>+10,.0f}{g.roc.mean()*100:>+7.1f}%")
    # chart
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [2.4, 1]})
    a1.plot(pd.to_datetime(t.exit), eq, lw=1.7, color="tab:green")
    a1.fill_between(pd.to_datetime(t.exit), eq-np.maximum.accumulate(eq), 0, alpha=.15, color="red")
    a1.set_title(f"Bull put spread on STMR signal — cumulative P&L (SPX, 2010-2023, {len(t)} trades)")
    a1.set_ylabel("cum $"); a1.grid(alpha=.3)
    yb = t.groupby("yr").pnl.sum()
    a2.bar(yb.index, yb.values, color=["green" if v > 0 else "red" for v in yb.values])
    a2.axhline(0, color="gray", lw=.8); a2.set_title("net $ by year"); a2.grid(alpha=.3, axis="y")
    plt.tight_layout()
    p = ROOT/"docs"/"living"/"mr_bull_put_spread_fullrun.png"
    plt.savefig(p, dpi=120); print(f"\nchart: {p}")
    t.to_parquet(ROOT/"docs"/"living"/"mr_bull_put_spread_trades.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--short_d", type=float, default=0.30)
    ap.add_argument("--long_d", type=float, default=0.15)
    ap.add_argument("--dte", type=int, default=30)
    ap.add_argument("--slip", type=float, default=0.25)
    run(ap.parse_args())
