"""BO market-entry 2R on ticks: TOD sweep + recheck all filters + skip-days, full metrics + by-year."""
import glob
from pathlib import Path
import pandas as pd, numpy as np
from datetime import date as _D

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF, T = 50.0, 17.5, 10 ** 9, 2.0

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {}
for d, g in b5.groupby("Date"):
    g = g.sort_values("bar")
    BARS[d] = dict(bar=g["bar"].astype(int).values, H=g.High.values, L=g.Low.values, C=g.Close.values, V=g.Volume.values,
                   arr={int(k): (o, h, l, c) for k, o, h, l, c in zip(g["bar"], g.Open, g.High, g.Low, g.Close)})
dl = b5.groupby("Date").agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"), c=("Close", "last")).reset_index()
dl["rng"] = dl.h - dl.l; dl["adr10"] = dl.rng.rolling(10).mean().shift(1); dl["sma20"] = dl.c.rolling(20).mean().shift(1)
dl["prng"] = dl.rng.shift(1); dl["pclose"] = dl.c.shift(1); dl["dow"] = pd.to_datetime(dl.Date).dt.dayofweek
DF = dl.set_index("Date").to_dict("index"); ADRMED = dl.adr10.median()

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    if rt != "BO": continue
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}", ft=int(bn) - 1,
                     btc=num(btc), stop=num(stop), hh=int(tm[:2])))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)


def ema(a, span):
    k = 2 / (span + 1); e = a[0]
    for x in a[1:]: e = k * x + (1 - k) * e
    return e


rows = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date); df = DF.get(date)
    if not tp.exists() or not bd or df is None or np.isnan(df["adr10"]): continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bd["arr"]: continue
        sc = bd["arr"][ft][3]; sh = sc - s["btc"]; stop = s["stop"] + sh; long = s["long"]
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        ex = Pr[live:]; entry = ex[0]; risk = abs(entry - stop)
        if risk < 0.25: continue
        if long:
            sm = ex <= stop; tm = ex >= entry + T * risk
        else:
            sm = ex >= stop; tm = ex <= entry - T * risk
        si = int(np.argmax(sm)) if sm.any() else INF; ti = int(np.argmax(tm)) if tm.any() else INF
        px = ex[-1] if (si == INF and ti == INF) else (stop if si <= ti else (entry + T * risk if long else entry - T * risk))
        usd = ((px - entry) if long else (entry - px)) * PT - RT
        # features
        idx = bd["bar"] <= ft; C = bd["C"][idx]; H = bd["H"][idx]; L = bd["L"][idx]; V = bd["V"][idx]
        if len(C) < 3: continue
        vwap = float(((H + L + C) / 3 * V).sum() / V.sum()) if V.sum() else sc; e20 = ema(C, 20)
        gap = abs(df["o"] - df["pclose"]) / df["pclose"] * 100 if df["pclose"] else 0
        rows.append(dict(date=date, yr=date[:4], long=long, hh=s["hh"], usd=usd,
            with_sma=(not np.isnan(df["sma20"])) and (entry > df["sma20"]) == long,
            with_vwap=(entry > vwap) == long, with_ema=(entry > e20) == long,
            hivol=df["adr10"] > ADRMED, gap=gap,
            trend_prior=(not np.isnan(df["prng"])) and df["prng"] > 1.6 * df["adr10"], dow=df["dow"]))

print(f"BO market-2R trades (all hours): {len(rows)}\n")


def fm(sub):
    us = np.array([r["usd"] for r in sub]); n = len(us)
    if n < 2: return None
    net = us.sum(); w = us[us > 0]; l = us[us <= 0]; pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    mcl = cl = 0
    for x in us:
        cl = cl + 1 if x <= 0 else 0; mcl = max(mcl, cl)
    dts = sorted(r["date"] for r in sub); yrs = (_D.fromisoformat(dts[-1]) - _D.fromisoformat(dts[0])).days / 365.25 or 1
    sd = us.std(ddof=1); sh = us.mean() / sd if sd else 0
    return dict(n=n, net=round(net), yr=round(net / yrs), exp=round(us.mean(), 1), pf=round(pf, 2),
                win=round(100 * len(w) / n), dd=round(dd), nd=round(net / dd, 2) if dd else 9.99, shann=round(sh * np.sqrt(n / yrs), 2), mcl=mcl)


