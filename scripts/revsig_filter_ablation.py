"""Systematic filter ablation on the full MyReversals export, 1R target, NT-tick bars.

Baseline = all filled trades. Each filter prints Net$/PF/win/MaxDD$/Net-DD/n at 1R.
Features computed at the SIGNAL bar (no lookahead). Daily features use PRIOR day.
Dimensions: type, direction, location, intraday EMA20, VWAP, IB, gap, after-trend-day,
time-of-day, risk size, volatility, with-day-move, first-of-day, day-of-week, fill speed.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np, statistics as st

ROOT = Path(r"c:\Users\Admin\myquant")
PT, RT, T = 50.0, 17.5, 1.0   # 1R target

b = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
DAY = {}
for d, g in b.groupby("Date"):
    g = g.sort_values("bar")
    DAY[d] = dict(bar=g["bar"].astype(int).values, O=g.Open.values, H=g.High.values,
                  L=g.Low.values, C=g.Close.values, V=g.Volume.values,
                  arr={int(k): (o, h, l, c) for k, o, h, l, c in
                       zip(g["bar"], g.Open, g.High, g.Low, g.Close)})
# daily frame
dl = b.groupby("Date").agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"),
                           c=("Close", "last")).reset_index()
dl["rng"] = dl.h - dl.l
dl["sma20"] = dl.c.rolling(20).mean().shift(1)
dl["adr10"] = dl.rng.rolling(10).mean().shift(1)
dl["prng"] = dl.rng.shift(1)
dl["pclose"] = dl.c.shift(1)
dl["pdh"] = dl.h.shift(1); dl["pdl"] = dl.l.shift(1)
dl["dow"] = pd.to_datetime(dl.Date).dt.dayofweek
DFEAT = dl.set_index("Date").to_dict("index")

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt),
                     hh=int(tm[:2]), mn=int(tm[3:5])))
sigs.sort(key=lambda s: (s["date"], s["ft"]))


def ema(arr, span):
    a = 2 / (span + 1); e = arr[0]
    for x in arr[1:]:
        e = a * x + (1 - a) * e
    return e


rows = []
seen_day = {}
for s in sigs:
    d = DAY.get(s["date"]); df = DFEAT.get(s["date"])
    if not d or df is None or s["ft"] not in d["arr"]:
        continue
    ft = s["ft"]; long = s["long"]
    sh = d["arr"][ft][3] - s["btc"]                         # BTC anchor -> bar scale
    lmt = s["lmt"] + sh; stop = s["stop"] + sh; ref = d["arr"][ft][3]
    risk = abs(lmt - stop)
    if risk < 0.25 or np.isnan(df["sma20"]) or np.isnan(df["adr10"]) or df["adr10"] <= 0:
        continue
    # intraday features up to ft
    idx = d["bar"] <= ft
    C = d["C"][idx]; H = d["H"][idx]; L = d["L"][idx]; V = d["V"][idx]
    if len(C) < 2: continue
    ema20 = ema(C, 20)
    tp = (H + L + C) / 3.0
    vwap = float((tp * V).sum() / V.sum()) if V.sum() > 0 else ref
    dh, dld = H.max(), L.min()
    loc = (ref - dld) / (dh - dld) if dh > dld else 0.5     # 0=day low, 1=day high
    ibh = ibl = None
    ibmask = d["bar"] <= 11
    if len(C) >= 12 and ibmask.any():
        ibh = d["H"][ibmask].max(); ibl = d["L"][ibmask].min()
    openpx = d["arr"][0][0] if 0 in d["arr"] else C[0]
    daymove = ref - openpx
    adr = df["adr10"]; sma = df["sma20"]
    gap = (df["o"] - df["pclose"]) if not np.isnan(df["pclose"]) else 0.0
    gap_pct = gap / df["pclose"] * 100 if df["pclose"] else 0.0
    trend_prior = (not np.isnan(df["prng"])) and (df["prng"] > 1.6 * df["adr10"])
    fd = s["date"] not in seen_day; seen_day[s["date"]] = 1

    # --- trade sim (pullback fill, 1R) ---
    arr = d["arr"]; n = int(d["bar"].max()); slo = arr[ft][2]; shi = arr[ft][1]; away = False; fb = None
    for i in range(ft + 1, n + 1):
        if i not in arr: continue
        hi, lo = arr[i][1], arr[i][2]
        if long:
            if away and lo < lmt: fb = i; break
            if hi > shi: away = True
        else:
            if away and hi > lmt: fb = i; break
            if lo < slo: away = True
    if fb is None:
        continue
    tgt = lmt + T * risk if long else lmt - T * risk
    expx = None
    for j in range(fb, n + 1):
        if j not in arr: continue
        hi, lo = arr[j][1], arr[j][2]
        if long:
            if lo <= stop: expx = stop; break
            if hi >= tgt: expx = tgt; break
        else:
            if hi >= stop: expx = stop; break
            if lo <= tgt: expx = tgt; break
    if expx is None:
        expx = arr[max(arr)][3]
    pts = (expx - lmt) if long else (lmt - expx)
    usd = pts * PT - RT

    rows.append(dict(
        date=s["date"], long=long, rt=s["rt"], usd=usd, btf=fb - ft, risk=risk,
        # dimensionless / directional features (with-trend = True means aligned to trade side)
        w_sma=(ref > sma) == long, w_ema=(ref > ema20) == long, w_vwap=(ref > vwap) == long,
        w_open=(ref > openpx) == long, w_day=(daymove > 0) == long,
        loc=loc, loc_frac_side=(loc if long else 1 - loc),   # how far entry is from the extreme it's fading toward
        above_ib=(ibh is not None and ref > ibh), below_ib=(ibl is not None and ref < ibl),
        inside_ib=(ibh is not None and ibl <= ref <= ibh),
        dist_extreme_adr=((dh - ref) if long else (ref - dld)) / adr,   # room to the day extreme it targets
        gap_pct=gap_pct, trend_prior=trend_prior, risk_adr=risk / adr,
        hh=s["hh"], first_day=fd, dow=df["dow"], adr=adr))

print(f"filled trades with features: {len(rows)}   (target = 1R, NT bars, $17.5 RT)\n")


def M(sub):
    n = len(sub)
    if n == 0: return None
    us = [r["usd"] for r in sub]; net = sum(us)
    w = [x for x in us if x > 0]; l = [x for x in us if x <= 0]
    pf = sum(w) / (-sum(l)) if l and sum(l) < 0 else float("inf")
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(w) / n),
                dd=round(dd), nd=(round(net / dd, 2) if dd else 9.99))


base = M(rows)
def show(lab, sub):
    m = M(sub)
    if not m or m["n"] < 120:
        print(f"  {lab:<26} n={m['n'] if m else 0:<4} (too few)"); return
    print(f"  {lab:<26} n={m['n']:<4} net=${m['net']:>8,} PF {m['pf']:>4.2f} win {m['win']:>2}% "
          f"DD ${m['dd']:>7,} nd {m['nd']:>5.2f}")

print(f"BASELINE  n={base['n']} net=${base['net']:,} PF {base['pf']} win {base['win']}% DD ${base['dd']:,} nd {base['nd']}\n")

FILTERS = [
    ("longs only", lambda r: r["long"]),
    ("shorts only", lambda r: not r["long"]),
    ("drop Trap", lambda r: r["rt"] != "Trap"),
    ("BO only", lambda r: r["rt"] == "BO"),
    ("with SMA20-D", lambda r: r["w_sma"]),
    ("against SMA20-D", lambda r: not r["w_sma"]),
    ("with EMA20 (intraday)", lambda r: r["w_ema"]),
    ("against EMA20", lambda r: not r["w_ema"]),
    ("with VWAP", lambda r: r["w_vwap"]),
    ("against VWAP", lambda r: not r["w_vwap"]),
    ("with day-open", lambda r: r["w_open"]),
    ("with day-move (momo)", lambda r: r["w_day"]),
    ("against day-move (fade)", lambda r: not r["w_day"]),
    ("entry beyond IB (brk)", lambda r: r["above_ib"] or r["below_ib"]),
    ("entry inside IB", lambda r: r["inside_ib"]),
    ("NOT fading into extreme (>0.5adr room)", lambda r: r["dist_extreme_adr"] > 0.5),
    ("fading into extreme (<0.25adr)", lambda r: r["dist_extreme_adr"] < 0.25),
    ("loc: entry mid-range (.3-.7)", lambda r: 0.3 <= r["loc"] <= 0.7),
    ("skip gap days (|gap|<0.3%)", lambda r: abs(r["gap_pct"]) < 0.3),
    ("only gap days (|gap|>0.5%)", lambda r: abs(r["gap_pct"]) > 0.5),
    ("skip after trend day", lambda r: not r["trend_prior"]),
    ("only after trend day", lambda r: r["trend_prior"]),
    ("tight risk (<0.15 ADR)", lambda r: r["risk_adr"] < 0.15),
    ("wide risk (>0.30 ADR)", lambda r: r["risk_adr"] > 0.30),
    ("morning (<11:00)", lambda r: r["hh"] < 11),
    ("midday (11-13)", lambda r: 11 <= r["hh"] < 13),
    ("afternoon (>=13)", lambda r: r["hh"] >= 13),
    ("skip first 30m & last 30m", lambda r: r["hh"] >= 9 and r["hh"] < 14 or (r["hh"] == 14)),
    ("first signal of day only", lambda r: r["first_day"]),
    ("fast fill (<=2 bars)", lambda r: r["btf"] <= 2),
    ("slow fill (>=6 bars)", lambda r: r["btf"] >= 6),
    ("calm day (ADR<median)", lambda r: r["adr"] < dl.adr10.median()),
    ("volatile day (ADR>median)", lambda r: r["adr"] > dl.adr10.median()),
    ("Mon/Tue", lambda r: r["dow"] in (0, 1)),
    ("Wed/Thu/Fri", lambda r: r["dow"] in (2, 3, 4)),
]
print("SINGLE FILTERS (min n=120), scan:")
res = [(lab, M([r for r in rows if fn(r)])) for lab, fn in FILTERS]
for lab, fn in FILTERS:
    show(lab, [r for r in rows if fn(r)])

print("\nRANKED by Net/DD (n>=200):")
ranked = sorted([(lab, m) for lab, m in res if m and m["n"] >= 200], key=lambda x: -x[1]["nd"])
for lab, m in ranked[:12]:
    print(f"  {lab:<40} nd {m['nd']:>5.2f}  PF {m['pf']:>4.2f}  net ${m['net']:>8,}  n {m['n']}")

# quick combos of the top directional cuts
print("\nCOMBOS:")
combos = [
    ("longs + with-SMA20", lambda r: r["long"] and r["w_sma"]),
    ("longs + drop-Trap", lambda r: r["long"] and r["rt"] != "Trap"),
    ("longs + with-VWAP", lambda r: r["long"] and r["w_vwap"]),
    ("longs + not-fade-extreme", lambda r: r["long"] and r["dist_extreme_adr"] > 0.5),
    ("longs + skip-gap + skip-TD", lambda r: r["long"] and abs(r["gap_pct"]) < 0.3 and not r["trend_prior"]),
    ("longs + with-SMA20 + not-fade-extreme", lambda r: r["long"] and r["w_sma"] and r["dist_extreme_adr"] > 0.5),
    ("longs + with-VWAP + with-SMA20", lambda r: r["long"] and r["w_vwap"] and r["w_sma"]),
]
for lab, fn in combos:
    show(lab, [r for r in rows if fn(r)])
