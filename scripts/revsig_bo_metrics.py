"""Full PnL metrics for the BO tick configs. 1 ES, $50/pt, $17.5 RT, touch-limit entry."""
import glob
from pathlib import Path
import pandas as pd, numpy as np
from datetime import date as D

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF = 50.0, 17.5, 10 ** 9

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

def fill(sub, lmt, stop, risk, long, T):
    fl = sub <= lmt if long else sub >= lmt
    if not fl.any(): return None
    fi = int(np.argmax(fl)); ex = sub[fi:]
    if long:
        sm = ex <= stop; tm = (ex >= lmt + T * risk) if T else np.array([False])
    else:
        sm = ex >= stop; tm = (ex <= lmt - T * risk) if T else np.array([False])
    si = int(np.argmax(sm)) if sm.any() else INF; ti = int(np.argmax(tm)) if (T and tm.any()) else INF
    px = ex[-1] if (si == INF and ti == INF) else (stop if si <= ti else (lmt + T * risk if long else lmt - T * risk))
    pts = (px - lmt) if long else (lmt - px)
    return pts * PT - RT

rows = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date)
    if not tp.exists() or not bd: continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    Bmin = t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy()
    B = (Bmin - 510) // 5
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bd: continue
        so, shh, sll, sc = bd[ft]; sh = sc - s["btc"]
        lmt = s["lmt"] + sh; stop = s["stop"] + sh; long = s["long"]; risk = abs(lmt - stop)
        if risk < 0.25: continue
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        sub = Pr[live:]
        r1 = fill(sub, lmt, stop, risk, long, 1.0)
        re = fill(sub, lmt, stop, risk, long, None)
        if r1 is None: continue
        rows.append(dict(date=date, rt=s["rt"], long=long, hh=s["hh"], usd1=r1, usde=re, risk=risk))

def full(sub, key):
    us = np.array([r[key] for r in sub if r[key] is not None])
    n = len(us)
    if n < 2: return None
    net = us.sum(); w = us[us > 0]; l = us[us <= 0]
    pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    # max consecutive losers
    mcl = cl = 0
    for x in us:
        cl = cl + 1 if x <= 0 else 0; mcl = max(mcl, cl)
    dts = sorted(r["date"] for r in sub if r[key] is not None)
    yrs = (D.fromisoformat(dts[-1]) - D.fromisoformat(dts[0])).days / 365.25 or 1
    sh = us.mean() / us.std(ddof=1) if us.std(ddof=1) else 0
    return dict(n=n, net=round(net), exp=round(us.mean(), 1), pf=round(pf, 2),
                win=round(100 * len(w) / n, 1), aw=round(w.mean(), 1) if len(w) else 0,
                al=round(l.mean(), 1) if len(l) else 0,
                payoff=round(w.mean() / -l.mean(), 2) if len(l) and l.mean() < 0 else 0,
                dd=round(dd), nd=round(net / dd, 2) if dd else 9.99,
                sh_tr=round(sh, 3), sh_ann=round(sh * np.sqrt(n / yrs), 2),
                mcl=mcl, best=round(us.max()), worst=round(us.min()), yr=round(net / yrs))

def block(name, sub, key):
    m = full(sub, key)
    if not m: print(f"\n{name}: n<2"); return
    print(f"\n=== {name}  (1 ES, ${PT:.0f}/pt, ${RT} RT) ===")
    print(f"  trades {m['n']}    net ${m['net']:,}    $/yr ${m['yr']:,}    exp $/trade {m['exp']}")
    print(f"  PF {m['pf']}    win% {m['win']}    avgWin ${m['aw']}   avgLoss ${m['al']}   payoff {m['payoff']}")
    print(f"  maxDD ${m['dd']:,}   net/DD {m['nd']}   Sharpe/trade {m['sh_tr']}   Sharpe ann {m['sh_ann']}")
    print(f"  maxConsecLoss {m['mcl']}   best ${m['best']:,}   worst ${m['worst']:,}")

BO = lambda r: r["rt"] == "BO"
block("BO + skip-morning(>=11) + 1R", [r for r in rows if BO(r) and r["hh"] >= 11], "usd1")
block("BO + midday(11-13) + 1R", [r for r in rows if BO(r) and 11 <= r["hh"] < 13], "usd1")
block("BO + skip-morning + EOD hold", [r for r in rows if BO(r) and r["hh"] >= 11], "usde")
block("ALL types + 1R (reference)", rows, "usd1")
block("BO all-day + 1R (reference)", [r for r in rows if BO(r)], "usd1")

# scaling note
m = full([r for r in rows if BO(r) and r["hh"] >= 11], "usd1")
if m:
    print(f"\nScaling (linear): {m['yr']:,}/yr per 1 ES  ->  3 ES ${m['yr']*3:,}/yr, 10 ES ${m['yr']*10:,}/yr "
          f"(MES = 1/10: ${round(m['yr']/10):,}/yr but $5 RT not $17.5 -> better net)")
