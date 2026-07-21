"""BPS family — VIX-rank regime conditioning + yearly walk-forward (S73, playbook §F).

Same pricing as the honest 146-trade backtest (14DTE/50pt/30Δ short, BID/ASK fills,
$1.30/contract, OptionsDX EOD 2010-2023) — the daily-close signal set (research view;
the executable causal set differs ~13%, see mr_bps_causal_1559.py). NEW here:

  A. Regime conditioning: each trade tagged with VIX level, VIX 252d rank, 5d VIX
     direction at entry -> per-bucket stats. Question: does "elevated-but-falling IV"
     actually select the good trades, as the playbook §A prior claims?
  B. Yearly walk-forward: train on trailing 4y, pick the best simple filter by
     expectancy (min 8 train trades), trade next year OOS. Honest OOS equity.

Run: .venv/Scripts/python.exe scripts/mr_bps_regime_wf.py
"""
import glob
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OPT = ROOT / "data" / "optionsdx"
spec = importlib.util.spec_from_file_location("m", str(ROOT / "scripts" / "mr_options_strategies.py"))
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)

SLIP, FEE, DTE, WIDTH, SHORT_D = 1.0, 1.30, 14, 50, 0.30

FILTERS = {  # name -> f(row) on regime tags at entry
    "none": lambda r: True,
    "rank>33": lambda r: r.vrank > 1 / 3,
    "rank>50": lambda r: r.vrank > 0.5,
    "falling": lambda r: r.vchg5 < 0,
    "rank>33&falling": lambda r: r.vrank > 1 / 3 and r.vchg5 < 0,
    "rank<33": lambda r: r.vrank <= 1 / 3,
}


def fp(b, a, s):
    mid = (b + a) / 2
    half = (a - b) / 2
    return mid - SLIP * half if s == "sell" else mid + SLIP * half


def okp(r):
    return (not r.empty) and np.isfinite(r.iloc[0].P_BID) and np.isfinite(r.iloc[0].P_ASK) and r.iloc[0].P_ASK > 0


def daily_signals():
    d = pd.read_csv(ROOT / "data" / "ES_stoch_daily.csv")
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["date"] = pd.to_datetime(d["DateTime"]).dt.date.astype(str)
    C, H, L = d.Close.values, d.High.values, d.Low.values
    sma100 = pd.Series(C).rolling(100).mean().values
    sma5 = pd.Series(C).rolling(5).mean().values
    ll = pd.Series(L).rolling(8).min().values
    hh = pd.Series(H).rolling(8).max().values
    K = 100 * (C - ll) / np.where(hh - ll == 0, 1, hh - ll)
    fire = (K < 15) & (C > sma100)
    dt_ = d.date.values
    sig = []
    for i in range(110, len(d) - 1):
        if fire[i] and "2010-02" <= dt_[i][:7] <= "2023-12":
            j = next((jj for jj in range(i + 1, min(len(d), i + 41)) if C[jj] > sma5[jj]),
                     min(len(d) - 1, i + 40))
            sig.append((dt_[i], dt_[j]))
    return sig


def vix_tags():
    v = pd.read_csv(ROOT / "data" / "vix_daily.csv")
    dcol, ccol = v.columns[0], v.columns[-1]
    v["date"] = pd.to_datetime(v[dcol]).dt.date.astype(str)
    v["vix"] = v[ccol].astype(float)
    v["vrank"] = v.vix.rolling(252).apply(lambda w: (w <= w.iloc[-1]).mean(), raw=False)
    v["vchg5"] = v.vix.diff(5)
    return v.set_index("date")[["vix", "vrank", "vchg5"]]


