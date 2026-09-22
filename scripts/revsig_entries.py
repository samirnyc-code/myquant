"""Alternative entries on tick fills. retest=limit@LMT, cont=stop@signal-bar break,
mkt=at signal close. Stop = export stop (bar scale); target = entry +/- T*|entry-stop|.
BO and ALL, targets 1R/2R/EOD, TRAIN 21-23 / TEST 24-26. $50/pt, $17.5 RT.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF = 50.0, 17.5, 10 ** 9
TGTS = [1.0, 2.0, None]

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


def resolve(ex, entry, stop, long, T):
    risk = abs(entry - stop)
    if risk < 0.25: return None
    if long:
        sm = ex <= stop; tm = (ex >= entry + T * risk) if T else np.array([False])
    else:
        sm = ex >= stop; tm = (ex <= entry - T * risk) if T else np.array([False])
    si = int(np.argmax(sm)) if sm.any() else INF; ti = int(np.argmax(tm)) if (T and tm.any()) else INF
    px = ex[-1] if (si == INF and ti == INF) else (stop if si <= ti else (entry + T * risk if long else entry - T * risk))
    pts = (px - entry) if long else (entry - px)
    return pts * PT - RT


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
        lmt = s["lmt"] + sh; stop = s["stop"] + sh; long = s["long"]
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        sub = Pr[live:]
        rec = dict(date=date, yr=date[:4], rt=s["rt"], long=long, hh=s["hh"], train=date < "2024-01-01")
        # entries -> entry index & price
        ent = {}
        # retest: first touch of LMT
        fl = sub <= lmt if long else sub >= lmt
        if fl.any(): i = int(np.argmax(fl)); ent["retest"] = (i, lmt)
        # continuation: break of signal bar extreme in trade dir
        cm = sub >= shh if long else sub <= sll
        if cm.any(): i = int(np.argmax(cm)); ent["cont"] = (i, sub[i])
        # market: first tick after signal
        ent["mkt"] = (0, sub[0])
        for name, (i, entry) in ent.items():
            ex = sub[i:]
            for T in TGTS:
                rec[f"{name}_{T}"] = resolve(ex, entry, stop, long, T)
        rows.append(rec)

print(f"signals: {len(rows)}\n")


def agg(sub, key):
    us = [r[key] for r in sub if r.get(key) is not None]
    n = len(us)
    if n < 20: return None
    us = np.array(us); net = us.sum(); w = us[us > 0]; l = us[us <= 0]
    pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    return dict(n=n, net=round(net), exp=round(us.mean(), 1), pf=round(pf, 2),
                win=round(100 * len(w) / n), dd=round(dd), nd=round(net / dd, 2) if dd else 9.99)


def tl(T): return "EOD" if T is None else f"{int(T)}R"

for grp, fn in [("ALL", lambda r: True), ("BO", lambda r: r["rt"] == "BO"),
                ("BO skip-morning(>=11)", lambda r: r["rt"] == "BO" and r["hh"] >= 11)]:
    print(f"[{grp}]  (TRAIN | TEST  net$/PF/exp/n)")
    for ent in ("retest", "cont", "mkt"):
        for T in TGTS:
            k = f"{ent}_{T}"
            tr = agg([r for r in rows if r["train"] and fn(r)], k)
            te = agg([r for r in rows if not r["train"] and fn(r)], k)
            if tr and te:
                flag = "  <==" if tr["net"] > 0 and te["net"] > 0 else ""
                print(f"  {ent:<6} {tl(T):<3} TR ${tr['net']:>6,}/{tr['pf']:.2f}/{tr['exp']:>5}/n{tr['n']:<4} | "
                      f"TE ${te['net']:>6,}/{te['pf']:.2f}/{te['exp']:>5}/n{te['n']}{flag}")
    print()

print("BY-YEAR (BO skip-morning>=11) — net$/PF/n:")
BOskip = lambda r: r["rt"]=="BO" and r["hh"]>=11
for k in ["retest_1.0","mkt_1.0","mkt_2.0","cont_2.0"]:
    print(f"  [{k}]")
    for y in ["2021","2022","2023","2024","2025","2026"]:
        m = agg([r for r in rows if BOskip(r) and r["yr"]==y], k)
        if m: print(f"    {y}: ${m['net']:>6,} PF {m['pf']:>4.2f} exp {m['exp']:>5} n{m['n']}")
    full = agg([r for r in rows if BOskip(r)], k)
    if full: print(f"    ALL: ${full['net']:>6,} PF {full['pf']:>4.2f} exp {full['exp']} n{full['n']} nd{full['nd']}")

from datetime import date as _D
def fullm(sub, key):
    us = np.array([r[key] for r in sub if r.get(key) is not None]); n=len(us)
    if n<2: return None
    net=us.sum(); w=us[us>0]; l=us[us<=0]
    pf=w.sum()/-l.sum() if l.sum()<0 else 9.99
    eq=np.cumsum(us); dd=float((np.maximum.accumulate(eq)-eq).max())
    mcl=cl=0
    for x in us:
        cl=cl+1 if x<=0 else 0; mcl=max(mcl,cl)
    dts=sorted(r["date"] for r in sub if r.get(key) is not None)
    yrs=(_D.fromisoformat(dts[-1])-_D.fromisoformat(dts[0])).days/365.25 or 1
    sd=us.std(ddof=1); sh=us.mean()/sd if sd else 0
    return dict(n=n,net=round(net),yr=round(net/yrs),exp=round(us.mean(),1),pf=round(pf,2),
        win=round(100*len(w)/n,1),aw=round(w.mean(),1) if len(w) else 0,al=round(l.mean(),1) if len(l) else 0,
        payoff=round(w.mean()/-l.mean(),2) if len(l) and l.mean()<0 else 0,dd=round(dd),
        nd=round(net/dd,2) if dd else 9.99,shtr=round(sh,3),shann=round(sh*np.sqrt(n/yrs),2),
        mcl=mcl,best=round(us.max()),worst=round(us.min()))
def blk(name,sub,key):
    m=fullm(sub,key)
    if not m: print(f"\n{name}: n<2"); return
    print(f"\n=== {name} ===")
    print(f"  trades {m['n']}  net ${m['net']:,}  $/yr ${m['yr']:,}  exp/trade ${m['exp']}")
    print(f"  PF {m['pf']}  win% {m['win']}  avgWin ${m['aw']}  avgLoss ${m['al']}  payoff {m['payoff']}")
    print(f"  maxDD ${m['dd']:,}  net/DD {m['nd']}  Sharpe/tr {m['shtr']}  Sharpe ann {m['shann']}  maxConsecLoss {m['mcl']}")
    print(f"  best ${m['best']:,}  worst ${m['worst']:,}")
BOskip=lambda r: r["rt"]=="BO" and r["hh"]>=11
print("\n########## FULL METRICS ##########")
blk("BO skip-morning + MARKET + 2R", [r for r in rows if BOskip(r)], "mkt_2.0")
blk("BO skip-morning + retest + 1R", [r for r in rows if BOskip(r)], "retest_1.0")
blk("ALL types + MARKET + 2R", rows, "mkt_2.0")
