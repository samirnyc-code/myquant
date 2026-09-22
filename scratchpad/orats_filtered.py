# -*- coding: utf-8 -*-
"""Filtered vs UNfiltered STMR barrage on SPX ORATS. Thomas's filter:
  IBS<40 AND (body0>range0/2.7 OR body1>range1/2.5)   added on top of  %K8<15 & C>SMA100.
Signal from ES_stoch_daily.csv (has Open/High/Low/Close). Options priced on SPX ORATS,
intrinsic settled on SPX close. Realistic fill 1.25%. -> JSON for the report.
"""
import glob, json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant"); ORATS = ROOT / "data" / "orats" / "SPX"
DTE_T, FEE, SP = 14, 1.30, 0.0125
FILLS = {"mid": 0.0, "realistic": 0.0125, "conservative": 0.025}

# ---- signal + Thomas filter from ES daily (has Open) ----
e = pd.read_csv(ROOT / "data" / "ES_stoch_daily.csv")
e.columns = [c.strip().lstrip("﻿") for c in e.columns]
e["date"] = pd.to_datetime(e["DateTime"]).dt.strftime("%Y-%m-%d")
e = e[(e.date >= "2009-01-01") & (e.date <= "2026-12-31")].sort_values("date").reset_index(drop=True)
O, H, L, C = e.Open, e.High, e.Low, e.Close
rng = (H - L).replace(0, np.nan)
e["sma100"], e["sma5"] = C.rolling(100).mean(), C.rolling(5).mean()
for n in (3, 8, 10):
    e[f"sma{n}"] = C.rolling(n).mean()
