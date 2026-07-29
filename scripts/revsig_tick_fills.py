"""REAL-TICK fill engine for the MyReversals export. No 5M phantom fills.

Ticks: data/ticks_continuous/{date}.parquet (NT ticks, RTH, cols DateTime/Price/Volume),
same continuous scale as es_5m_rth. Each signal anchored to bars via its BTC (shift).

Fill model (a fill needs a real tick AT/through the level, resolved in time order):
  LONG  (buy-limit LMT below signal close): away when a tick > signal-bar high; then FILL
        when a tick <= LMT; exit whichever comes first in tick order: tick<=stop or tick>=target.
  SHORT: mirror.  away_depth = (extreme reached before fill - LMT)/risk.
Reports: tick vs 5M (phantom check), bars-to-fill dist, order-expiry sweep (pull after N bars),
and the $ given up by filtering to away>=1R / >=1.5R.  1 ES, $50/pt, $17.5 RT.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(r"c:\Users\Admin\myquant")
TICKS = ROOT / "data" / "ticks_continuous"
PT, RT, T = 50.0, 17.5, 1.0

# 5M bars for signal-bar OHLC + shift anchor
b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BAR = {}
for d, g in b5.groupby("Date"):
    g = g.sort_values("bar")
    BAR[d] = {int(k): (o, h, l, c) for k, o, h, l, c in zip(g["bar"], g.Open, g.High, g.Low, g.Close)}

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt)))
byday = {}
for s in sigs:
    byday.setdefault(s["date"], []).append(s)

INF = 10 ** 9
res = []           # per trade dicts
nofill = 0; noticks = 0
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"
    bars = BAR.get(date)
    if not tp.exists() or not bars:
        noticks += len(byday[date]); continue
    t = pd.read_parquet(tp)
    P = t["Price"].to_numpy(float)
    mins = t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy()
    B = (mins - 510) // 5                       # 5M bar index of each tick (08:30 -> 0)
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bars: continue
        so, shh, sll, sc = bars[ft]
        sh = sc - s["btc"]
        lmt = s["lmt"] + sh; stop = s["stop"] + sh; long = s["long"]
        risk = abs(lmt - stop)
        if risk < 0.25: continue
        live = int(np.searchsorted(B, ft + 1))   # first tick at/after signal-bar close
        if live >= len(P): nofill += 1; continue
        sub = P[live:]; subB = B[live:]
        if long:
            aw = sub > shh
            if not aw.any(): nofill += 1; continue
            a = int(np.argmax(aw))
            after = sub[a:]; fl = after <= lmt
            if not fl.any(): nofill += 1; continue
            fi = a + int(np.argmax(fl))
            away_depth = (sub[:fi + 1].max() - lmt) / risk
            ex = sub[fi:]
            sm = ex <= stop; tm = ex >= (lmt + T * risk)
            si = int(np.argmax(sm)) if sm.any() else INF
            ti = int(np.argmax(tm)) if tm.any() else INF
        else:
            aw = sub < sll
            if not aw.any(): nofill += 1; continue
            a = int(np.argmax(aw))
            after = sub[a:]; fl = after >= lmt
            if not fl.any(): nofill += 1; continue
            fi = a + int(np.argmax(fl))
            away_depth = (lmt - sub[:fi + 1].min()) / risk
            ex = sub[fi:]
            sm = ex >= stop; tm = ex <= (lmt - T * risk)
            si = int(np.argmax(sm)) if sm.any() else INF
            ti = int(np.argmax(tm)) if tm.any() else INF
        if si == INF and ti == INF:
            expx = sub[-1]                        # EOD
        elif si <= ti:
            expx = stop
        else:
            expx = lmt + T * risk if long else lmt - T * risk
        pts = (expx - lmt) if long else (lmt - expx)
        btf = int(subB[fi]) - ft
        res.append(dict(date=date, long=long, rt=s["rt"], usd=pts * PT - RT,
                        away=away_depth, btf=max(btf, 0)))

print(f"signals filled on ticks: {len(res)}   (no-fill {nofill}, no-ticks {noticks})\n")


def M(sub):
    n = len(sub)
    if n == 0: return None
    us = [r["usd"] for r in sub]; net = sum(us)
    w = [x for x in us if x > 0]; ls = [x for x in us if x <= 0]
    pf = sum(w) / (-sum(ls)) if ls and sum(ls) < 0 else 9.99
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(w) / n), dd=round(dd),
                nd=(round(net / dd, 2) if dd else 9.99))


def P(lab, sub):
    m = M(sub)
    print(f"  {lab:<26} n={m['n']:<4} net=${m['net']:>8,} PF {m['pf']:>4.2f} win {m['win']}% "
          f"DD ${m['dd']:>7,} nd {m['nd']}" if m else f"  {lab}: none")

print("REAL-TICK results:")
P("ALL fills", res)
P("away>=1R", [r for r in res if r["away"] >= 1.0])
P("away>=1.5R", [r for r in res if r["away"] >= 1.5])
P("away<1R (excluded set)", [r for r in res if r["away"] < 1.0])
P("away 1.0-1.5R (excluded by 1.5)", [r for r in res if 1.0 <= r["away"] < 1.5])

print("\nPnL GIVEN UP by filtering (these trades are DROPPED):")
d1 = M([r for r in res if r["away"] < 1.0]); a1 = M([r for r in res if r["away"] >= 1.0])
d15 = M([r for r in res if r["away"] < 1.5]); a15 = M([r for r in res if r["away"] >= 1.5])
print(f"  filter away>=1R  : keep n{a1['n']} ${a1['net']:,} ; DROP n{d1['n']} net ${d1['net']:,}  "
      f"(drop PF {d1['pf']}) -> giving up ${max(d1['net'],0):,} of profit, cutting ${-min(d1['net'],0):,} of loss")
print(f"  filter away>=1.5R: keep n{a15['n']} ${a15['net']:,} ; DROP n{d15['n']} net ${d15['net']:,}")

print("\nBARS-TO-FILL distribution (tick fills):")
btf = [r["btf"] for r in res]
for lab, lo, hi in [("0-1", 0, 1), ("2-3", 2, 3), ("4-5", 4, 5), ("6-10", 6, 10), ("11-20", 11, 20), (">20", 21, 999)]:
    sub = [r for r in res if lo <= r["btf"] <= hi]
    m = M(sub)
    print(f"  {lab:<6} n={m['n']:<4} net=${m['net']:>8,} PF {m['pf']:>4.2f}  (share {100*m['n']//len(res)}%)" if m else f"  {lab}: 0")

print("\nORDER-EXPIRY sweep (pull limit if not filled within N bars) -> keep btf<=N:")
print("  N     ALL fills            away>=1R")
for N in [1, 2, 3, 4, 5, 8, 12, 999]:
    allm = M([r for r in res if r["btf"] <= N])
    awm = M([r for r in res if r["btf"] <= N and r["away"] >= 1.0])
    lab = "none" if N == 999 else str(N)
    print(f"  {lab:<4}  ${allm['net']:>8,}/PF{allm['pf']:.2f}/n{allm['n']:<4}   "
          f"${awm['net']:>8,}/PF{awm['pf']:.2f}/n{awm['n']}" if allm and awm else f"  {lab}")
