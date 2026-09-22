"""Full filter ablation on REAL TICK fills. TRAIN 2021-23 / TEST 2024..2026-06.
Outcome ($, away-depth, bars-to-fill) from data/ticks_continuous (exact tick order).
Features at the signal bar (5M, no lookahead). 1 ES, $50/pt, $17.5 RT.
Goal: find any subset net-positive AFTER cost, out-of-sample.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, T, INF = 50.0, 17.5, 1.0, 10 ** 9

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {}
for d, g in b5.groupby("Date"):
    g = g.sort_values("bar")
    BARS[d] = dict(bar=g["bar"].astype(int).values, O=g.Open.values, H=g.High.values, L=g.Low.values,
                   C=g.Close.values, V=g.Volume.values,
                   arr={int(k): (o, h, l, c) for k, o, h, l, c in zip(g["bar"], g.Open, g.High, g.Low, g.Close)})
dl = b5.groupby("Date").agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"), c=("Close", "last")).reset_index()
dl["rng"] = dl.h - dl.l
dl["sma20"] = dl.c.rolling(20).mean().shift(1); dl["adr10"] = dl.rng.rolling(10).mean().shift(1)
dl["prng"] = dl.rng.shift(1); dl["pclose"] = dl.c.shift(1); dl["pdh"] = dl.h.shift(1); dl["pdl"] = dl.l.shift(1)
dl["dow"] = pd.to_datetime(dl.Date).dt.dayofweek
DF = dl.set_index("Date").to_dict("index")

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt), hh=int(tm[:2]), mn=int(tm[3:5])))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)


def ema(a, span):
    k = 2 / (span + 1); e = a[0]
    for x in a[1:]: e = k * x + (1 - k) * e
    return e


rows = []; cnt = {}
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date); df = DF.get(date)
    if not tp.exists() or not bd or df is None: continue
    if np.isnan(df["sma20"]) or np.isnan(df["adr10"]) or df["adr10"] <= 0: continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    adr = df["adr10"]
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bd["arr"]: continue
        so, shh, sll, sc = bd["arr"][ft]; sh = sc - s["btc"]
        lmt = s["lmt"] + sh; stop = s["stop"] + sh; long = s["long"]; risk = abs(lmt - stop)
        if risk < 0.25: continue
        # --- tick fill ---
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        sub = Pr[live:]; subB = B[live:]
        if long:
            aw = sub > shh
            if not aw.any(): continue
            a = int(np.argmax(aw)); fl = sub[a:] <= lmt
            if not fl.any(): continue
            fi = a + int(np.argmax(fl)); awd = (sub[:fi + 1].max() - lmt) / risk
            ex = sub[fi:]; sm = ex <= stop; tm = ex >= lmt + risk
        else:
            aw = sub < sll
            if not aw.any(): continue
            a = int(np.argmax(aw)); fl = sub[a:] >= lmt
            if not fl.any(): continue
            fi = a + int(np.argmax(fl)); awd = (lmt - sub[:fi + 1].min()) / risk
            ex = sub[fi:]; sm = ex >= stop; tm = ex <= lmt - risk
        si = int(np.argmax(sm)) if sm.any() else INF; ti = int(np.argmax(tm)) if tm.any() else INF
        expx = sub[-1] if (si == INF and ti == INF) else (stop if si <= ti else (lmt + risk if long else lmt - risk))
        pts = (expx - lmt) if long else (lmt - expx)
        usd = pts * PT - RT; btf = max(int(subB[fi]) - ft, 0)
        # --- features at signal bar ---
        idx = bd["bar"] <= ft; C = bd["C"][idx]; H = bd["H"][idx]; L = bd["L"][idx]; V = bd["V"][idx]
        if len(C) < 6: continue
        e20 = ema(C, 20); tpv = (H + L + C) / 3.0; vwap = float((tpv * V).sum() / V.sum()) if V.sum() > 0 else sc
        dh, dld = H.max(), L.min(); loc = (sc - dld) / (dh - dld) if dh > dld else .5
        openpx = bd["arr"][0][0] if 0 in bd["arr"] else C[0]
        srng = shh - sll; cl = (sc - sll) / srng if srng > 0 else .5
        nth = cnt.get(date, 0); cnt[date] = nth + 1
        room = ((df["pdh"] - sc) if long else (sc - df["pdl"])) / adr
        rows.append(dict(train=date < "2024-01-01", long=long, rt=s["rt"], usd=usd, away=awd, btf=btf,
            w_sma=(sc > df["sma20"]) == long, w_vwap=(sc > vwap) == long, w_ema=(sc > e20) == long,
            w_day=((sc - openpx) > 0) == long, loc=loc, dist_ext=((dh - sc) if long else (sc - dld)) / adr,
            risk_adr=risk / adr, hh=s["hh"], nth=nth, dow=df["dow"], close_loc=(cl if long else 1 - cl),
            room=room if not np.isnan(room) else 9, gap=(abs(df["o"] - df["pclose"]) / df["pclose"] * 100 if df["pclose"] else 0),
            trend_prior=((not np.isnan(df["prng"])) and df["prng"] > 1.6 * df["adr10"])))

TR = [r for r in rows if r["train"]]; TE = [r for r in rows if not r["train"]]
print(f"tick fills: {len(rows)}  train {len(TR)} / test {len(TE)}\n")


def M(sub):
    n = len(sub)
    if not n: return None
    us = [r["usd"] for r in sub]; net = sum(us); w = [x for x in us if x > 0]; ls = [x for x in us if x <= 0]
    pf = sum(w) / (-sum(ls)) if ls and sum(ls) < 0 else 9.99
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(w) / n), nd=(round(net / dd, 2) if dd else 9.99))


def line(lab, fn):
    tr = M([r for r in TR if fn(r)]); te = M([r for r in TE if fn(r)])
    if not tr or tr["n"] < 60: return
    flag = " <== TEST+" if te and te["net"] > 0 else ""
    print(f"  {lab:<26} TR ${tr['net']:>7,}/PF{tr['pf']:.2f}/n{tr['n']:<4} | TE ${te['net']:>7,}/PF{te['pf']:.2f}/n{te['n']}{flag}"
          if te else f"  {lab:<26} TR ${tr['net']:>7,}/PF{tr['pf']:.2f}/n{tr['n']}")


print("SINGLE FILTERS (TRAIN | TEST), net after $17.5 RT:")
for lab, fn in [
    ("BASELINE", lambda r: True), ("longs", lambda r: r["long"]), ("shorts", lambda r: not r["long"]),
    ("drop Trap", lambda r: r["rt"] != "Trap"), ("BO only", lambda r: r["rt"] == "BO"),
    ("IB only", lambda r: r["rt"] == "IB"), ("Trap only", lambda r: r["rt"] == "Trap"),
    ("with SMA20", lambda r: r["w_sma"]), ("against SMA20", lambda r: not r["w_sma"]),
    ("with VWAP", lambda r: r["w_vwap"]), ("against VWAP", lambda r: not r["w_vwap"]),
    ("with EMA20", lambda r: r["w_ema"]), ("with day-move", lambda r: r["w_day"]),
    ("skip morning(>=11)", lambda r: r["hh"] >= 11), ("morning(<11)", lambda r: r["hh"] < 11),
    ("midday(11-13)", lambda r: 11 <= r["hh"] < 13), ("pm(>=13)", lambda r: r["hh"] >= 13),
    ("tight risk<0.15adr", lambda r: r["risk_adr"] < 0.15), ("wide risk>0.25adr", lambda r: r["risk_adr"] > 0.25),
    ("away>=1R", lambda r: r["away"] >= 1), ("away>=1.5R", lambda r: r["away"] >= 1.5),
    ("away<0.5R", lambda r: r["away"] < 0.5), ("fast fill(<=2b)", lambda r: r["btf"] <= 2),
    ("slow fill(>=6b)", lambda r: r["btf"] >= 6), ("strong close>=0.6", lambda r: r["close_loc"] >= 0.6),
    ("skip gap<0.3%", lambda r: r["gap"] < 0.3), ("only gap>0.5%", lambda r: r["gap"] > 0.5),
    ("skip after TD", lambda r: not r["trend_prior"]), ("only after TD", lambda r: r["trend_prior"]),
    ("mid loc(.3-.7)", lambda r: 0.3 <= r["loc"] <= 0.7), ("room>=1adr", lambda r: r["room"] >= 1),
    ("1st sig of day", lambda r: r["nth"] == 0), ("Mon/Tue", lambda r: r["dow"] in (0, 1)),
    ("Wed/Thu/Fri", lambda r: r["dow"] in (2, 3, 4)),
]:
    line(lab, fn)

print("\nORDER-EXPIRY (keep btf<=N):")
for N in [1, 2, 3, 5, 8, 999]:
    line(f"btf<={('inf' if N==999 else N)}", lambda r, N=N: r["btf"] <= N)