def price_trades(sig):
    dates = set()
    for e, x in sig:
        dates.update([e, x])
    files = sorted(glob.glob(str(OPT / "*.txt")))
    ch = mm.load(dates, DTE, files)
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    px = {}
    for f in files:
        t = pd.read_csv(f, skipinitialspace=True,
                        usecols=lambda c: c.strip().strip("[]").upper() in ("QUOTE_DATE", "UNDERLYING_LAST"))
        t.columns = [c.strip().strip("[]").upper() for c in t.columns]
        for k, g in t.groupby("QUOTE_DATE"):
            px.setdefault(str(k).strip(), float(g.UNDERLYING_LAST.iloc[0]))
    rows = []
    for e, x in sig:
        en, ex = by.get(e), by.get(x)
        if en is None:
            continue
        exp = en.iloc[(en.DTE - DTE).abs().argmin()].EXPIRE_DATE
        puts = en[(en.EXPIRE_DATE == exp) & en.P_DELTA.notna() & (en.P_BID > 0) & (en.P_ASK > 0)]
        if len(puts) < 4:
            continue
        sp = puts.iloc[(puts.P_DELTA.abs() - SHORT_D).abs().argmin()]
        av = puts[puts.STRIKE <= sp.STRIKE - WIDTH]
        if av.empty:
            continue
        lp = av.iloc[(av.STRIKE - (sp.STRIKE - WIDTH)).abs().argmin()]
        if lp.STRIKE >= sp.STRIKE:
            continue
        cr = fp(sp.P_BID, sp.P_ASK, "sell") - fp(lp.P_BID, lp.P_ASK, "buy")
        if cr <= 0:
            continue
        past = pd.to_datetime(x) > pd.to_datetime(exp)
        early = not past
        if past or ex is None:
            S = px.get(exp if past else x)
            if S is None:
                continue
            cost = max(0, sp.STRIKE - S) - max(0, lp.STRIKE - S)
        else:
            def q(KK, s):
                r = ex[(ex.EXPIRE_DATE == exp) & (ex.STRIKE == KK)]
                return fp(float(r.iloc[0].P_BID), float(r.iloc[0].P_ASK), s) if okp(r) else None
            xs, xl = q(sp.STRIKE, "buy"), q(lp.STRIKE, "sell")
            undx = float(ex.iloc[0].UNDERLYING_LAST)
            cost = (xs - xl) if (xs is not None and xl is not None) else (
                max(0, sp.STRIKE - undx) - max(0, lp.STRIKE - undx))
        fee = 2 * FEE + (2 * FEE if early else 0)
        rows.append((e, x, cr * 100, (cr - cost) * 100 - fee))
    return pd.DataFrame(rows, columns=["entry", "exit", "credit", "pnl"])


def stats(p):
    if not len(p):
        return "n=0"
    pf = p[p > 0].sum() / -p[p < 0].sum() if (p < 0).any() else float("inf")
    return (f"n {len(p):3d}  win {(p > 0).mean() * 100:3.0f}%  PF {pf:5.2f}  "
            f"avg ${p.mean():+7.0f}  total ${p.sum():+9,.0f}")


def main():
    sig = daily_signals()
    print(f"daily STMR signals 2010-2023: {len(sig)}")
    t = price_trades(sig)
    vt = vix_tags()
    t = t.join(vt, on="entry")
    t["year"] = t.entry.str[:4].astype(int)
    t = t.dropna(subset=["vrank", "vchg5"]).reset_index(drop=True)
    print(f"priced + VIX-tagged trades: {len(t)}\n")

    print("=== A. REGIME CONDITIONING (full sample, IN-SAMPLE — descriptive only) ===")
    for name, f in FILTERS.items():
        sel = t[t.apply(f, axis=1)]
        print(f"{name:16s} {stats(sel.pnl)}")
    print("\nby VIX-rank tercile:")
    t["bucket"] = pd.cut(t.vrank, [0, 1 / 3, 2 / 3, 1.01], labels=["low", "mid", "high"])
    for b, g in t.groupby("bucket", observed=True):
        print(f"rank {b:5s}      {stats(g.pnl)}")

    print("\n=== B. YEARLY WALK-FORWARD (train 4y -> trade next year OOS) ===")
    oos = []
    for yr in range(2014, 2024):
        tr = t[(t.year >= yr - 4) & (t.year < yr)]
        te = t[t.year == yr]
        if len(tr) < 8 or not len(te):
            continue
        best, best_exp = "none", -1e9
        for name, f in FILTERS.items():
            s = tr[tr.apply(f, axis=1)]
            if len(s) >= 8 and s.pnl.mean() > best_exp:
                best, best_exp = name, s.pnl.mean()
        sel = te[te.apply(FILTERS[best], axis=1)]
        oos.append((yr, best, sel.pnl))
        print(f"{yr}: filter '{best:16s}' (train exp ${best_exp:+.0f})  OOS {stats(sel.pnl)}")
    allo = pd.concat([p for _, _, p in oos]) if oos else pd.Series(dtype=float)
    base = t[t.year >= 2014].pnl
    print(f"\nOOS filtered   : {stats(allo)}")
    print(f"unfiltered 14+ : {stats(base)}")
    eq = allo.cumsum().values if len(allo) else np.array([0.0])
    print(f"OOS maxDD ${(eq - np.maximum.accumulate(eq)).min():+,.0f}")
    t.to_csv(ROOT / "data" / "options_sim" / "bps_regime_trades.csv", index=False)
    print("\ntrade file -> data/options_sim/bps_regime_trades.csv")
    print("CAVEATS: daily-close signal set (research view, NOT the executable causal set);")
    print("filter selection in-sample per fold is only as good as ~30 trades/fold allows.")


if __name__ == "__main__":
    main()
