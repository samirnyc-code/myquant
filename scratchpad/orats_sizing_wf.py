# -*- coding: utf-8 -*-
"""BPS 30/10, K8<15, exit SMA5 (frozen params):
  (A) SIZING LADDER — XSP x1..10 vs SPX x1, 2020-2026, realistic haircut + fees, gross/fees/net split.
  (B) WALK-FORWARD — SPX 2007-2026, fixed params tested across sub-periods (out-of-sample proof).
"""
import glob
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
DTE_T, FEE, SP = 14, 1.30, 0.0125    # $1.30/ct/side ; 1.25% spread haircut

d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"], d["sma5"] = C.rolling(100).mean(), C.rolling(5).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
close_by = dict(zip(d.Date, C))

ent = (d.k8 < 15) & (C > d.sma100) & d.k8.notna() & d.sma100.notna()
exi = C > d.sma5
EPS, ip, cur = [], False, None
for i in range(len(d)):
    if not ip and ent.iloc[i]:
        cur = {"entry": d.Date.iloc[i]}; ip = True
    elif ip and exi.iloc[i]:
        cur["exit"] = d.Date.iloc[i]; EPS.append(cur); ip = False


def load(tk):
    need = set()
    for e in EPS:
        need.add(e["entry"]); need.add(e.get("exit"))
    ch = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "orats" / tk / f"{tk}_*.parquet"))):
        yr = Path(f).stem.split("_")[-1]
        nd = {x for x in need if x and x[:4] == yr}
        if not nd:
            continue
        df = pd.read_parquet(f, columns=["tradeDate", "expirDate", "dte", "strike", "delta", "putValue"])
        df = df[(df.dte >= 5) & (df.dte <= 25) & df.tradeDate.isin(nd)]
        for t, g in df.groupby("tradeDate"):
            ch[t] = g
    return ch


def px(m, side):
    return m * (1 - SP / 2) if side == "sell" else m * (1 + SP / 2)


def bps_trades(ch, undf):
    """Per-1-spread: gross P&L (pre-fee), fee, risk(collateral). Realistic haircut applied."""
    rows = []
    for ep in EPS:
        c = ch.get(ep["entry"])
        if c is None:
            continue
        x = c[c.dte >= 1]
        if x.empty:
            continue
        exp = x.iloc[(x.dte - DTE_T).abs().argsort()].iloc[0].expirDate
        e = c[(c.expirDate == exp) & c.putValue.notna() & (c.putValue > 0)]
        if len(e) < 2:
            continue
        s = e.iloc[(e.delta - 0.70).abs().argsort()].iloc[0]
        bl = e[e.strike < s.strike]
        if bl.empty:
            continue
        lo = bl.iloc[(bl.delta - 0.90).abs().argsort()].iloc[0]
        cr = px(s.putValue, "sell") - px(lo.putValue, "buy")
        if cr <= 0:
            continue
        risk = (s.strike - lo.strike - cr) * 100
        ex = ep.get("exit")
        if ex and ex <= exp:
            ce = ch.get(ex); v = None
            if ce is not None:
                a = ce[(ce.expirDate == exp) & (ce.strike == s.strike)]; b = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
                if not a.empty and not b.empty:
                    v = px(a.iloc[0].putValue, "buy") - px(b.iloc[0].putValue, "sell")
            if v is None:
                S = undf(ex); v = (max(0, s.strike-S)-max(0, lo.strike-S)) if S else cr
            gross = (cr - v) * 100; fee = 4 * FEE
        else:
            S = undf(exp)
            if S is None:
                continue
            gross = (cr - (max(0, s.strike-S)-max(0, lo.strike-S))) * 100; fee = 2 * FEE
        rows.append({"year": int(ep["entry"][:4]), "exit": ex or ep["entry"],
                     "gross": gross, "fee": fee, "net": gross - fee, "risk": risk})
    return pd.DataFrame(rows)


und = {"SPX": lambda x: close_by.get(x), "XSP": lambda x: (close_by.get(x)/10 if close_by.get(x) else None)}
T = {tk: bps_trades(load(tk), und[tk]) for tk in ("XSP", "SPX")}


def stats(g):
    gp, gl = g.net[g.net > 0].sum(), -g.net[g.net < 0].sum()
    eq = g.sort_values("exit").net.cumsum()
    return dict(n=len(g), win=(g.net > 0).mean()*100, PF=(gp/gl if gl else np.nan),
                gross=g.gross.sum(), fee=g.fee.sum(), net=g.net.sum(),
                dd=(eq.cummax()-eq).max(), medrisk=g.risk.median())


# ---------- (A) SIZING LADDER on the common 2020-2026 window ----------
win = {tk: T[tk][T[tk].year >= 2020].copy() for tk in T}
sx, sp = stats(win["XSP"]), stats(win["SPX"])
print("=" * 104)
print("SIZING LADDER — BPS 30/10, K8<15, exit SMA5 · 2020-2026 · haircut 1.25% + $1.30/ct/side")
print("=" * 104)
print(f"{'position':11s}{'capital':>11s}{'n':>4s}{'win%':>6s}{'PF':>6s}{'gross$':>11s}{'fees$':>10s}"
      f"{'NET$':>11s}{'fee%gr':>8s}{'RoC%':>7s}{'maxDD$':>10s}")
def row(lbl, base, N):
    cap = base["medrisk"] * N
    print(f"{lbl:11s}{cap:>11,.0f}{base['n']:>4d}{base['win']:>6.0f}{base['PF']:>6.2f}"
          f"{base['gross']*N:>11,.0f}{base['fee']*N:>10,.0f}{base['net']*N:>11,.0f}"
          f"{base['fee']/base['gross']*100:>8.1f}{base['net']/(base['medrisk'])*100/base['n']*base['n']:>7.1f}"  # RoC invariant
          f"{base['dd']*N:>10,.0f}")
for N in range(1, 11):
    row(f"XSP x{N}", sx, N)
row("SPX x1", sp, 1)
print("\nNote: 10x XSP ≈ 1x SPX notional. PF/win/RoC are size-invariant; gross/fees/net/DD/capital scale with N.")
print(f"XSP fee drag: {sx['fee']/sx['gross']*100:.1f}% of gross vs SPX {sp['fee']/sp['gross']*100:.1f}%.")

# ---------- (B) WALK-FORWARD: frozen params across sub-periods (SPX, full history) ----------
print("\n" + "=" * 104)
print("WALK-FORWARD — SPX, FROZEN params (30/10, K8<15, SMA5), tested per sub-period (out-of-sample)")
print("=" * 104)
g = T["SPX"]
periods = [("2007-2012", 2007, 2012), ("2013-2018 (OOS)", 2013, 2018), ("2019-2026 (OOS)", 2019, 2026)]
print(f"{'period':18s}{'n':>4s}{'win%':>7s}{'PF':>7s}{'avgNet$':>10s}{'total$':>11s}{'maxDD$':>10s}")
for lbl, a, b in periods:
    sub = g[(g.year >= a) & (g.year <= b)]
    s = stats(sub)
    print(f"{lbl:18s}{s['n']:>4d}{s['win']:>7.0f}{s['PF']:>7.2f}{s['net']/s['n']:>10,.0f}{s['net']:>11,.0f}{s['dd']:>10,.0f}")
sall = stats(g)
print(f"{'ALL 2007-2026':18s}{sall['n']:>4d}{sall['win']:>7.0f}{sall['PF']:>7.2f}{sall['net']/sall['n']:>10,.0f}{sall['net']:>11,.0f}{sall['dd']:>10,.0f}")
