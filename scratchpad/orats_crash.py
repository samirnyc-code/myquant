# -*- coding: utf-8 -*-
"""How the STMR bull put spread performed through every market crash since 2008.
BPS 30/10, K8<15 & C>SMA100, exit SMA5, realistic fill + fees. Tags trades by crash window,
shows worst single trades, and whether the SMA100 filter kept it out of the core."""
import glob
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); DTE_T, FEE, SP = 14, 1.30, 0.0125

d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"], d["sma5"] = C.rolling(100).mean(), C.rolling(5).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
close_by = dict(zip(d.Date, C))
above100 = dict(zip(d.Date, C > d.sma100))
ent = (d.k8 < 15) & (C > d.sma100) & d.k8.notna() & d.sma100.notna()
exi = C > d.sma5
EPS, ip, cur = [], False, None
for i in range(len(d)):
    if not ip and ent.iloc[i]:
        cur = {"entry": d.Date.iloc[i]}; ip = True
    elif ip and exi.iloc[i]:
        cur["exit"] = d.Date.iloc[i]; EPS.append(cur); ip = False

need = set()
for e in EPS:
    need.add(e["entry"]); need.add(e.get("exit"))
ch = {}
for f in sorted(glob.glob(str(ROOT / "data" / "orats" / "SPX" / "SPX_*.parquet"))):
    yr = Path(f).stem.split("_")[-1]
    nd = {x for x in need if x and x[:4] == yr}
    if not nd:
        continue
    df = pd.read_parquet(f, columns=["tradeDate", "expirDate", "dte", "strike", "delta", "putValue"])
    df = df[(df.dte >= 5) & (df.dte <= 25) & df.tradeDate.isin(nd)]
    for t, g in df.groupby("tradeDate"):
        ch[t] = g


def px(m, s):
    return m*(1-SP/2) if s == "sell" else m*(1+SP/2)


def trade(ep):
    c = ch.get(ep["entry"])
    if c is None:
        return None
    x = c[c.dte >= 1]
    if x.empty:
        return None
    exp = x.iloc[(x.dte-DTE_T).abs().argsort()].iloc[0].expirDate
    e = c[(c.expirDate == exp) & c.putValue.notna() & (c.putValue > 0)]
    if len(e) < 2:
        return None
    s = e.iloc[(e.delta-0.70).abs().argsort()].iloc[0]; bl = e[e.strike < s.strike]
    if bl.empty:
        return None
    lo = bl.iloc[(bl.delta-0.90).abs().argsort()].iloc[0]; cr = px(s.putValue, "sell")-px(lo.putValue, "buy")
    if cr <= 0:
        return None
    risk = (s.strike-lo.strike-cr)*100; ex = ep.get("exit")
    if ex and ex <= exp:
        ce = ch.get(ex); v = None
        if ce is not None:
            a = ce[(ce.expirDate == exp) & (ce.strike == s.strike)]; b = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
            if not a.empty and not b.empty:
                v = px(a.iloc[0].putValue, "buy")-px(b.iloc[0].putValue, "sell")
        if v is None:
            S = close_by.get(ex); v = (max(0, s.strike-S)-max(0, lo.strike-S)) if S else cr
        pnl = (cr-v)*100-4*FEE
    else:
        S = close_by.get(exp)
        if S is None:
            return None
        pnl = (cr-(max(0, s.strike-S)-max(0, lo.strike-S)))*100-2*FEE
    return {"entry": ep["entry"], "pnl": pnl, "risk": risk}


T = pd.DataFrame([t for t in (trade(e) for e in EPS) if t])

CRASHES = [
    ("2008 GFC", "2008-09-01", "2008-12-31"),
    ("2010 Flash Crash", "2010-05-01", "2010-06-30"),
    ("2011 US downgrade", "2011-08-01", "2011-10-31"),
    ("2015-16 China/oil", "2015-08-01", "2016-02-29"),
    ("2018 Volmageddon", "2018-01-25", "2018-02-28"),
    ("2018 Q4 selloff", "2018-10-01", "2018-12-31"),
    ("2020 COVID", "2020-02-20", "2020-04-30"),
    ("2022 bear", "2022-01-01", "2022-10-31"),
]
print("=" * 92)
print("STMR BULL PUT SPREAD THROUGH MARKET CRASHES (BPS 30/10, realistic fill+fees)")
print("=" * 92)
print(f"{'crash':22s}{'tradingdays':>12s}{'daysAbv100':>11s}{'STMRtrades':>11s}{'net P&L':>10s}{'worst':>9s}{'win%':>6s}")
for name, a, b in CRASHES:
    days = d[(d.Date >= a) & (d.Date <= b)]
    nd = len(days); abv = int((days.Close > days.sma100).sum())
    tr = T[(T.entry >= a) & (T.entry <= b)]
    if len(tr):
        print(f"{name:22s}{nd:>12d}{abv:>11d}{len(tr):>11d}{tr.pnl.sum():>10,.0f}{tr.pnl.min():>9,.0f}{(tr.pnl>0).mean()*100:>6.0f}")
    else:
        print(f"{name:22s}{nd:>12d}{abv:>11d}{0:>11d}{'—':>10s}{'—':>9s}{'—':>6s}  (filter kept it OUT)")
print("\n--- 8 WORST individual STMR trades ever, and when ---")
for _, r in T.nsmallest(8, "pnl").iterrows():
    tag = next((n for n, a, b in CRASHES if a <= r.entry <= b), "normal market")
    print(f"   {r.entry}  ${r.pnl:>8,.0f}   ({tag})")
eq = T.sort_values("entry").pnl.cumsum()
print(f"\n--- overall: {len(T)} trades, total ${T.pnl.sum():,.0f}, "
      f"worst single ${T.pnl.min():,.0f}, max drawdown ${(eq.cummax()-eq).max():,.0f} ---")
print(f"    % of trading days where C>SMA100 (strategy CAN trade): {above100_pct:.0f}%" if (above100_pct:=100*np.mean(list(above100.values()))) else "")
