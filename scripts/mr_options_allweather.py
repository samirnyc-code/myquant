"""All-weather DEFINED-RISK options book on the STMR signals, real SPX chains.

  LONG side  (bull put spread):  %K8<15 & Close>SMA100 -> sell ~30d put / buy ~15d put; exit Close>SMA5
  SHORT side (bear call spread): %K8>85 & SMA50<SMA200 & Close<SMA50 -> sell ~30d call / buy ~15d call; exit Close<SMA5

Real bid/ask fills (slip 0.25), ~30 DTE, fees in. Reports each side + combined,
per-year, equity/drawdown. Answers "is it only bull put spreads?" -> no, the bear
call spread carries the down-regimes the put spread sits out.
"""
import glob, argparse
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import importlib.util
ROOT = Path(__file__).resolve().parent.parent; OPT = ROOT/"data"/"optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT/"scripts"/"mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)
SLIP, DTE, SD, LD, FEE = 0.25, 30, 0.30, 0.15, 4.0

def fp(b, a, s):
    mid = (b+a)/2; half = (a-b)/2
    return mid - SLIP*half if s == "sell" else mid + SLIP*half

def build_signals():
    d = pd.read_csv(ROOT/"data"/"ES_stoch_daily.csv"); d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["date"] = pd.to_datetime(d["DateTime"]).dt.date.astype(str)
    C = d["Close"].values.astype(float); H = d["High"].values.astype(float); L = d["Low"].values.astype(float); n = len(d)
    s5 = pd.Series(C).rolling(5).mean().values; s50 = pd.Series(C).rolling(50).mean().values
    s100 = pd.Series(C).rolling(100).mean().values; s200 = pd.Series(C).rolling(200).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K8 = 100*(C-ll)/np.where(hh-ll == 0, 1, hh-ll)
    longs, shorts = [], []
    for i in range(200, n-1):
        yr = d["date"].iloc[i][:4]
        if not ("2010" <= yr <= "2023"): continue
        if K8[i] < 15 and C[i] > s100[i]:
            j = next((k for k in range(i+1, min(n, i+41)) if C[k] > s5[k]), min(n-1, i+40))
            longs.append((d["date"].iloc[i], d["date"].iloc[j]))
        if K8[i] > 85 and s50[i] < s200[i] and C[i] < s50[i]:
            j = next((k for k in range(i+1, min(n, i+41)) if C[k] < s5[k]), min(n-1, i+40))
            shorts.append((d["date"].iloc[i], d["date"].iloc[j]))
    return longs, shorts

def okrow(r, opt): return (not r.empty) and np.isfinite(r.iloc[0][opt+"_BID"]) and np.isfinite(r.iloc[0][opt+"_ASK"]) and r.iloc[0][opt+"_ASK"] > 0

