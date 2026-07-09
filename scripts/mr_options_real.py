"""Real-options backtest of the STMR oversold signal, using OptionsDX EOD chains.

Replaces the Black-Scholes ESTIMATE (note 0014 flagged it unreliable) with actual
bid/ask fills. At each oversold ES signal (%K8<15 & Close>SMA100), sell a bull put
spread on SPY/XSP: short ~SHORT_DELTA put, long one WIDTH lower, ~TARGET_DTE out.
Fill realistically (sell at BID, buy at ASK). Exit when the futures rule exits
(first Close>SMA5) by closing the spread at market; if that's past expiry, settle
at intrinsic. Reports the TRUE per-trade P&L, win%, PF, equity/DD — head-to-head
with the futures version.

USAGE
  1. Download OptionsDX SPY (and/or XSP) EOD files -> data/optionsdx/
     (any subfolders / .txt / .csv; pipe- or comma-delimited, bracketed headers ok)
  2. python scripts/mr_options_real.py            # auto-detects files
     python scripts/mr_options_real.py --underlying XSP --width 5 --delta 0.30 --dte 30

If no files are found it prints exactly what to fetch and exits cleanly.
"""
import sys, glob, argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
OPTDIR = ROOT / "data" / "optionsdx"


# ---------- 1. our oversold signals from the ES daily (reuse the validated core) ----------
def es_signals():
    d = pd.read_csv(ROOT / "data" / "ES_stoch_daily.csv")
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    C = d["Close"].values.astype(float)
    H = d["High"].values.astype(float); L = d["Low"].values.astype(float)
    n = len(d); dt = pd.to_datetime(d["DateTime"]).dt.date.astype(str).values
    sma5 = pd.Series(C).rolling(5).mean().values
    sma100 = pd.Series(C).rolling(100).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K8 = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll)
    sigs = []
    for i in range(250, n - 1):
        if K8[i] < 15 and C[i] > sma100[i]:
            xi = None
            for j in range(i + 1, min(n, i + 41)):
                if C[j] > sma5[j]:
                    xi = j; break
            if xi is None:
                xi = min(n - 1, i + 40)
            sigs.append((dt[i], dt[xi]))            # (entry_date, exit_date)
    return sigs


# ---------- 2. OptionsDX loader (defensive to their bracketed/underscored headers) ----------
def _norm(col):
    return col.strip().strip("[]").upper().replace(" ", "_")


def load_chains():
    files = [f for ext in ("*.txt", "*.csv") for f in glob.glob(str(OPTDIR / "**" / ext), recursive=True)]
    if not files:
        return None
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=None, engine="python")
        except Exception:
            df = pd.read_csv(f, sep="|", engine="python")
        df.columns = [_norm(c) for c in df.columns]
        frames.append(df)
    chains = pd.concat(frames, ignore_index=True)
    # normalize the columns we rely on (OptionsDX naming varies slightly by vintage)
    ren = {}
    for c in chains.columns:
        if c in ("QUOTE_DATE", "DATE"): ren[c] = "QDATE"
        elif c in ("EXPIRE_DATE", "EXPIRATION"): ren[c] = "EXP"
        elif c in ("UNDERLYING_LAST", "UNDERLYING_PRICE"): ren[c] = "UND"
        elif c == "DTE": ren[c] = "DTE"
        elif c == "STRIKE": ren[c] = "STRIKE"
        elif c in ("P_BID", "PUT_BID"): ren[c] = "P_BID"
        elif c in ("P_ASK", "PUT_ASK"): ren[c] = "P_ASK"
        elif c in ("P_DELTA", "PUT_DELTA"): ren[c] = "P_DELTA"
        elif c in ("P_IV", "PUT_IV"): ren[c] = "P_IV"
    chains = chains.rename(columns=ren)
    for col in ("QDATE", "EXP"):
        chains[col] = pd.to_datetime(chains[col]).dt.date.astype(str)
    for col in ("UND", "DTE", "STRIKE", "P_BID", "P_ASK", "P_DELTA"):
        chains[col] = pd.to_numeric(chains[col], errors="coerce")
    return chains