def show(lab, sub):
    m = fm(sub)
    if not m or m["n"] < 60: return
    print(f"  {lab:<24} n{m['n']:<4} net ${m['net']:>7,} $/yr ${m['yr']:>6,} exp ${m['exp']:>5} PF {m['pf']:.2f} "
          f"win{m['win']}% DD ${m['dd']:>6,} nd {m['nd']:.2f} Sh {m['shann']:.2f} mcl{m['mcl']}")


print("TIME-OF-DAY sweep (BO market-2R):")
for lab, fn in [("all hours", lambda r: True), (">=10", lambda r: r["hh"] >= 10), (">=11", lambda r: r["hh"] >= 11),
                (">=12", lambda r: r["hh"] >= 12), (">=13", lambda r: r["hh"] >= 13), ("hour==11", lambda r: r["hh"] == 11),
                ("hour==12", lambda r: r["hh"] == 12), ("hour==13", lambda r: r["hh"] == 13), ("hour==14", lambda r: r["hh"] == 14),
                ("11-13", lambda r: 11 <= r["hh"] <= 13), ("12-14", lambda r: 12 <= r["hh"] <= 14),
                ("11-14", lambda r: 11 <= r["hh"] <= 14), ("morning<11 (skip me)", lambda r: r["hh"] < 11)]:
    show(lab, [r for r in rows if fn(r)])

print("\nFILTERS on BO market-2R, >=11 base:")
base = lambda r: r["hh"] >= 11
for lab, fn in [("base(>=11)", lambda r: True), ("+with SMA20", lambda r: r["with_sma"]), ("+with VWAP", lambda r: r["with_vwap"]),
                ("+with EMA20", lambda r: r["with_ema"]), ("+hi-vol day", lambda r: r["hivol"]), ("+lo-vol day", lambda r: not r["hivol"]),
                ("+skip gap<0.3", lambda r: r["gap"] < 0.3), ("+only gap>0.5", lambda r: r["gap"] > 0.5),
                ("+skip after TD", lambda r: not r["trend_prior"]), ("+longs", lambda r: r["long"]), ("+shorts", lambda r: not r["long"]),
                ("+Mon-Wed", lambda r: r["dow"] <= 2), ("+Thu-Fri", lambda r: r["dow"] >= 3)]:
    show(lab, [r for r in rows if base(r) and fn(r)])

print("\nCOMBOS + by-year:")
combos = [("hivol", lambda r: r["hh"] >= 11 and r["hivol"]),
          ("hivol+with-vwap", lambda r: r["hh"] >= 11 and r["hivol"] and r["with_vwap"]),
          ("hivol+with-sma", lambda r: r["hh"] >= 11 and r["hivol"] and r["with_sma"]),
          ("11-14+hivol", lambda r: 11 <= r["hh"] <= 14 and r["hivol"])]
for lab, fn in combos:
    show(lab, [r for r in rows if fn(r)])
    yr = "   ".join(f"{y[2:]}:${(fm([r for r in rows if fn(r) and r['yr']==y]) or {'net':0})['net']:>5,}" for y in ["2021","2022","2023","2024","2025","2026"])
    print(f"      {yr}")

print("\nROBUSTNESS (by-year + OOS) for finalists:")
fin = [("skip-gap(>=11)", lambda r: r["hh"]>=11 and r["gap"]<0.3),
       ("hi-vol(>=11)", lambda r: r["hh"]>=11 and r["hivol"]),
       ("11-14+hivol", lambda r: 11<=r["hh"]<=14 and r["hivol"]),
       ("skip-gap+hivol", lambda r: r["hh"]>=11 and r["gap"]<0.3 and r["hivol"])]
for lab, fn in fin:
    print(f"  [{lab}]")
    for y in ["2021","2022","2023","2024","2025","2026"]:
        m = fm([r for r in rows if fn(r) and r["yr"]==y])
        if m: print(f"    {y}: net ${m['net']:>6,} PF {m['pf']:>4.2f} n{m['n']}")
    tr = fm([r for r in rows if fn(r) and r["yr"]<"2024"]); te = fm([r for r in rows if fn(r) and r["yr"]>="2024"])
    full = fm([r for r in rows if fn(r)])
    if tr and te and full:
        print(f"    TRAIN ${tr['net']:>6,}/PF{tr['pf']:.2f}/n{tr['n']} | TEST ${te['net']:>6,}/PF{te['pf']:.2f}/n{te['n']} | "
              f"ALL ${full['net']:,}/PF{full['pf']}/Sh{full['shann']}/nd{full['nd']}/mcl{full['mcl']}")