e["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
e["ibs"] = (C - L) / rng
e["body0"] = (C - O).abs()
e["decisive"] = (e.body0 > rng / 2.7) | (e.body0.shift(1) > rng.shift(1) / 2.5)
e["filt"] = (e.ibs < 0.40) & e.decisive
# SPX close for intrinsic
s = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
s["date"] = pd.to_datetime(s["Date"]).dt.strftime("%Y-%m-%d")
close_by = dict(zip(s.date, s.Close))


def episodes(oversold, exsma, filtered):
    base = (e.k8 < oversold) & (C > e.sma100) & e.k8.notna() & e.sma100.notna()
    ent = base & e.filt if filtered else base
    exi = C > e[f"sma{exsma}"]
    out, ip, cur = [], False, None
    for i in range(len(e)):
        if not ip and ent.iloc[i]:
            cur = {"entry": e.date.iloc[i]}; ip = True
        elif ip and exi.iloc[i]:
            cur["exit"] = e.date.iloc[i]; out.append(cur); ip = False
    if ip:
        cur["exit"] = None; out.append(cur)
    return out


# ---- ORATS chains (union of all dates any config touches) ----
need = set()
for filt in (False, True):
    for ov in (15,):
        for ex in (3, 5, 8, 10):
            for ep in episodes(ov, ex, filt):
                need.add(ep["entry"])
                if ep["exit"]:
                    need.add(ep["exit"])
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
print("chain-days:", len(chains))


def px(mid, side, sp):
    return mid * (1 - sp / 2) if side == "sell" else mid * (1 + sp / 2)


def one(entry, exitd, kind, p1, p2, sp):
    ch = chains.get(entry)
    if ch is None:
        return None
    x = ch[(ch.dte >= 1)]
    if x.empty:
        return None
    exp = x.iloc[(x.dte - DTE_T).abs().argsort()].iloc[0].expirDate
    if kind == "bps":
        d = ch[(ch.expirDate == exp) & ch.putValue.notna() & (ch.putValue > 0)]
        if len(d) < 2:
            return None
        sh = d.iloc[(d.delta - p1).abs().argsort()].iloc[0]
        bl = d[d.strike < sh.strike]
        if bl.empty:
            return None
        lo = bl.iloc[(bl.delta - p2).abs().argsort()].iloc[0]
        cr = px(sh.putValue, "sell", sp) - px(lo.putValue, "buy", sp)
        if cr <= 0:
            return None
        risk = (sh.strike - lo.strike) * 100 - cr * 100
        if exitd and exitd <= exp:
            ce = chains.get(exitd); v = None
            if ce is not None:
                a = ce[(ce.expirDate == exp) & (ce.strike == sh.strike)]; b = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
                if not a.empty and not b.empty:
                    v = px(a.iloc[0].putValue, "buy", sp) - px(b.iloc[0].putValue, "sell", sp)
            if v is None:
                S = close_by.get(exitd); v = (max(0, sh.strike-S)-max(0, lo.strike-S)) if S else cr
            return (cr - v) * 100 - 4 * FEE, risk
        S = close_by.get(exp)
        if S is None:
            return None
        return (cr - (max(0, sh.strike-S)-max(0, lo.strike-S))) * 100 - 2 * FEE, risk
    d = ch[(ch.expirDate == exp) & ch.callValue.notna() & (ch.callValue > 0)]
    if d.empty:
        return None
    lc = d.iloc[(d.delta - p1).abs().argsort()].iloc[0]; Kl = None
    if kind == "bcs":
        up = d[d.strike > lc.strike]
        if up.empty:
            return None
        sc = up.iloc[(up.delta - p2).abs().argsort()].iloc[0]; cost = px(lc.callValue, "buy", sp) - px(sc.callValue, "sell", sp); Kl = sc.strike
    else:
        cost = px(lc.callValue, "buy", sp)
    if cost <= 0:
        return None
    risk = cost * 100; Ks = lc.strike
    if exitd and exitd <= exp:
        ce = chains.get(exitd); v = None
        if ce is not None:
            a = ce[(ce.expirDate == exp) & (ce.strike == Ks)]
            if not a.empty:
                v = px(a.iloc[0].callValue, "sell", sp)
                if Kl is not None:
                    b = ce[(ce.expirDate == exp) & (ce.strike == Kl)]
                    v = v - px(b.iloc[0].callValue, "buy", sp) if not b.empty else v
        if v is None:
            S = close_by.get(exitd); v = (max(0, S-Ks)-(max(0, S-Kl) if Kl else 0)) if S else 0
        return (v - cost) * 100 - (4 if Kl else 2) * FEE, risk
    S = close_by.get(exp)
    if S is None:
        return None
    return (max(0, S-Ks)-(max(0, S-Kl) if Kl else 0) - cost) * 100 - (2 if Kl else 1) * FEE, risk


def run(eps, kind, p1, p2, sp):
    r = []
    for ep in eps:
        z = one(ep["entry"], ep["exit"], kind, p1, p2, sp)
        if z:
            r.append({"year": int(ep["entry"][:4]), "exit": ep["exit"] or ep["entry"], "pnl": z[0], "risk": z[1]})
    return pd.DataFrame(r)


def met(g):
    if g.empty:
        return {"n": 0}
    eq = g.sort_values("exit").pnl.cumsum()
    gp, gl = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
    return {"n": int(len(g)), "win": round((g.pnl > 0).mean()*100), "PF": round(gp/gl, 2) if gl else None,
            "avg": round(g.pnl.mean()), "roc": round(g.pnl.mean()/g.risk.mean()*100, 1), "tot": round(g.pnl.sum()),
            "maxDD": round((eq.cummax()-eq).max()), "maxRisk": round(g.risk.max())}


INSTR = {"BPS 30/10": ("bps", 0.70, 0.90), "BCS 50/30": ("bcs", 0.50, 0.30), "Call ATM": ("call", 0.50, None)}
out = {"meta": {"range": "2009-2026", "filter": "IBS<40 AND (body0>range0/2.7 OR body1>range1/2.5)"}, "variants": {}}
for vk, filt in [("unfiltered", False), ("filtered", True)]:
    base = episodes(15, 5, filt)
    V = {"n_signals": len(base), "fill": {}, "delta": {}, "exit": {}, "year": {}}
    for lbl, (k, p1, p2) in INSTR.items():
        V["fill"][lbl] = {fn: met(run(base, k, p1, p2, sp)) for fn, sp in FILLS.items()}
        V["delta"][lbl] = met(run(base, k, p1, p2, SP))
        V["exit"][lbl] = {f"SMA{x}": met(run(episodes(15, x, filt), k, p1, p2, SP)) for x in (3, 5, 8, 10)}
    runs = {lbl: run(base, *INSTR[lbl], SP) for lbl in INSTR}
    for y in range(2009, 2027):
        row = {lbl: {"n": int((g.year == y).sum()), "pnl": round(g[g.year == y].pnl.sum())} for lbl, g in runs.items() if (g.year == y).any()}
        if row:
            V["year"][str(y)] = row
    out["variants"][vk] = V
    print(f"{vk}: {len(base)} signals, BPS PF {V['delta']['BPS 30/10'].get('PF')}")


def _c(o):
    if isinstance(o, np.floating): return float(o)
    if isinstance(o, np.integer): return int(o)
    raise TypeError
(ROOT / "scratchpad" / "stmr_filtered_data.json").write_text(json.dumps(out, indent=1, default=_c))
print("wrote scratchpad/stmr_filtered_data.json")