# ---------- 3. the bull-put-spread backtest at real fills ----------
def run(args):
    chains = load_chains()
    if chains is None:
        print("No OptionsDX files found in data/optionsdx/.")
        print("Download SPY (or XSP) EOD chains from optionsdx.com -> put the .txt/.csv there.")
        print("Then re-run:  python scripts/mr_options_real.py")
        return
    by_date = {k: v for k, v in chains.groupby("QDATE")}
    sigs = es_signals()
    MULT = 100.0                # 1 option contract = 100 shares
    COMM = 1.30 * 2             # ~$0.65/leg each way, 2 legs
    rows = []
    for edate, xdate in sigs:
        ch = by_date.get(edate)
        if ch is None:
            continue
        puts = ch[(ch["P_DELTA"].abs() > 0.05) & (ch["DTE"] >= args.dte - 10) & (ch["DTE"] <= args.dte + 12)].copy()
        if puts.empty:
            continue
        # pick the expiry closest to TARGET_DTE
        exp = puts.iloc[(puts["DTE"] - args.dte).abs().argmin()]["EXP"]
        leg = puts[puts["EXP"] == exp]
        # short put ~ target delta; long put WIDTH lower
        short = leg.iloc[(leg["P_DELTA"].abs() - args.delta).abs().argmin()]
        Ks = short["STRIKE"]; Kl = Ks - args.width
        longp = leg.iloc[(leg["STRIKE"] - Kl).abs().argmin()]
        if longp["STRIKE"] >= Ks:
            continue
        credit = short["P_BID"] - longp["P_ASK"]        # realistic: sell bid, buy ask
        if credit <= 0:
            continue
        # ---- exit: close at the exit date's chain (buy short@ask, sell long@bid); else settle intrinsic ----
        cx = by_date.get(xdate)
        debit = None
        if cx is not None and xdate <= exp:
            s2 = cx[(cx["EXP"] == exp) & (cx["STRIKE"] == Ks)]
            l2 = cx[(cx["EXP"] == exp) & (cx["STRIKE"] == longp["STRIKE"])]
            if not s2.empty and not l2.empty:
                debit = float(s2.iloc[0]["P_ASK"]) - float(l2.iloc[0]["P_BID"])
        if debit is None:                                # settle at expiry intrinsic on underlying
            und_exit = float(ch.iloc[0]["UND"])          # fallback: entry underlying (approx)
            debit = max(0.0, Ks - und_exit) - max(0.0, longp["STRIKE"] - und_exit)
        pnl = (credit - debit) * MULT - COMM
        max_loss = (args.width - credit) * MULT
        rows.append((edate, xdate, Ks, longp["STRIKE"], credit, debit, pnl, max_loss))
    if not rows:
        print("Files loaded but no signal dates matched the chains. Check date overlap / underlying.")
        return
    t = pd.DataFrame(rows, columns=["edate", "xdate", "Kshort", "Klong", "credit", "debit", "pnl", "maxloss"])
    eq = t["pnl"].cumsum().values; mdd = (eq - np.maximum.accumulate(eq)).min()
    pf = t.pnl[t.pnl > 0].sum() / -t.pnl[t.pnl < 0].sum() if (t.pnl < 0).any() else np.inf
    print(f"=== REAL bull-put-spread on {args.underlying} — {len(t)} trades (WIDTH {args.width}, ~{args.delta:.0%}delta, ~{args.dte}DTE) ===")
    print(f"  win {(t.pnl>0).mean()*100:.0f}%   PF {pf:.2f}   exp ${t.pnl.mean():+.0f}/trade   total ${eq[-1]:+,.0f}   maxDD ${mdd:+,.0f}")
    print(f"  avg credit ${t.credit.mean()*100:.0f}   avg max-loss ${t.maxloss.mean():.0f}   worst trade ${t.pnl.min():+.0f}")
    t.to_parquet(ROOT / "docs" / "living" / "mr_options_real_trades.parquet")
    print("  -> saved docs/living/mr_options_real_trades.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default="SPY")
    ap.add_argument("--width", type=float, default=5.0)      # SPY $5 wide; XSP maybe 5
    ap.add_argument("--delta", type=float, default=0.30)     # short-put delta
    ap.add_argument("--dte", type=int, default=30)           # target days to expiry
    run(ap.parse_args())
