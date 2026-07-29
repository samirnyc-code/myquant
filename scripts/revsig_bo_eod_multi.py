"""BO>=11 market entry: 2R-vs-EOD conditional exits (when to let it run) + multi-signal-day analysis. Ticks."""
import glob
from pathlib import Path
import pandas as pd, numpy as np
from collections import defaultdict

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF = 50.0, 17.5, 10 ** 9

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {d: {int(k): (o, h, l, c) for k, o, h, l, c in zip(g.sort_values("bar")["bar"], g.Open, g.High, g.Low, g.Close)}
        for d, g in b5.groupby("Date")}
dl = b5.groupby("Date").agg(o=("Open", "first"), c=("Close", "last"), h=("High", "max"), l=("Low", "min")).reset_index()
dl["rng"] = dl.h - dl.l; dl["adr10"] = dl.rng.rolling(10).mean().shift(1); dl["sma20"] = dl.c.rolling(20).mean().shift(1); dl["pclose"] = dl.c.shift(1)
DF = dl.set_index("Date").to_dict("index"); ADRMED = dl.adr10.median()

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    if rt != "BO" or int(tm[:2]) < 11: continue
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}", ft=int(bn) - 1, btc=num(btc), stop=num(stop), hh=int(tm[:2])))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)

rows = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date); df = DF.get(date)
    if not tp.exists() or not bd or df is None or np.isnan(df["adr10"]): continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    day_sigs = sorted(byday[date], key=lambda s: s["ft"]); nsig = len(day_sigs)
    for nth, s in enumerate(day_sigs):
        ft = s["ft"]
        if ft not in bd: continue
        sc = bd[ft][3]; sh = sc - s["btc"]; stop = s["stop"] + sh; long = s["long"]
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        ex = Pr[live:]; entry = ex[0]; risk = abs(entry - stop)
        if risk < 0.25: continue
        si = int(np.argmax(ex <= stop)) if (ex <= stop).any() else INF if long else (int(np.argmax(ex >= stop)) if (ex >= stop).any() else INF)
        if long:
            stopm = ex <= stop; t2 = ex >= entry + 2 * risk
        else:
            stopm = ex >= stop; t2 = ex <= entry - 2 * risk
        si = int(np.argmax(stopm)) if stopm.any() else INF
        ti = int(np.argmax(t2)) if t2.any() else INF
        # 2R outcome
        if si == INF and ti == INF: px2 = ex[-1]
        elif si <= ti: px2 = stop
        else: px2 = entry + 2 * risk if long else entry - 2 * risk
        usd2 = ((px2 - entry) if long else (entry - px2)) * PT - RT
        # EOD outcome (stop stays, no target)
        pxe = stop if si != INF else ex[-1]
        usde = ((pxe - entry) if long else (entry - pxe)) * PT - RT
        # MFE up to (stop or EOD)
        end = si if si != INF else len(ex) - 1
        seg = ex[:end + 1]
        mfe = ((seg.max() - entry) if long else (entry - seg.min())) / risk
        gap = abs(df["o"] - df["pclose"]) / df["pclose"] * 100 if df["pclose"] else 0
        rows.append(dict(date=date, yr=date[:4], long=long, hh=s["hh"], usd2=usd2, usde=usde, mfe=mfe,
                         reached2=mfe >= 2, nth=nth, nsig=nsig,
                         with_sma=(not np.isnan(df["sma20"])) and (entry > df["sma20"]) == long,
                         hivol=df["adr10"] > ADRMED, nogap=gap < 0.3))

print(f"BO>=11 trades: {len(rows)}\n")


def agg(sub, key):
    us = np.array([r[key] for r in sub]); n = len(us)
    if n < 2: return None
    net = us.sum(); w = us[us > 0]; l = us[us <= 0]; pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = us.std(ddof=1); yrs = 5.0
    return dict(n=n, net=round(net), exp=round(us.mean(), 1), pf=round(pf, 2), win=round(100 * len(w) / n),
                dd=round(dd), nd=round(net / dd, 2) if dd else 9.99, sh=round((us.mean() / sd) * np.sqrt(n / yrs), 2) if sd else 0)


def cond(sub, use_eod_if):
    """conditional exit: EOD if predicate true else 2R"""
    us = np.array([(r["usde"] if use_eod_if(r) else r["usd2"]) for r in sub])
    net = us.sum(); w = us[us > 0]; l = us[us <= 0]; pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = us.std(ddof=1)
    return dict(n=len(us), net=round(net), pf=round(pf, 2), sh=round((us.mean() / sd) * np.sqrt(len(us) / 5), 2) if sd else 0, nd=round(net / dd, 2) if dd else 0)


print("=== PART 1: 2R vs EOD, and conditional (let it run when X) ===")
print(f"  pure 2R : {agg(rows,'usd2')}")
print(f"  pure EOD: {agg(rows,'usde')}")
print("  MFE: reached 2R in", round(100 * np.mean([r['reached2'] for r in rows])), "% ; among winners avg MFE",
      round(np.mean([r['mfe'] for r in rows if r['reached2']]), 2), "R")
print("  of trades that reached 2R, how far did they actually go (MFE R): "
      f"med {round(np.median([r['mfe'] for r in rows if r['reached2']]),1)}  "
      f">=3R {round(100*np.mean([r['mfe']>=3 for r in rows if r['reached2']]))}%  "
      f">=4R {round(100*np.mean([r['mfe']>=4 for r in rows if r['reached2']]))}%")
