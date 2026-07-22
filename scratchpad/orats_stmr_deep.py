"""STMR deep-dive on SPX ORATS 2007-2026 (close entry, one-at-a-time).
Transposed tables (instruments across), exit & delta sweeps, per-year breakdowns,
risk metrics (maxDD / max single risk / max concurrent collateral), and a
double-down study (average into further weakness vs add on the bounce).
Fill=MID (optimistic; worst for the sold BPS). Fees $1.30/ct/side.
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant"); ORATS = ROOT / "data" / "orats" / "SPX"
DTE_T, FEE = 14, 1.30

d = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
d["Date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")
d = d[(d.Date >= "2007-01-01") & (d.Date <= "2026-12-31")].reset_index(drop=True)
C, H, L = d.Close, d.High, d.Low
d["sma100"] = C.rolling(100).mean()
for n in (3, 5, 8, 10):
    d[f"sma{n}"] = C.rolling(n).mean()
d["k8"] = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
close_by = dict(zip(d.Date, d.Close))
k8_by = dict(zip(d.Date, d.k8))
idx_by = {dt_: i for i, dt_ in enumerate(d.Date)}


def episodes(oversold, exsma):
    ent = (d.k8 < oversold) & (C > d.sma100) & d.k8.notna() & d.sma100.notna()
    exi = C > d[f"sma{exsma}"]
    out, inpos, cur = [], False, None
    for i in range(len(d)):
        if not inpos and ent.iloc[i]:
            cur = {"entry": d.Date.iloc[i], "mid": []}; inpos = True
        elif inpos:
            if exi.iloc[i]:
                cur["exit"] = d.Date.iloc[i]; out.append(cur); inpos = False
            else:
                cur["mid"].append(d.Date.iloc[i])
    if inpos:
        cur["exit"] = None; out.append(cur)
    return out


# ---- load chains for every date any test touches (entries, mids, exits) ----
need = set()
for ov in (10, 15, 20, 25):
    for ex in (3, 5, 8, 10):
        for e in episodes(ov, ex):
            need.add(e["entry"])
            if e["exit"]:
                need.add(e["exit"])
            need.update(e["mid"])
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
print(f"loaded {len(chains)} chain-days")


def _exp(ch):
    return None if ch.empty else ch.iloc[(ch.dte - DTE_T).abs().argsort()].iloc[0].expirDate


def one(entry, exitd, kind, p1, p2=None):
    """Return (pnl, risk$) for one unit opened at `entry`, closed at `exitd` (or expiry).
    kind: 'bps'(short p1/long p2 put-delta) | 'call'(delta p1) | 'bcs'(long p1/short p2 call-delta)."""
    ch = chains.get(entry)
    if ch is None:
        return None
    exp = _exp(ch)
    if exp is None:
        return None
    if kind == "bps":
        e = ch[(ch.expirDate == exp) & ch.putValue.notna() & (ch.putValue > 0)]
        if len(e) < 2:
            return None
        s = e.iloc[(e.delta - p1).abs().argsort()].iloc[0]
        below = e[e.strike < s.strike]
        if below.empty:
            return None
        lo = below.iloc[(below.delta - p2).abs().argsort()].iloc[0]
        cr = s.putValue - lo.putValue
        if cr <= 0:
            return None
        risk = (s.strike - lo.strike - cr) * 100
        cd = exitd if (exitd and exitd <= exp) else None
        if cd:
            ce = chains.get(cd); v = None
            if ce is not None:
                a = ce[(ce.expirDate == exp) & (ce.strike == s.strike)]
                b = ce[(ce.expirDate == exp) & (ce.strike == lo.strike)]
                if not a.empty and not b.empty:
                    v = a.iloc[0].putValue - b.iloc[0].putValue
            if v is None:
                S = close_by.get(cd); v = (max(0, s.strike-S)-max(0, lo.strike-S)) if S else cr
            return (cr - v) * 100 - 4 * FEE, risk
        S = close_by.get(exp)
        if S is None:
            return None
        return (cr - (max(0, s.strike-S)-max(0, lo.strike-S))) * 100 - 2 * FEE, risk
    # call / bcs
    e = ch[(ch.expirDate == exp) & ch.callValue.notna() & (ch.callValue > 0)]
    if e.empty:
        return None
    lc = e.iloc[(e.delta - p1).abs().argsort()].iloc[0]
    Kl = None
    if kind == "bcs":
        up = e[e.strike > lc.strike]
        if up.empty:
            return None
        sc = up.iloc[(up.delta - p2).abs().argsort()].iloc[0]
        cost = lc.callValue - sc.callValue; Kl = sc.strike
    else:
        cost = lc.callValue
    if cost <= 0:
        return None
    risk = cost * 100
    Ks = lc.strike
    cd = exitd if (exitd and exitd <= exp) else None
    if cd:
        ce = chains.get(cd); v = None
        if ce is not None:
            a = ce[(ce.expirDate == exp) & (ce.strike == Ks)]
            if not a.empty:
                v = a.iloc[0].callValue
                if Kl is not None:
                    b = ce[(ce.expirDate == exp) & (ce.strike == Kl)]
                    v = (v - b.iloc[0].callValue) if not b.empty else v
        if v is None:
            S = close_by.get(cd); v = (max(0, S-Ks)-(max(0, S-Kl) if Kl else 0)) if S else 0
        return (v - cost) * 100 - (4 if Kl else 2) * FEE, risk
    S = close_by.get(exp)
    if S is None:
        return None
    pay = max(0, S-Ks) - (max(0, S-Kl) if Kl else 0)
    return (pay - cost) * 100 - (2 if Kl else 1) * FEE, risk


INSTR = {  # label -> (kind, p1, p2)
    "BPS 30/10": ("bps", 0.70, 0.90), "BPS 40/15": ("bps", 0.60, 0.85),
    "BCS 50/30": ("bcs", 0.50, 0.30), "Call ATM": ("call", 0.50, None), "Call ITM": ("call", 0.65, None),
}


def run(eps, kind, p1, p2):
    rows = []
    for ep in eps:
        r = one(ep["entry"], ep["exit"], kind, p1, p2)
        if r:
            rows.append({"entry": ep["entry"], "exit": ep["exit"] or ep["entry"],
                         "year": int(ep["entry"][:4]), "pnl": r[0], "risk": r[1]})
    return pd.DataFrame(rows)


def metrics(g):
    if g.empty:
        return dict(n=0)
    eq = g.sort_values("exit").pnl.cumsum()
    gp, gl = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
    return dict(n=len(g), win=round((g.pnl > 0).mean()*100), PF=round(gp/gl, 2) if gl else np.inf,
                avg=round(g.pnl.mean()), roc=round(g.pnl.mean()/g.risk.mean()*100, 1),
                tot=round(g.pnl.sum()), maxDD=round((eq.cummax()-eq).max()),
                maxRisk=round(g.risk.max()), medRisk=round(g.risk.median()))


def tbl(colmap, rowkeys, title):
    print(f"\n{title}")
    labels = list(colmap)
    print(f"  {'metric':10s}| " + " | ".join(f"{l:>10s}" for l in labels))
    print("  " + "-"*(11 + 13*len(labels)))
    names = {"n": "n trades", "win": "win %", "PF": "PF", "avg": "avg $/tr",
             "roc": "RoC/tr %", "tot": "total $", "maxDD": "max DD $",
             "maxRisk": "maxRisk $", "medRisk": "medRisk $"}
    for rk in rowkeys:
        print(f"  {names[rk]:10s}| " + " | ".join(f"{colmap[l].get(rk, ''):>10}" for l in labels))


# ===== DELTA SWEEP (K8<15, exitSMA5) — instruments across =====
base = episodes(15, 5)
cm = {lbl: metrics(run(base, *spec)) for lbl, spec in INSTR.items()}
tbl(cm, ["n", "win", "PF", "avg", "roc", "tot", "maxDD", "maxRisk", "medRisk"],
    "="*70 + "\nDELTA / INSTRUMENT SWEEP  (signal K8<15, exit SMA5)\n" + "="*70)

# ===== EXIT SWEEP — for each core instrument, exitSMA across =====
for lbl in ["BPS 30/10", "BCS 50/30", "Call ATM"]:
    kind, p1, p2 = INSTR[lbl]
    cm = {f"exitSMA{e}": metrics(run(episodes(15, e), kind, p1, p2)) for e in (3, 5, 8, 10)}
    tbl(cm, ["n", "win", "PF", "avg", "roc", "tot", "maxDD"],
        "="*70 + f"\nEXIT SWEEP — {lbl}  (signal K8<15)\n" + "="*70)

# ===== PER-YEAR (base signal, 3 instruments) =====
print("\n" + "="*70 + "\nPER-YEAR  (K8<15, exitSMA5)  n | P&L$ per instrument\n" + "="*70)
runs = {lbl: run(base, *INSTR[lbl]) for lbl in ["BPS 30/10", "BCS 50/30", "Call ATM"]}
print(f"  {'year':6s}" + "".join(f"| {l:>18s}" for l in runs))
for y in range(2007, 2027):
    cells = []
    for lbl, g in runs.items():
        gy = g[g.year == y]
        cells.append(f"{len(gy):2d}  ${gy.pnl.sum():>9,.0f}" if len(gy) else f"{'-':>13}")
    print(f"  {y:<6d}" + "".join(f"| {c:>18s}" for c in cells))

# ===== DOUBLE-DOWN STUDY (BPS 30/10, base signal) =====
print("\n" + "="*70 + "\nDOUBLE-DOWN — BPS 30/10, K8<15, exit SMA5 (cap 3 units/episode)\n" + "="*70)


def dd_run(eps, mode):
    """mode: 'base'|'weak'(add on more-oversold day)|'strong'(add on bounce day)."""
    units, peak_coll = [], 0.0
    for ep in eps:
        entry, exitd = ep["entry"], ep["exit"]
        adds = [entry]
        if mode != "base":
            e0 = close_by[entry]; prev = e0
            for m in ep["mid"]:
                cm_ = close_by.get(m); k = k8_by.get(m)
                if cm_ is None:
                    continue
                if mode == "weak" and cm_ < prev and k is not None and k < 15 and len(adds) < 3:
                    adds.append(m); prev = cm_
                if mode == "strong" and cm_ > e0 and len(adds) < 3:
                    adds.append(m)
        ep_units, ep_coll = [], 0.0
        for a in adds:
            r = one(a, exitd, "bps", 0.70, 0.90)
            if r:
                ep_units.append({"exit": exitd or a, "pnl": r[0], "risk": r[1]})
                ep_coll += r[1]
        units += ep_units
        peak_coll = max(peak_coll, ep_coll)   # all units in an episode overlap near exit
    g = pd.DataFrame(units)
    m = metrics(g.rename(columns={}))
    m["maxConcColl"] = round(peak_coll)
    m["episodes"] = len(eps)
    return m


ddm = {"baseline (1x)": dd_run(base, "base"),
       "add on WEAKNESS": dd_run(base, "weak"),
       "add on BOUNCE": dd_run(base, "strong")}
tbl(ddm, ["n", "win", "PF", "avg", "tot", "maxDD", "maxRisk"], "double-down variants:")
print("  " + "-"*50)
for k, m in ddm.items():
    print(f"  {k:18s}: max CONCURRENT collateral ${m['maxConcColl']:,} "
          f"(single-trade maxRisk ${m['maxRisk']:,})")
print("\nFILL=MID (optimistic, esp. sold BPS). maxRisk=largest single-unit capital-at-risk;")
print("maxConcColl=peak simultaneous collateral within one episode (what a broker holds).")
