"""CAUSAL, executable STMR bull-put-spread backtest — the honest version (S70).

Fixes the look-ahead that earlier options backtests hid:
  * signal is read at 15:59 ET (the OPEN of the 14:59-CT 1-minute bar), STRICTLY
    before the 16:00 option fill — not the 16:15 daily close.
  * 1-minute bars are OPEN-stamped; the daily file is CLOSE-stamped (16:15 ET).
    Mixing them naively is the S31 landmine — handled explicitly here.
  * fill = OptionsDX 16:00 marks, BID/ASK (sell bid / buy ask), realistic per-contract fees.

KNOWN, DISCLOSED LIMITS (do not present the number without these):
  * fill-drift: real fill lands in the 16:00-16:15 window, not exactly at the 16:00 mark.
    Unmeasurable on EOD data — quantify via the OPRA forward-test or ThetaData.
  * 1-minute ES only exists from 2021-06, so the causal signal is buildable ONLY on
    2021-07 .. 2023-12 (OptionsDX ends 2023). ~29 trades. Too small to conclude an edge;
    and that window was a benign regime for premium-selling (PF here > full-sample).
  * ~13% of STMR signals are timing-sensitive (flip between 15:59 and the 16:15 close),
    so this trade set differs from the daily-close backtest — they are NOT the same thing.

Run: PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/mr_bps_causal_1559.py
"""
import glob, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent; OPT = ROOT/"data"/"optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT/"scripts"/"mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)
SLIP, FEE, DTE, WIDTH, SHORT_D = 1.0, 1.30, 14, 50, 0.30   # SLIP=1.0 => bid/ask


def fp(b, a, s):
    mid = (b+a)/2; half = (a-b)/2
    return mid - SLIP*half if s == "sell" else mid + SLIP*half


def okp(r):
    return (not r.empty) and np.isfinite(r.iloc[0].P_BID) and np.isfinite(r.iloc[0].P_ASK) and r.iloc[0].P_ASK > 0


def causal_signals():
    """STMR entries/exits read at 15:59 ET (open of the 14:59-CT bar), 2021-07..2023-12."""
    d = pd.read_csv(ROOT/"data"/"ES_stoch_daily.csv"); d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["date"] = pd.to_datetime(d["DateTime"]).dt.date.astype(str)
    d = d[["date", "High", "Low", "Close"]].rename(columns=str.lower)
    m = pd.read_parquet(ROOT/"data"/"bars"/"_continuous_1m.parquet"); m["DateTime"] = pd.to_datetime(m["DateTime"])
    m["date"] = m["DateTime"].dt.date.astype(str); m["t"] = m["DateTime"].dt.strftime("%H:%M")
    p = m[m.t == "14:59"].set_index("date")["Open"].rename("p")           # 15:59 ET price (open-stamped)
    thru = m[m.t <= "14:58"].groupby("date").agg(h=("High", "max"), l=("Low", "min"))  # session H/L thru 15:59 ET
    df = d.merge(thru.join(p).reset_index(), on="date", how="left").sort_values("date").reset_index(drop=True)
    C = np.where(df.p.isna(), df.close, df.p).astype(float)
    H = np.where(df.h.isna(), df.high, df.h); L = np.where(df.l.isna(), df.low, df.l)
    sma100 = pd.Series(C).rolling(100).mean().values; sma5 = pd.Series(C).rolling(5).mean().values
    ll = pd.Series(L).rolling(8).min().values; hh = pd.Series(H).rolling(8).max().values
    K = 100*(C-ll)/np.where(hh-ll == 0, 1, hh-ll)
    fire = (K < 15) & (C > sma100); dt = df.date.values
    sig = []
    for i in range(110, len(df)-1):
        if fire[i] and "2021-07" <= dt[i][:7] and dt[i] <= "2023-12-29":
            j = next((jj for jj in range(i+1, min(len(df), i+41)) if C[jj] > sma5[jj]), min(len(df)-1, i+40))
            sig.append((dt[i], dt[j]))
    return sig