print("\n  conditional exit rules (EOD if cond, else 2R):")
for lab, fn in [("with-SMA20 (trend-aligned)", lambda r: r["with_sma"]), ("hi-vol day", lambda r: r["hivol"]),
                ("longs", lambda r: r["long"]), ("first signal of day", lambda r: r["nth"] == 0),
                ("with-SMA20 & hi-vol", lambda r: r["with_sma"] and r["hivol"]), ("never (=pure 2R)", lambda r: False),
                ("always (=pure EOD)", lambda r: True)]:
    print(f"    {lab:<28} {cond(rows, fn)}")

# by subgroup: is EOD>2R within trend-aligned trades?
print("\n  within-subgroup 2R vs EOD net$:")
for lab, fn in [("with-SMA20", lambda r: r["with_sma"]), ("against-SMA20", lambda r: not r["with_sma"]),
                ("hi-vol", lambda r: r["hivol"]), ("lo-vol", lambda r: not r["hivol"])]:
    sub = [r for r in rows if fn(r)]
    print(f"    {lab:<14} 2R {agg(sub,'usd2')['net']:>7,}  EOD {agg(sub,'usde')['net']:>7,}  (n{len(sub)})")

print("\n=== PART 2: multiple signals per day ===")
perday = defaultdict(int)
for r in rows: perday[r["date"]] = r["nsig"]
from collections import Counter
dist = Counter(v for v in perday.values())
print("  signals/day distribution:", dict(sorted(dist.items())))
print(f"  days with >=2 BO>=11 signals: {sum(1 for v in perday.values() if v>=2)} / {len(perday)}")
print("\n  performance by Nth-signal-of-day (2R):")
for k in [0, 1, 2]:
    sub = [r for r in rows if r["nth"] == k]
    m = agg(sub, "usd2")
    if m: print(f"    signal #{k+1}: net ${m['net']:>7,} PF {m['pf']:.2f} exp ${m['exp']} n{m['n']}")
sub3 = [r for r in rows if r["nth"] >= 3]
if sub3: print(f"    signal #4+: net ${agg(sub3,'usd2')['net']:,} PF {agg(sub3,'usd2')['pf']} n{len(sub3)}")
print("\n  cap to FIRST-signal-per-day vs ALL (2R):")
print(f"    first only : {agg([r for r in rows if r['nth']==0],'usd2')}")
print(f"    all        : {agg(rows,'usd2')}")
# same-day clustering: correlation of outcomes on multi-signal days
multi = defaultdict(list)
for r in rows:
    if r["nsig"] >= 2: multi[r["date"]].append(1 if r["usd2"] > 0 else 0)
same = [1 if len(set(v)) == 1 else 0 for v in multi.values() if len(v) >= 2]
print(f"\n  multi-signal days where ALL same outcome (all win or all lose): {round(100*np.mean(same))}%  (n{len(same)} days) -> clustering risk")

print("\n=== CONDITIONAL WINNER: EOD if AGAINST-SMA20 (counter-trend), else 2R ===")
def condfull(sub, use_eod_if, byyear=False):
    us = np.array([(r["usde"] if use_eod_if(r) else r["usd2"]) for r in sub])
    net=us.sum(); w=us[us>0]; l=us[us<=0]; pf=w.sum()/-l.sum() if l.sum()<0 else 9.99
    eq=np.cumsum(us); dd=float((np.maximum.accumulate(eq)-eq).max()); sd=us.std(ddof=1)
    m=dict(n=len(us),net=round(net),exp=round(us.mean(),1),pf=round(pf,2),win=round(100*len(w)/len(us)),
           dd=round(dd),nd=round(net/dd,2) if dd else 0,sh=round((us.mean()/sd)*np.sqrt(len(us)/5),2) if sd else 0,aw=round(w.mean()) if len(w) else 0,al=round(l.mean()) if len(l) else 0)
    return m
rule = lambda r: not r["with_sma"]
m = condfull(rows, rule)
print(f"  ALL: net ${m['net']:,} $/yr ${round(m['net']/5):,} exp ${m['exp']} PF {m['pf']} win{m['win']}% DD ${m['dd']:,} nd {m['nd']} Sharpe {m['sh']} avgW ${m['aw']} avgL ${m['al']}")
print("  by year:", "  ".join(f"{y[2:]}:${condfull([r for r in rows if r['yr']==y],rule)['net']:>5,}" for y in ["2021","2022","2023","2024","2025","2026"]))
print("  vs pure 2R net $31,672 (Sh 0.75) / pure EOD $36,348 (Sh 0.55)")
# add skip-gap on top
rg = lambda r: not r["with_sma"]
sub = [r for r in rows if r["nogap"]]
m2 = condfull(sub, rg)
print(f"\n  + skip-gap: net ${m2['net']:,} exp ${m2['exp']} PF {m2['pf']} DD ${m2['dd']:,} nd {m2['nd']} Sharpe {m2['sh']} n{m2['n']}")
print("  by year:", "  ".join(f"{y[2:]}:${condfull([r for r in sub if r['yr']==y],rg)['net']:>5,}" for y in ["2021","2022","2023","2024","2025","2026"]))
