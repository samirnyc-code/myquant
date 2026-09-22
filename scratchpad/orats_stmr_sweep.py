"""STMR parameter sweep on SPX ORATS 2007-2026 (close entry, one-at-a-time).
Sensitivity map (NOT an optimizer) across oversold level, exit SMA, and option deltas,
for: bull put spread, long call, bull call spread. Fill=MID (optimistic), fees $1.30/ct/side.
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant"); ORATS = ROOT / "data" / "orats" / "SPX"
DTE_T, FEE = 14, 1.30

# ---- daily indicators ----
d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"] = C.rolling(100).mean()
for n in (3, 5, 8, 10):
    d[f"sma{n}"] = C.rolling(n).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
close_by = dict(zip(d.Date, d.Close))

OVERSOLD, EXITSMA = [10, 15, 20, 25], [3, 5, 8, 10]


def gen_trades(oversold, exsma):
    ent = (d.k8 < oversold) & (C > d.sma100) & d.k8.notna() & d.sma100.notna()
    exi = C > d[f"sma{exsma}"]
    out, inpos, cur = [], False, None
    for i in range(len(d)):
        if not inpos and ent.iloc[i]:
            cur = {"entry": d.Date.iloc[i]}; inpos = True
        elif inpos and exi.iloc[i]:
            cur["exit"] = d.Date.iloc[i]; out.append(cur); inpos = False
    if inpos:
        cur["exit"] = None; out.append(cur)
    return out


# ---- load ORATS chains for every date any config could touch (dte 5..25 only = light) ----
allt = [t for ov in OVERSOLD for ex in EXITSMA for t in gen_trades(ov, ex)]
need = set()
for t in allt:
    need.add(t["entry"])
    if t["exit"]:
        need.add(t["exit"])
cols = ["tradeDate", "expirDate", "dte", "strike", "delta", "putValue", "callValue"]
chains = {}
for f in sorted(glob.glob(str(ORATS / "SPX_*.parquet"))):
    yr = Path(f).stem.split("_")[-1]
    nd = {x for x in need if x[:4] == yr}
    if not nd:
        continue
    df = pd.read_parquet(f, columns=cols)
    df = df[(df.dte >= 5) & (df.dte <= 25) & df.tradeDate.isin(nd)]
    for dt_, g in df.groupby("tradeDate"):
        chains[dt_] = g
print(f"loaded {len(chains)} chain-days for {len(need)} needed dates")


def _exp(ch):
    return None if ch.empty else ch.iloc[(ch.dte - DTE_T).abs().argsort()].iloc[0].expirDate


def pnl_bps(trades, sd, ld):
    r = []
    for t in trades:
        ch = chains.get(t["entry"])
        if ch is None:
            continue
        exp = _exp(ch)
        if exp is None:
            continue
        e = ch[(ch.expirDate == exp) & ch.putValue.notna() & (ch.putValue > 0)]
        if len(e) < 2:
            continue
        s = e.iloc[(e.delta - sd).abs().argsort()].iloc[0]
        below = e[e.strike < s.strike]
        if below.empty:
            continue
        lo = below.iloc[(below.delta - ld).abs().argsort()].iloc[0]
        cr = s.putValue - lo.putValue
        if cr <= 0:
            continue
        w = s.strike - lo.strike
        ex = t["exit"]
        if ex and ex <= exp:
            ce = chains.get(ex)
            v = None
            if ce is not None:
                rs = ce[(ce.expirDate == exp) & (ce.strike == s.strike)]
                rl = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
                if not rs.empty and not rl.empty:
                    v = rs.iloc[0].putValue - rl.iloc[0].putValue
            if v is None:
                S = close_by.get(ex); v = (max(0, s.strike-S)-max(0, lo.strike-S)) if S else cr
            p = (cr - v) * 100 - 4 * FEE
        else:
            S = close_by.get(exp)
            if S is None:
                continue
            p = (cr - (max(0, s.strike-S)-max(0, lo.strike-S))) * 100 - 2 * FEE
        r.append({"pnl": p, "risk": (w - cr) * 100})
    return pd.DataFrame(r)


def pnl_call(trades, cd, spread_short=None):
    """Long call (spread_short=None) or bull CALL spread (sell call at delta spread_short)."""
    r = []
    for t in trades:
        ch = chains.get(t["entry"])
        if ch is None:
            continue
        exp = _exp(ch)
        if exp is None:
            continue
        e = ch[(ch.expirDate == exp) & ch.callValue.notna() & (ch.callValue > 0)]
        if e.empty:
            continue
        lc = e.iloc[(e.delta - cd).abs().argsort()].iloc[0]
        if spread_short is not None:
            up = e[e.strike > lc.strike]
            if up.empty:
                continue
            sc = up.iloc[(up.delta - spread_short).abs().argsort()].iloc[0]
            cost = lc.callValue - sc.callValue
            Ks, Kl = lc.strike, sc.strike
        else:
            cost = lc.callValue; Ks = lc.strike; Kl = None
        if cost <= 0:
            continue
        ex = t["exit"]
        if ex and ex <= exp:
            ce = chains.get(ex); v = None
            if ce is not None:
                r1 = ce[(ce.expirDate == exp) & (ce.strike == Ks)]
                if not r1.empty:
                    v = r1.iloc[0].callValue
                    if Kl is not None:
                        r2 = ce[(ce.expirDate == exp) & (ce.strike == Kl)]
                        v = (v - r2.iloc[0].callValue) if not r2.empty else v
            if v is None:
                S = close_by.get(ex)
                v = (max(0, S-Ks) - (max(0, S-Kl) if Kl else 0)) if S else 0
            p = (v - cost) * 100 - (4 if Kl else 2) * FEE
        else:
            S = close_by.get(exp)
            if S is None:
                continue
            pay = max(0, S-Ks) - (max(0, S-Kl) if Kl else 0)
            p = (pay - cost) * 100 - (2 if Kl else 1) * FEE
        r.append({"pnl": p, "risk": cost * 100})
    return pd.DataFrame(r)


def line(g):
    if g.empty:
        return "   n=0"
    w = (g.pnl > 0).mean() * 100
    gp, gl = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
    pf = gp / gl if gl else np.inf
    roc = g.pnl.mean() / g.risk.mean() * 100
    return (f"n={len(g):3d}  win={w:3.0f}%  PF={pf:4.2f}  avg=${g.pnl.mean():6.0f}  "
            f"RoC/trade={roc:5.1f}%  tot=${g.pnl.sum():8,.0f}  DD=${(g.pnl.cumsum().cummax()-g.pnl.cumsum()).max():7,.0f}")


print("\n" + "=" * 96)
print("SIGNAL SWEEP — base legs: BPS short0.70/long0.90 (30d/10d put) · CALL 0.50 (ATM)")
print("=" * 96)
for inst, fn in [("BPS ", lambda tr: pnl_bps(tr, 0.70, 0.90)), ("CALL", lambda tr: pnl_call(tr, 0.50))]:
    print(f"\n[{inst}]           " + "  ".join(f"exitSMA{e:<2d}" for e in EXITSMA))
    for ov in OVERSOLD:
        for e in EXITSMA:
            pass
        print(f"  K8<{ov:<2d}:")
        for e in EXITSMA:
            print(f"     exitSMA{e:<2d}  {line(fn(gen_trades(ov, e)))}")

print("\n" + "=" * 96)
print("DELTA SWEEP — fixed signal K8<15, exit SMA5")
print("=" * 96)
base = gen_trades(15, 5)
print("\n[BULL PUT SPREAD]  short-delta / long-delta (put deltas):")
for sd, sdl in [(0.80, "20d"), (0.70, "30d"), (0.60, "40d")]:
    for ld, ldl in [(0.90, "10d"), (0.85, "15d")]:
        print(f"  short {sdl}/long {ldl}:  {line(pnl_bps(base, sd, ld))}")
print("\n[LONG CALL]  call delta:")
for cd, lbl in [(0.65, "65d ITM"), (0.50, "50d ATM"), (0.35, "35d OTM")]:
    print(f"  {lbl}:  {line(pnl_call(base, cd))}")
print("\n[BULL CALL SPREAD]  buy 50d / sell short-delta:")
for ss, lbl in [(0.30, "sell 30d"), (0.20, "sell 20d")]:
    print(f"  buy 50d / {lbl}:  {line(pnl_call(base, 0.50, spread_short=ss))}")
print("\nFILL=MID (no bid/ask -> optimistic, worst for the sold BPS). RoC/trade = avg$ / avg capital-at-risk.")