def run():
    sig = causal_signals()
    dates = set(); [dates.update([e, x]) for e, x in sig]
    ch = mm.load(dates, DTE, sorted(glob.glob(str(OPT/"*.txt")))); by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = {}
    for f in sorted(glob.glob(str(OPT/"*.txt"))):
        t = pd.read_csv(f, skipinitialspace=True, usecols=lambda c: c.strip().strip("[]").upper() in ("QUOTE_DATE", "UNDERLYING_LAST"))
        t.columns = [c.strip().strip("[]").upper() for c in t.columns]
        for k, g in t.groupby("QUOTE_DATE"):
            px.setdefault(str(k).strip(), float(g.UNDERLYING_LAST.iloc[0]))
    rows = []
    for e, x in sig:
        en = by.get(e); ex = by.get(x)
        if en is None:
            continue
        exp = en.iloc[(en.DTE-DTE).abs().argmin()].EXPIRE_DATE
        puts = en[(en.EXPIRE_DATE == exp) & en.P_DELTA.notna() & (en.P_BID > 0) & (en.P_ASK > 0)]
        if len(puts) < 4:
            continue
        sp = puts.iloc[(puts.P_DELTA.abs()-SHORT_D).abs().argmin()]; av = puts[puts.STRIKE <= sp.STRIKE-WIDTH]
        if av.empty:
            continue
        lp = av.iloc[(av.STRIKE-(sp.STRIKE-WIDTH)).abs().argmin()]
        if lp.STRIKE >= sp.STRIKE:
            continue
        cr = fp(sp.P_BID, sp.P_ASK, "sell") - fp(lp.P_BID, lp.P_ASK, "buy")
        if cr <= 0:
            continue
        past = pd.to_datetime(x) > pd.to_datetime(exp); early = not past
        if past or ex is None:
            S = px.get(exp if past else x)
            if S is None:
                continue
            cost = max(0, sp.STRIKE-S) - max(0, lp.STRIKE-S); early = not past
        else:
            def q(KK, s):
                r = ex[(ex.EXPIRE_DATE == exp) & (ex.STRIKE == KK)]
                return fp(float(r.iloc[0].P_BID), float(r.iloc[0].P_ASK), s) if okp(r) else None
            xs = q(sp.STRIKE, "buy"); xl = q(lp.STRIKE, "sell"); undx = float(ex.iloc[0].UNDERLYING_LAST)
            cost = (xs-xl) if (xs is not None and xl is not None) else (max(0, sp.STRIKE-undx)-max(0, lp.STRIKE-undx))
        fee = 2*FEE + (2*FEE if early else 0)
        rows.append((e, x, cr*100, (cr-cost)*100-fee, (sp.STRIKE-lp.STRIKE-cr)*100))
    t = pd.DataFrame(rows, columns=["entry", "exit", "credit", "pnl", "coll"])
    pf = t.pnl[t.pnl > 0].sum()/(-t.pnl[t.pnl < 0].sum()) if (t.pnl < 0).any() else float("inf")
    eq = t.pnl.cumsum().values; mdd = (eq-np.maximum.accumulate(eq)).min()
    print(f"causal 15:59 signals: {len(sig)}   priced trades: {len(t)}")
    print(f"=== CAUSAL 15:59 BPS {DTE}DTE/{WIDTH}pt, BID/ASK, ${FEE}/contract, 2021-07..2023-12 ===")
    print(f"trades {len(t)}  win {(t.pnl>0).mean()*100:.0f}%  PF {pf:.2f}  total ${t.pnl.sum():+,.0f}  maxDD ${mdd:+,.0f}")
    print(f"avg ${t.pnl.mean():+.0f}  worst ${t.pnl.min():+,.0f}")
    print("CAVEATS: fill-drift (16:00 mark vs 16:00-16:15 real fill) unmeasured; n small; benign regime.")


if __name__ == "__main__":
    run()