def price(sigs, by, opt):
    """opt='P' bull put spread (bullish); opt='C' bear call spread (bearish). Both credit, defined risk."""
    rows = []
    for e, x in sigs:
        en = by.get(e); ex = by.get(x)
        if en is None: continue
        exp = en.iloc[(en["DTE"]-DTE).abs().argmin()]["EXPIRE_DATE"]
        leg = en[(en["EXPIRE_DATE"] == exp) & en[opt+"_DELTA"].notna() & (en[opt+"_BID"] > 0) & (en[opt+"_ASK"] > 0)]
        if len(leg) < 4: continue
        short = leg.iloc[(leg[opt+"_DELTA"].abs()-SD).abs().argmin()]
        long = leg.iloc[(leg[opt+"_DELTA"].abs()-LD).abs().argmin()]
        # put spread: long strike BELOW short; call spread: long strike ABOVE short
        if opt == "P" and long["STRIKE"] >= short["STRIKE"]: continue
        if opt == "C" and long["STRIKE"] <= short["STRIKE"]: continue
        credit = fp(short[opt+"_BID"], short[opt+"_ASK"], "sell") - fp(long[opt+"_BID"], long[opt+"_ASK"], "buy")
        if credit <= 0: continue
        undx = float(ex.iloc[0].UNDERLYING_LAST) if ex is not None else float(short.UNDERLYING_LAST)
        def xv(K, side):
            if ex is None: return None
            r = ex[(ex["EXPIRE_DATE"] == exp) & (ex["STRIKE"] == K)]
            return fp(float(r.iloc[0][opt+"_BID"]), float(r.iloc[0][opt+"_ASK"]), side) if okrow(r, opt) else None
        xs = xv(short.STRIKE, "buy"); xl = xv(long.STRIKE, "sell")
        if xs is not None and xl is not None:
            cost = xs - xl
        else:  # intrinsic settle
            if opt == "P": cost = max(0, short.STRIKE-undx) - max(0, long.STRIKE-undx)
            else: cost = max(0, undx-short.STRIKE) - max(0, undx-long.STRIKE)
        if not (np.isfinite(credit) and np.isfinite(cost)): continue
        width = abs(short.STRIKE-long.STRIKE)
        rows.append((e, x, (credit-cost)*100-FEE, (width-credit)*100))
    return pd.DataFrame(rows, columns=["entry", "exit", "pnl", "ml"])

def stats(t, lab):
    if len(t) == 0: print(f"{lab}: no trades"); return t
    t = t.copy(); t["yr"] = t.entry.str[:4]
    eq = t.sort_values("exit").pnl.cumsum().values; mdd = (eq-np.maximum.accumulate(eq)).min()
    pf = t.pnl[t.pnl > 0].sum()/-t.pnl[t.pnl < 0].sum() if (t.pnl < 0).any() else np.inf
    print(f"{lab:24s} n{len(t):>4} win{(t.pnl>0).mean()*100:>4.0f}% PF{pf:>5.2f} total${t.pnl.sum():>+9,.0f} maxDD${mdd:>+8,.0f} avgRoC{(t.pnl/t.ml).mean()*100:>+5.1f}%")
    return t

def run():
    longs, shorts = build_signals()
    print(f"long signals {len(longs)}, short signals {len(shorts)}; loading chains...")
    dates = set()
    for s in (longs+shorts):
        dates.update(s)
    ch = mm.load(dates, DTE, sorted(glob.glob(str(OPT/"*.txt"))))
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    bp = stats(price(longs, by, "P"), "BULL PUT (long side)")
    bc = stats(price(shorts, by, "C"), "BEAR CALL (short side)")
    comb = pd.concat([bp, bc], ignore_index=True)
    comb = stats(comb, "COMBINED all-weather")
    print("\nper-year combined ($):")
    for y, g in comb.groupby("yr"):
        print(f"  {y}: n{len(g):>3}  ${g.pnl.sum():>+8,.0f}  ({(g.pnl>0).mean()*100:.0f}% win)")
    # chart
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [2.4, 1]})
    for t, lab, c in [(bp, "bull put (long)", "tab:green"), (bc, "bear call (short)", "tab:red"), (comb, "combined", "black")]:
        ts = t.sort_values("exit"); a1.plot(pd.to_datetime(ts.exit), ts.pnl.cumsum().values, lw=1.6, label=lab, color=c)
    a1.legend(); a1.grid(alpha=.3); a1.set_ylabel("cum $"); a1.set_title("All-weather defined-risk options book — SPX 2010-2023")
    yb = comb.groupby("yr").pnl.sum()
    a2.bar(yb.index, yb.values, color=["green" if v > 0 else "red" for v in yb.values]); a2.axhline(0, color="gray", lw=.8)
    a2.set_title("combined net $ by year"); a2.grid(alpha=.3, axis="y")
    plt.tight_layout(); p = ROOT/"docs"/"living"/"mr_options_allweather.png"; plt.savefig(p, dpi=120); print(f"\nchart: {p}")
    comb.to_parquet(ROOT/"docs"/"living"/"mr_options_allweather_trades.parquet")

if __name__ == "__main__":
    run()
