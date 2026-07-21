"""Real-options backtest of the STMR oversold signal, using OptionsDX SPX EOD chains.

Replaces the Black-Scholes ESTIMATE (note 0014 flagged it unreliable) with actual
bid/ask fills. At each oversold ES signal (%K8<15 & Close>SMA100), sell a bull put
spread on SPX: short ~SHORT_DELTA put, long ~LONG_DELTA put (delta-defined so it
scales across SPX 1100->6800), ~TARGET_DTE out. Fill realistically (sell short at
BID, buy long at ASK). Exit on the futures rule's exit date (first Close>SMA5) by
closing at market (buy short@ASK, sell long@BID); if past expiry, settle intrinsic.

Memory-safe: 4.9GB of chains, so we only read the columns we need and keep only the
rows on our ~300 signal entry/exit dates.

  python scripts/mr_options_real.py
  python scripts/mr_options_real.py --short_delta 0.30 --long_delta 0.15 --dte 30
"""
import glob, argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OPTDIR = ROOT / "data" / "optionsdx"
MULT = 100.0          # SPX index option = $100 per point
COMM_RT = 4.0         # ~$1/leg x 4 legs round trip (open 2 + close 2)


def es_signals():
    d = pd.read_csv(ROOT / "data" / "ES_stoch_daily.csv")
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    C = d["Close"].values.astype(float); H = d["High"].values.astype(float); L = d["Low"].values.astype(float)
    n = len(d); dt = pd.to_datetime(d["DateTime"]).dt.date.astype(str).values
    sma5 = pd.Series(C).rolling(5).mean().values; sma100 = pd.Series(C).rolling(100).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K8 = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll)
    out = []
    for i in range(250, n - 1):
        if K8[i] < 15 and C[i] > sma100[i]:
            xi = next((j for j in range(i + 1, min(n, i + 41)) if C[j] > sma5[j]), min(n - 1, i + 40))
            out.append((dt[i], dt[xi]))
    return out


USE = ["[QUOTE_DATE]", " [UNDERLYING_LAST]", " [EXPIRE_DATE]", " [DTE]",
       " [STRIKE]", " [P_BID]", " [P_ASK]", " [P_DELTA]", " [P_IV]"]


