"""BPS exit-rule shootout (S73 hypothesis test) — does "manage at 50%" beat SMA5?

Same entries as mr_bps_regime_wf.py (daily STMR, 14DTE/50pt/30Δ, bid/ask, $1.30/ct,
OptionsDX EOD 2010-2023). The spread is re-priced EVERY EOD it is open (targeted
per-strike scan — only the 2 strikes per trade are kept, so memory stays tiny), then
exit variants are simulated on those marks:

  sma5      first daily close > SMA5 -> buy back next mark (the current playbook rule)
  expiry    hold to settlement
  tp50      buy back when spread can be closed for <= 50% of entry credit
  tp50_sl2  tp50 + stop when close cost >= 2x credit
  sl2       stop only
  tp50_sma5 whichever of tp50 / sma5 hits first

The tastylive claim under test: TP50 improves risk-adjusted results vs holding.
Run: .venv/Scripts/python.exe scripts/mr_bps_exit_rules.py
"""
import glob
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OPT = ROOT / "data" / "optionsdx"
spec = importlib.util.spec_from_file_location("wf", str(ROOT / "scripts" / "mr_bps_regime_wf.py"))
wf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wf)

FEE = 1.30


def entry_positions(sig):
    """Price entries; return [{entry, sma5_exit, credit, ks, kl, expiry}]."""
    dates = {e for e, _ in sig}
    ch = wf.mm.load(dates, wf.DTE, sorted(glob.glob(str(OPT / "*.txt"))))
    by = {k: v for k, v in ch.groupby("QUOTE_DATE")}
    out = []
    for e, x in sig:
        en = by.get(e)
        if en is None:
            continue
        exp = en.iloc[(en.DTE - wf.DTE).abs().argmin()].EXPIRE_DATE
        puts = en[(en.EXPIRE_DATE == exp) & en.P_DELTA.notna() & (en.P_BID > 0) & (en.P_ASK > 0)]
        if len(puts) < 4:
            continue
        sp = puts.iloc[(puts.P_DELTA.abs() - wf.SHORT_D).abs().argmin()]
        av = puts[puts.STRIKE <= sp.STRIKE - wf.WIDTH]
        if av.empty:
            continue
        lp = av.iloc[(av.STRIKE - (sp.STRIKE - wf.WIDTH)).abs().argmin()]
        if lp.STRIKE >= sp.STRIKE:
            continue
        cr = wf.fp(sp.P_BID, sp.P_ASK, "sell") - wf.fp(lp.P_BID, lp.P_ASK, "buy")
        if cr <= 0:
            continue
        out.append({"entry": e, "sig_exit": x, "credit": cr,
                    "ks": float(sp.STRIKE), "kl": float(lp.STRIKE), "expiry": str(exp)})
    return out


def collect_marks(pos):
    """Per-file scan keeping ONLY (date, expiry, strike in {ks,kl}) rows we need."""
    need_exp = {}
    for p in pos:
        need_exp.setdefault(p["expiry"], set()).update([p["ks"], p["kl"]])
    marks, und = {}, {}
    use = ("QUOTE_DATE", "EXPIRE_DATE", "STRIKE", "P_BID", "P_ASK", "UNDERLYING_LAST")
    for f in sorted(glob.glob(str(OPT / "*.txt"))):
        hdr = pd.read_csv(f, nrows=0, skipinitialspace=True)
        cols = {c.strip().strip("[]").upper(): c for c in hdr.columns}
        if any(k not in cols for k in use):
            continue
        df = pd.read_csv(f, usecols=[cols[k] for k in use], skipinitialspace=True)
        df.columns = [c.strip().strip("[]").upper() for c in df.columns]
        df["EXPIRE_DATE"] = df.EXPIRE_DATE.astype(str).str.strip()
        df = df[df.EXPIRE_DATE.isin(need_exp)]
        if df.empty:
            continue
        df["QUOTE_DATE"] = df.QUOTE_DATE.astype(str).str.strip()
        for c in ("STRIKE", "P_BID", "P_ASK", "UNDERLYING_LAST"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        for k, g in df.groupby("QUOTE_DATE"):
            und.setdefault(k, float(g.UNDERLYING_LAST.iloc[0]))
        df = df[[r and (s in need_exp[e]) for r, s, e in
                 zip(df.STRIKE.notna(), df.STRIKE, df.EXPIRE_DATE)]]
        for _, r in df.iterrows():
            if r.P_BID == r.P_BID and r.P_ASK == r.P_ASK and r.P_ASK > 0:
                marks[(r.QUOTE_DATE, r.EXPIRE_DATE, r.STRIKE)] = (float(r.P_BID), float(r.P_ASK))
    return marks, und


def simulate(pos, marks, und, all_dates):
    """Walk each trade's open days; record close-cost path; apply each rule."""
    rules = ["sma5", "expiry", "tp50", "tp50_sl2", "sl2", "tp50_sma5"]
    res = {r: [] for r in rules}
    dates_sorted = sorted(all_dates)
    for p in pos:
        cr, ks, kl, exp = p["credit"], p["ks"], p["kl"], p["expiry"]
        days = [d for d in dates_sorted if p["entry"] < d <= min(exp, p["sig_exit"] if False else exp)]
        # daily close-cost path (buy short back at ask, sell long at bid)
        path = []
        for d in days:
            m_s, m_l = marks.get((d, exp, ks)), marks.get((d, exp, kl))
            if m_s and m_l:
                cost = wf.fp(*m_s, "buy") - wf.fp(*m_l, "sell")
                path.append((d, cost))
        S = und.get(exp)
        settle = (max(0, ks - S) - max(0, kl - S)) if S is not None else None

        def pnl_close(cost, early):
            return (cr - cost) * 100 - (2 * FEE + (2 * FEE if early else 0))

        for rule in rules:
            done = False
            for d, cost in path:
                hit_tp = "tp50" in rule and cost <= cr * 0.5
                hit_sl = "sl2" in rule and cost >= cr * 2
                hit_sma = "sma5" in rule and d >= p["sig_exit"]
                if hit_tp or hit_sl or hit_sma:
                    res[rule].append(pnl_close(cost, early=True))
                    done = True
                    break
            if not done:
                if settle is not None:
                    res[rule].append(pnl_close(settle, early=False))
    return res


def stats(p):
    p = pd.Series(p, dtype=float)
    if not len(p):
        return "n=0"
    pf = p[p > 0].sum() / -p[p < 0].sum() if (p < 0).any() else float("inf")
    eq = p.cumsum().values
    mdd = (eq - np.maximum.accumulate(eq)).min()
    return (f"n {len(p):3d}  win {(p > 0).mean() * 100:3.0f}%  PF {pf:5.2f}  avg ${p.mean():+7.0f}  "
            f"total ${p.sum():+9,.0f}  maxDD ${mdd:+8,.0f}")


def main():
    sig = wf.daily_signals()
    pos = entry_positions(sig)
    print(f"entries priced: {len(pos)}")
    marks, und = collect_marks(pos)
    print(f"daily marks collected: {len(marks)} strike-days, {len(und)} sessions")
    res = simulate(pos, marks, und, set(und))
    print("\n=== BPS 14DTE/50pt EXIT-RULE SHOOTOUT (2010-2023, bid/ask, $1.30/ct) ===")
    for rule, p in res.items():
        print(f"{rule:10s} {stats(p)}")
    print("\nNote: 'sma5' here re-prices the exit at the SIGNAL day's EOD marks — matches the")
    print("playbook rule. tp50* = tastylive 'manage at 50%' variants. Same entries throughout.")


if __name__ == "__main__":
    main()
