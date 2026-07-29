"""Exit engineering on BO+skip-morning+MARKET entry, real ticks. Target sweep,
breakeven-after-1R, trailing, scale-out. Full metrics + by-year. $50/pt, $17.5 RT.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np
from datetime import date as _D

ROOT = Path(r"c:\Users\Admin\myquant"); TICKS = ROOT / "data/ticks_continuous"
PT, RT, INF = 50.0, 17.5, 10 ** 9

b5 = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["Date"] = b5["DateTime"].dt.date.astype(str)
BARS = {d: {int(k): (o, h, l, c) for k, o, h, l, c in zip(g.sort_values("bar")["bar"], g.Open, g.High, g.Low, g.Close)}
        for d, g in b5.groupby("Date")}
dl = b5.groupby("Date").agg(h=("High", "max"), l=("Low", "min"), c=("Close", "last")).reset_index()
dl["rng"] = dl.h - dl.l; dl["adr10"] = dl.rng.rolling(10).mean().shift(1); dl["sma20"] = dl.c.rolling(20).mean().shift(1)
DF = dl.set_index("Date").to_dict("index")

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    if rt != "BO" or int(tm[:2]) < 11: continue          # BO + skip morning
    sigs.append(dict(long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}", ft=int(bn) - 1,
                     btc=num(btc), stop=num(stop), hh=int(tm[:2])))
byday = {}
for s in sigs: byday.setdefault(s["date"], []).append(s)


def fixed(ex, entry, stop, risk, long, T):
    if long:
        sm = ex <= stop; tm = ex >= entry + T * risk
    else:
        sm = ex >= stop; tm = ex <= entry - T * risk
    si = int(np.argmax(sm)) if sm.any() else INF; ti = int(np.argmax(tm)) if tm.any() else INF
    if si == INF and ti == INF: px = ex[-1]
    elif si <= ti: px = stop
    else: px = entry + T * risk if long else entry - T * risk
    return (px - entry) if long else (entry - px)


def dyn(ex, entry, stop, risk, long, mode, T=3.0, be_at=1.0, trail_k=1.0):
    """mode: 'be' (BE after be_at, target T) | 'trail' (trail_k R after be_at)"""
    s = stop; be = False; peak = ex[0]
    for p in ex[1:]:
        if long:
            peak = max(peak, p)
            if p >= entry + be_at * risk:
                if mode == "be" and not be: s = max(s, entry); be = True
                if mode == "trail": s = max(s, peak - trail_k * risk)
            if mode == "be" and p >= entry + T * risk: return T * risk
            if p <= s: return s - entry
        else:
            peak = min(peak, p)
            if p <= entry - be_at * risk:
                if mode == "be" and not be: s = min(s, entry); be = True
                if mode == "trail": s = min(s, peak + trail_k * risk)
            if mode == "be" and p <= entry - T * risk: return T * risk
            if p >= s: return entry - s
    return (ex[-1] - entry) if long else (entry - ex[-1])


def scale(ex, entry, stop, risk, long, T1=1.0, T2=3.0):
    # half at +T1, runner to +T2 with BE after T1
    h1 = fixed(ex, entry, stop, risk, long, T1)                 # first half capped at T1 (or stop)
    h2 = dyn(ex, entry, stop, risk, long, "be", T=T2, be_at=T1)  # runner BE-after-T1
    return 0.5 * h1 + 0.5 * h2


rows = []
for date in sorted(byday):
    tp = TICKS / f"{date}.parquet"; bd = BARS.get(date); df = DF.get(date)
    if not tp.exists() or not bd or df is None: continue
    t = pd.read_parquet(tp); Pr = t["Price"].to_numpy(float)
    B = (t["DateTime"].dt.hour.to_numpy() * 60 + t["DateTime"].dt.minute.to_numpy() - 510) // 5
    adr = df["adr10"]; sma = df["sma20"]
    for s in byday[date]:
        ft = s["ft"]
        if ft not in bd: continue
        sc = bd[ft][3]; sh = sc - s["btc"]; stop = s["stop"] + sh; long = s["long"]
        live = int(np.searchsorted(B, ft + 1))
        if live >= len(Pr): continue
        ex = Pr[live:]; entry = ex[0]; risk = abs(entry - stop)
        if risk < 0.25: continue
        r = dict(date=date, yr=date[:4], long=long,
                 with_sma=(not np.isnan(sma)) and ((entry > sma) == long),
                 hivol=(not np.isnan(adr)) and adr > dl.adr10.median())
        for T in [1.5, 2.0, 2.5, 3.0]:
            r[f"fix{T}"] = fixed(ex, entry, stop, risk, long, T) * PT - RT
        r["be3"] = dyn(ex, entry, stop, risk, long, "be", T=3.0, be_at=1.0) * PT - RT
        r["be4"] = dyn(ex, entry, stop, risk, long, "be", T=4.0, be_at=1.0) * PT - RT
        r["trail1"] = dyn(ex, entry, stop, risk, long, "trail", be_at=1.0, trail_k=1.0) * PT - RT
        r["trail1.5"] = dyn(ex, entry, stop, risk, long, "trail", be_at=1.0, trail_k=1.5) * PT - RT
        r["scale13"] = scale(ex, entry, stop, risk, long, 1.0, 3.0) * PT - RT
        rows.append(r)

print(f"BO skip-morning trades: {len(rows)}\n")


def fm(sub, key):
    us = np.array([r[key] for r in sub]); n = len(us)
    if n < 2: return None
    net = us.sum(); w = us[us > 0]; l = us[us <= 0]; pf = w.sum() / -l.sum() if l.sum() < 0 else 9.99
    eq = np.cumsum(us); dd = float((np.maximum.accumulate(eq) - eq).max())
    mcl = cl = 0
    for x in us:
        cl = cl + 1 if x <= 0 else 0; mcl = max(mcl, cl)
    dts = sorted(r["date"] for r in sub); yrs = (_D.fromisoformat(dts[-1]) - _D.fromisoformat(dts[0])).days / 365.25 or 1
    sd = us.std(ddof=1); sh = us.mean() / sd if sd else 0
    return dict(n=n, net=round(net), yr=round(net / yrs), exp=round(us.mean(), 1), pf=round(pf, 2),
                win=round(100 * len(w) / n), dd=round(dd), nd=round(net / dd, 2) if dd else 9.99,
                shann=round(sh * np.sqrt(n / yrs), 2), mcl=mcl, aw=round(w.mean()) if len(w) else 0, al=round(l.mean()) if len(l) else 0)


print(f"{'exit':<10} {'net$':>8} {'$/yr':>7} {'exp':>5} {'PF':>5} {'win%':>4} {'maxDD':>7} {'nd':>5} {'Shann':>6} {'mcl':>4} {'avgW':>6} {'avgL':>6}")
for k in ["fix1.5", "fix2.0", "fix2.5", "fix3.0", "be3", "be4", "trail1", "trail1.5", "scale13"]:
    m = fm(rows, k)
    print(f"{k:<10} {m['net']:>8,} {m['yr']:>7,} {m['exp']:>5} {m['pf']:>5.2f} {m['win']:>4} {m['dd']:>7,} {m['nd']:>5.2f} {m['shann']:>6.2f} {m['mcl']:>4} {m['aw']:>6,} {m['al']:>6,}")

# best few by-year + light gates
print("\nBY-YEAR for top exits:")
for k in ["fix2.0", "be3", "trail1.5", "scale13"]:
    print(f"  [{k}]", end=" ")
    yr = []
    for y in ["2021", "2022", "2023", "2024", "2025", "2026"]:
        sub = [r for r in rows if r["yr"] == y]
        m = fm(sub, k)
        if m: yr.append(f"{y[2:]}:${m['net']:>5,}/{m['pf']:.2f}")
    print("  ".join(yr))

print("\nLIGHT GATES on be3 (best runner):")
for lab, fn in [("all", lambda r: True), ("with-SMA20", lambda r: r["with_sma"]),
                ("against-SMA20", lambda r: not r["with_sma"]), ("hi-vol day", lambda r: r["hivol"]),
                ("lo-vol day", lambda r: not r["hivol"]), ("longs", lambda r: r["long"]), ("shorts", lambda r: not r["long"])]:
    sub = [r for r in rows if fn(r)]
    m = fm(sub, "be3")
    if m and m["n"] > 40: print(f"  be3 {lab:<14} net ${m['net']:>7,} PF {m['pf']:.2f} Shann {m['shann']:.2f} nd {m['nd']:.2f} n{m['n']} mcl{m['mcl']}")