def load_needed(dates, dte, pad=14):
    """Read only the rows on `dates` with DTE within target, across all monthly files."""
    files = sorted(glob.glob(str(OPTDIR / "*.txt")) + glob.glob(str(OPTDIR / "*.csv")))
    if not files:
        return None
    keep = []
    for f in files:
        # peek header to map columns robustly
        hdr = pd.read_csv(f, nrows=0)
        cols = {c.strip().strip("[]").upper(): c for c in hdr.columns}
        need = {k: cols.get(k) for k in ["QUOTE_DATE", "UNDERLYING_LAST", "EXPIRE_DATE", "DTE",
                                         "STRIKE", "P_BID", "P_ASK", "P_DELTA", "P_IV"]}
        if any(v is None for v in need.values()):
            continue
        usecols = list(need.values())
        df = pd.read_csv(f, usecols=usecols, skipinitialspace=True)
        df = df.rename(columns={v: k for k, v in need.items()})
        df["QUOTE_DATE"] = df["QUOTE_DATE"].astype(str).str.strip()
        df = df[df["QUOTE_DATE"].isin(dates)]
        if df.empty:
            continue
        for c in ["UNDERLYING_LAST", "DTE", "STRIKE", "P_BID", "P_ASK", "P_DELTA", "P_IV"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["EXPIRE_DATE"] = df["EXPIRE_DATE"].astype(str).str.strip()
        df = df[(df["DTE"] >= dte - pad) & (df["DTE"] <= dte + pad + 4)]
        keep.append(df)
    return pd.concat(keep, ignore_index=True) if keep else pd.DataFrame()


def run(a):
    sigs = es_signals()
    needed = set()
    for e, x in sigs:
        needed.add(e); needed.add(x)
    ch = load_needed(needed, a.dte)
    if ch is None:
        print("No files in data/optionsdx/. Extract the OptionsDX .7z there first."); return
    if ch.empty:
        print("Files loaded but no signal dates overlapped the chains (data is 2010-2023)."); return
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    rows = []
    for edate, xdate in sigs:
        c = by.get(edate)
        if c is None or c.empty:
            continue
        exp = c.iloc[(c["DTE"] - a.dte).abs().argmin()]["EXPIRE_DATE"]
        leg = c[(c["EXPIRE_DATE"] == exp) & c["P_DELTA"].notna() & (c["P_BID"] > 0)]
        if len(leg) < 4:
            continue
        short = leg.iloc[(leg["P_DELTA"].abs() - a.short_delta).abs().argmin()]
        longp = leg.iloc[(leg["P_DELTA"].abs() - a.long_delta).abs().argmin()]
        Ks, Kl = short["STRIKE"], longp["STRIKE"]
        if Kl >= Ks:
            continue
        credit = short["P_BID"] - longp["P_ASK"]           # sell short@bid, buy long@ask
        if credit <= 0:
            continue
        width = Ks - Kl
        cx = by.get(xdate); debit = None
        if cx is not None and xdate <= exp:
            s2 = cx[(cx["EXPIRE_DATE"] == exp) & (cx["STRIKE"] == Ks)]
            l2 = cx[(cx["EXPIRE_DATE"] == exp) & (cx["STRIKE"] == Kl)]
            if not s2.empty and not l2.empty and s2.iloc[0]["P_ASK"] > 0:
                debit = float(s2.iloc[0]["P_ASK"]) - float(l2.iloc[0]["P_BID"])   # buy short@ask, sell long@bid
        if debit is None:
            und = float(short["UNDERLYING_LAST"])          # fallback: intrinsic at entry underlying (approx)
            debit = max(0.0, Ks - und) - max(0.0, Kl - und)
        pnl = (credit - debit) * MULT - COMM * 2
        rows.append((edate, xdate, Ks, Kl, width, credit, debit, pnl, (width - credit) * MULT, short["P_IV"]))
    if not rows:
        print("No fillable spreads built — loosen deltas/DTE."); return
    t = pd.DataFrame(rows, columns=["edate", "xdate", "Ks", "Kl", "width", "credit", "debit", "pnl", "maxloss", "iv"])
    t["yr"] = t.edate.str[:4]
    eq = t.pnl.cumsum().values; mdd = (eq - np.maximum.accumulate(eq)).min()
    pf = t.pnl[t.pnl > 0].sum() / -t.pnl[t.pnl < 0].sum() if (t.pnl < 0).any() else np.inf
    print(f"=== REAL SPX bull put spread — {len(t)} trades, 2010-2023 (short~{a.short_delta:.0%}Δ / long~{a.long_delta:.0%}Δ, ~{a.dte}DTE) ===")
    print(f"  win {(t.pnl>0).mean()*100:.0f}%   PF {pf:.2f}   exp ${t.pnl.mean():+.0f}/trade   total ${eq[-1]:+,.0f}   maxDD ${mdd:+,.0f}")
    print(f"  avg credit ${t.credit.mean()*MULT:.0f}  avg width {t.width.mean():.0f}pt  avg maxloss ${t.maxloss.mean():.0f}  worst ${t.pnl.min():+,.0f}  avg entry IV {t.iv.mean():.1%}")
    print("  per-year net $: " + "  ".join(f"{y}:{g.pnl.sum():+,.0f}" for y, g in t.groupby("yr")))
    t.to_parquet(ROOT / "docs" / "living" / "mr_options_real_trades.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--short_delta", type=float, default=0.30)
    ap.add_argument("--long_delta", type=float, default=0.15)
    ap.add_argument("--dte", type=int, default=30)
    run(ap.parse_args())
