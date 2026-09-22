"""Drill the BO lead on REAL ticks. Two entry models (true-limit first-touch vs
away-then-touch), target sweep, by-year, by-time, by-dir, OOS split. $50/pt, $17.5 RT.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF = 50.0, 17.5, 10 ** 9
TARGETS = [1.0, 1.5, 2.0, 3.0, None]   # None = EOD hold

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {d: {int(k): (o, h, l, c) for k, o, h, l, c in zip(g.sort_values("bar")["bar"], g.Open, g.High, g.Low, g.Close)}
        for d, g in b5.groupby("Date")}

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt), hh=int(tm[:2])))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)


def exits(ex, lmt, stop, risk, long, T):
    if long:
        sm = ex <= stop; tm = ex >= lmt + T * risk if T else None
    else:
        sm = ex >= stop; tm = ex <= lmt - T * risk if T else None
    si = int(np.argmax(sm)) if sm.any() else INF
    ti = (int(np.argmax(tm)) if tm.any() else INF) if T else INF
    if si == INF and ti == INF: return ex[-1]
    if si <= ti: return stop
    return (lmt + T * risk) if long else (lmt - T * risk)


rows = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date)
    if not tp.exists() or not bd: continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bd: continue
        so, shh, sll, sc = bd[ft]; sh = sc - s["btc"]
        lmt = s["lmt"] + sh; stop = s["stop"] + sh; long = s["long"]; risk = abs(lmt - stop)
        if risk < 0.25: continue
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        sub = Pr[live:]; subB = B[live:]
        rec = dict(date=date, yr=date[:4], rt=s["rt"], long=long, hh=s["hh"], train=date < "2024-01-01")
        for model in ("touch", "away"):
            if model == "touch":
                fl = sub <= lmt if long else sub >= lmt
                if not fl.any(): rec[model] = None; continue
                fi = int(np.argmax(fl))
            else:
                aw = sub > shh if long else sub < sll
                if not aw.any(): rec[model] = None; continue
                a = int(np.argmax(aw)); after = sub[a:]
                fl = after <= lmt if long else after >= lmt
                if not fl.any(): rec[model] = None; continue
                fi = a + int(np.argmax(fl))
            ex = sub[fi:]
            rec[model] = {T: (( (exits(ex, lmt, stop, risk, long, T) - lmt) if long
                               else (lmt - exits(ex, lmt, stop, risk, long, T))) * PT - RT) for T in TARGETS}
            rec[model + "_btf"] = max(int(subB[fi]) - ft, 0)
        rows.append(rec)

print(f"signals: {len(rows)}\n")


def agg(sub, model, T):
    us = [r[model][T] for r in sub if r.get(model)]
    n = len(us)
    if not n: return None
    net = sum(us); w = [x for x in us if x > 0]; ls = [x for x in us if x <= 0]
    pf = sum(w) / (-sum(ls)) if ls and sum(ls) < 0 else 9.99
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(w) / n), nd=(round(net / dd, 2) if dd else 9.99))


def tl(T): return "EOD" if T is None else f"{T}R"

print("ENTRY MODEL x TARGET  (ALL types, then BO) — TRAIN | TEST net$/PF")
for grp, filt in [("ALL", lambda r: True), ("BO", lambda r: r["rt"] == "BO")]:
    print(f" [{grp}]")
    for model in ("touch", "away"):
        for T in TARGETS:
            tr = agg([r for r in rows if r["train"] and filt(r)], model, T)
            te = agg([r for r in rows if not r["train"] and filt(r)], model, T)
            if tr and te:
                print(f"   {model:<5} {tl(T):<4} TR ${tr['net']:>7,}/PF{tr['pf']:.2f}/n{tr['n']:<4} | "
                      f"TE ${te['net']:>7,}/PF{te['pf']:.2f}/n{te['n']}" + ("  <==" if te['net'] > 0 and tr['net'] > 0 else ""))
    print()

print("BO by YEAR (touch entry):")
for T in [1.0, 2.0, None]:
    print(f"  target {tl(T)}:")
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        m = agg([r for r in rows if r["rt"] == "BO" and r["yr"] == y], "touch", T)
        if m: print(f"    {y}: net ${m['net']:>7,} PF {m['pf']:>4.2f} win {m['win']}% n{m['n']}")

print("\nBO x TIME x DIR (touch, 1R & EOD), TRAIN|TEST:")
for lab, fn in [("morning<11", lambda r: r["hh"] < 11), ("midday11-13", lambda r: 11 <= r["hh"] < 13),
                ("pm>=13", lambda r: r["hh"] >= 13), ("longs", lambda r: r["long"]), ("shorts", lambda r: not r["long"]),
                ("skip morning", lambda r: r["hh"] >= 11)]:
    for T in [1.0, None]:
        tr = agg([r for r in rows if r["train"] and r["rt"] == "BO" and fn(r)], "touch", T)
        te = agg([r for r in rows if not r["train"] and r["rt"] == "BO" and fn(r)], "touch", T)
        if tr and te and tr["n"] > 30:
            print(f"  BO {lab:<13} {tl(T):<4} TR ${tr['net']:>6,}/PF{tr['pf']:.2f}/n{tr['n']:<3} | "
                  f"TE ${te['net']:>6,}/PF{te['pf']:.2f}/n{te['n']}" + ("  <==" if te['net'] > 0 and tr['net'] > 0 else ""))

print("\nCONSISTENCY CHECK - by YEAR (touch, 1R):")
for lab, fn in [("BO skip-morning(>=11)", lambda r: r["rt"]=="BO" and r["hh"]>=11),
                ("BO midday(11-13)", lambda r: r["rt"]=="BO" and 11<=r["hh"]<13),
                ("BO pm(>=13)", lambda r: r["rt"]=="BO" and r["hh"]>=13)]:
    print(f"  [{lab}]")
    for y in ["2021","2022","2023","2024","2025","2026"]:
        m = agg([r for r in rows if fn(r) and r["yr"]==y], "touch", 1.0)
        if m: print(f"    {y}: net ${m['net']:>6,} PF {m['pf']:>4.2f} win {m['win']}% n{m['n']}")
    full = agg([r for r in rows if fn(r)], "touch", 1.0)
    if full: print(f"    ALL: net ${full['net']:>6,} PF {full['pf']:>4.2f} win {full['win']}% n{full['n']} nd {full['nd']}")
