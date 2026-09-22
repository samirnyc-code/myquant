"""Round 2: OOS-validated filter search on the full MyReversals export.

TRAIN = 2021-2023, TEST = 2024..2026-06. 1R target, NT-tick bars, per-signal BTC anchor.
- Expanded features (new ideas): away-depth before fill, signal-bar strength/close-loc,
  limit depth, VWAP extension, EMA slope, minutes-from-open, Nth-signal-of-day, room-to-target.
- Single filters reported TRAIN vs TEST (spot overfitting).
- Threshold sweeps for the continuous knobs.
- Greedy forward-selection stack on TRAIN, reported OOS.
Note: bars-to-fill is NOT a pre-trade filter (you're already in). away-depth IS actionable
(arm the limit only after price extends K*risk beyond the signal) — so we test that instead.
"""
import glob
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(r"c:\Users\Admin\myquant")
PT, RT, T = 50.0, 17.5, 1.0

b = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
DAY = {}
for d, g in b.groupby("Date"):
    g = g.sort_values("bar")
    DAY[d] = dict(bar=g["bar"].astype(int).values, O=g.Open.values, H=g.High.values,
                  L=g.L.values if "L" in g else g.Low.values, C=g.Close.values, V=g.Volume.values,
                  arr={int(k): (o, h, l, c) for k, o, h, l, c in zip(g["bar"], g.Open, g.High, g.Low, g.Close)})
dl = b.groupby("Date").agg(o=("Open", "first"), h=("High", "max"), l=("Low", "min"), c=("Close", "last")).reset_index()
dl["rng"] = dl.h - dl.l
dl["sma20"] = dl.c.rolling(20).mean().shift(1)
dl["adr10"] = dl.rng.rolling(10).mean().shift(1)
dl["prng"] = dl.rng.shift(1); dl["pclose"] = dl.c.shift(1); dl["dow"] = pd.to_datetime(dl.Date).dt.dayofweek
dl["pdh"] = dl.h.shift(1); dl["pdl"] = dl.l.shift(1)
DFEAT = dl.set_index("Date").to_dict("index")

f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit(): continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/"); num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt),
                     hh=int(tm[:2]), mn=int(tm[3:5])))
sigs.sort(key=lambda s: (s["date"], s["ft"]))


def ema_series(arr, span):
    a = 2 / (span + 1); e = [arr[0]]
    for x in arr[1:]:
        e.append(a * x + (1 - a) * e[-1])
    return e


rows = []
cnt_day = {}
for s in sigs:
    d = DAY.get(s["date"]); df = DFEAT.get(s["date"])
    if not d or df is None or s["ft"] not in d["arr"]: continue
    ft = s["ft"]; long = s["long"]
    sh = d["arr"][ft][3] - s["btc"]
    lmt = s["lmt"] + sh; stop = s["stop"] + sh
    so, shh, sll, ref = d["arr"][ft]
    risk = abs(lmt - stop)
    if risk < 0.25 or np.isnan(df["sma20"]) or np.isnan(df["adr10"]) or df["adr10"] <= 0: continue
    adr = df["adr10"]
    idx = d["bar"] <= ft
    C = d["C"][idx]; H = d["H"][idx]; L = d["L"][idx]; V = d["V"][idx]
    if len(C) < 6: continue
    es = ema_series(C, 20); ema20 = es[-1]; ema_slope_up = es[-1] > es[-6]
    tp = (H + L + C) / 3.0; vwap = float((tp * V).sum() / V.sum()) if V.sum() > 0 else ref
    dh, dld = H.max(), L.min(); loc = (ref - dld) / (dh - dld) if dh > dld else .5
    openpx = d["arr"][0][0] if 0 in d["arr"] else C[0]
    nth = cnt_day.get(s["date"], 0); cnt_day[s["date"]] = nth + 1
    sig_rng = shh - sll; sig_body = abs(so - ref)
    body_frac = sig_body / sig_rng if sig_rng > 0 else 0
    close_loc = (ref - sll) / sig_rng if sig_rng > 0 else .5   # for long want high; short want low
    lmt_depth = abs(ref - lmt) / risk
    vwap_dist = abs(ref - vwap) / adr
    mins = (s["hh"] - 8) * 60 + s["mn"] - 30
    # room to the target direction: distance to prior-day extreme in target dir
    if long:
        room = (df["pdh"] - ref) / adr if not np.isnan(df["pdh"]) else 9
    else:
        room = (ref - df["pdl"]) / adr if not np.isnan(df["pdl"]) else 9

    # --- sim + away depth ---
    arr = d["arr"]; n = int(d["bar"].max()); away = False; fb = None; ext = 0.0
    for i in range(ft + 1, n + 1):
        if i not in arr: continue
        hi, lo = arr[i][1], arr[i][2]
        if long:
            ext = max(ext, hi - lmt)
            if away and lo < lmt: fb = i; break
            if hi > shh: away = True
        else:
            ext = max(ext, lmt - lo)
            if away and hi > lmt: fb = i; break
            if lo < sll: away = True
    if fb is None: continue
    away_depth = ext / risk
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
    if expx is None: expx = arr[max(arr)][3]
    pts = (expx - lmt) if long else (lmt - expx)
    rows.append(dict(
        date=s["date"], train=s["date"] < "2024-01-01", long=long, rt=s["rt"], usd=pts * PT - RT, btf=fb - ft,
        risk_adr=risk / adr, w_sma=(ref > df["sma20"]) == long, w_vwap=(ref > vwap) == long,
        w_ema=(ref > ema20) == long, ema_slope_w=(ema_slope_up == long),
        w_day=((ref - openpx) > 0) == long, loc=loc,
        above_ib=None, inside_ib=None,  # (IB computed below if wanted; drop for speed)
        dist_extreme_adr=((dh - ref) if long else (ref - dld)) / adr,
        hh=s["hh"], mins=mins, nth=nth, dow=df["dow"],
        away_depth=away_depth, body_frac=body_frac, close_loc=(close_loc if long else 1 - close_loc),
        lmt_depth=lmt_depth, vwap_dist=vwap_dist, room=room,
        gap_pct=((df["o"] - df["pclose"]) / df["pclose"] * 100 if df["pclose"] else 0),
        trend_prior=((not np.isnan(df["prng"])) and df["prng"] > 1.6 * df["adr10"])))

TR = [r for r in rows if r["train"]]; TE = [r for r in rows if not r["train"]]
print(f"rows {len(rows)}  train {len(TR)} (..2023)  test {len(TE)} (2024..)\n")


def M(sub):
    n = len(sub)
    if n == 0: return None
    us = [r["usd"] for r in sub]; net = sum(us)
    w = [x for x in us if x > 0]; ls = [x for x in us if x <= 0]
    pf = sum(w) / (-sum(ls)) if ls and sum(ls) < 0 else 9.99
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(w) / n), nd=(round(net / dd, 2) if dd else 9.99))


def line(lab, fn):
    tr = M([r for r in TR if fn(r)]); te = M([r for r in TE if fn(r)])
    if not tr or tr["n"] < 60: return
    tes = f"${te['net']:>7,} PF{te['pf']:>5.2f} n{te['n']:>4}" if te and te["n"] else "  (no test)"
    print(f"  {lab:<30} TRAIN ${tr['net']:>7,} PF{tr['pf']:>5.2f} nd{tr['nd']:>5.2f} n{tr['n']:>4}  |  TEST {tes}")


print("SINGLE FILTERS — TRAIN vs TEST (overfit check):")
line("BASELINE (all)", lambda r: True)
for lab, fn in [
    ("longs only", lambda r: r["long"]),
    ("drop Trap", lambda r: r["rt"] != "Trap"),
    ("with SMA20-D", lambda r: r["w_sma"]),
    ("with VWAP", lambda r: r["w_vwap"]),
    ("with EMA20+slope", lambda r: r["w_ema"] and r["ema_slope_w"]),
    ("skip morning (>=11h)", lambda r: r["hh"] >= 11),
    ("midday+pm (11-15)", lambda r: 11 <= r["hh"] <= 15),
    ("tight risk (<0.15 ADR)", lambda r: r["risk_adr"] < 0.15),
    ("away-depth >=0.5R", lambda r: r["away_depth"] >= 0.5),
    ("away-depth >=1R", lambda r: r["away_depth"] >= 1.0),
    ("strong FT close (>=0.6)", lambda r: r["close_loc"] >= 0.6),
    ("FT body >=0.4", lambda r: r["body_frac"] >= 0.4),
    ("limit not too deep (<0.7R)", lambda r: r["lmt_depth"] < 0.7),
    ("near VWAP (<0.3 ADR)", lambda r: r["vwap_dist"] < 0.3),
    ("room to prior-ext >=1 ADR", lambda r: r["room"] >= 1.0),
    ("mid-range loc (.3-.7)", lambda r: 0.3 <= r["loc"] <= 0.7),
    ("1st or 2nd signal of day", lambda r: r["nth"] <= 1),
    ("Mon/Tue", lambda r: r["dow"] in (0, 1)),
    ("skip gap (<0.3%)", lambda r: abs(r["gap_pct"]) < 0.3),
    ("skip after trend day", lambda r: not r["trend_prior"]),
]:
    line(lab, fn)

print("\nTHRESHOLD SWEEPS (TRAIN net$ / PF / n  ||  TEST net$ / PF / n):")
def sweep(name, key, vals, ge=True):
    print(f"  {name}:")
    for v in vals:
        fn = (lambda r, v=v: r[key] >= v) if ge else (lambda r, v=v: r[key] <= v)
        tr = M([r for r in TR if fn(r)]); te = M([r for r in TE if fn(r)])
        if tr and te:
            print(f"    {('>=' if ge else '<=')}{v:<6} TR ${tr['net']:>7,}/{tr['pf']:.2f}/n{tr['n']:<4}  TE ${te['net']:>7,}/{te['pf']:.2f}/n{te['n']}")
sweep("away_depth >=", "away_depth", [0.25, 0.5, 0.75, 1.0, 1.5])
sweep("risk_adr <=", "risk_adr", [0.10, 0.15, 0.20, 0.25], ge=False)
sweep("min hour >=", "hh", [10, 11, 12, 13])
sweep("FT close_loc >=", "close_loc", [0.4, 0.5, 0.6, 0.7])

# greedy forward selection on TRAIN (maximize nd, n>=250)
print("\nGREEDY STACK (build on TRAIN by Net/DD, n>=250 floor):")
CAND = {
    "longs": lambda r: r["long"], "skip_morning": lambda r: r["hh"] >= 11,
    "tight_risk": lambda r: r["risk_adr"] < 0.18, "away>=0.5R": lambda r: r["away_depth"] >= 0.5,
    "strong_close": lambda r: r["close_loc"] >= 0.55, "with_vwap": lambda r: r["w_vwap"],
    "near_vwap": lambda r: r["vwap_dist"] < 0.4, "room>=0.75": lambda r: r["room"] >= 0.75,
    "drop_trap": lambda r: r["rt"] != "Trap", "with_sma": lambda r: r["w_sma"],
    "skip_gap": lambda r: abs(r["gap_pct"]) < 0.3,
}
chosen = []
def stackfn(names): return lambda r: all(CAND[k](r) for k in names)
cur = M(TR)
while True:
    best = None
    for k in CAND:
        if k in chosen: continue
        sub = [r for r in TR if stackfn(chosen + [k])(r)]
        m = M(sub)
        if m and m["n"] >= 250 and (best is None or m["nd"] > best[1]["nd"]):
            best = (k, m)
    if not best or best[1]["nd"] <= cur["nd"] + 0.05: break
    chosen.append(best[0]); cur = best[1]
    tr = cur; te = M([r for r in TE if stackfn(chosen)(r)])
    print(f"  + {best[0]:<14} -> stack {chosen}")
    print(f"      TRAIN ${tr['net']:>7,} PF{tr['pf']:.2f} win{tr['win']}% nd{tr['nd']} n{tr['n']}  |  "
          f"TEST ${te['net']:>7,} PF{te['pf']:.2f} win{te['win']}% nd{te['nd']} n{te['n']}" if te else "")
print(f"\nFINAL STACK: {chosen}")
full = [r for r in rows if stackfn(chosen)(r)]
print("  ALL(21-26):", M(full))

print("\nAWAY>=1R BASE + one partner (OOS):")
base = lambda r: r["away_depth"] >= 1.0
print("  away>=1R alone           ALL", M([r for r in rows if base(r)]))
for lab, fn in [
    ("+skip morning(>=11)", lambda r: r["hh"] >= 11), ("+longs", lambda r: r["long"]),
    ("+with SMA20", lambda r: r["w_sma"]), ("+drop Trap", lambda r: r["rt"] != "Trap"),
    ("+Mon/Tue", lambda r: r["dow"] in (0, 1)), ("+with VWAP", lambda r: r["w_vwap"]),
    ("+away>=1.5R", lambda r: r["away_depth"] >= 1.5), ("+skip gap", lambda r: abs(r["gap_pct"]) < 0.3),
    ("+skip after TD", lambda r: not r["trend_prior"]), ("+strong close(>=0.55)", lambda r: r["close_loc"] >= 0.55),
]:
    g = lambda r: base(r) and fn(r)
    tr = M([r for r in TR if g(r)]); te = M([r for r in TE if g(r)])
    if tr and te and te["n"] > 40:
        print(f"  away>=1R {lab:<20} TRAIN ${tr['net']:>6,}/PF{tr['pf']:.2f}/nd{tr['nd']:>4}/n{tr['n']:<4}  TEST ${te['net']:>6,}/PF{te['pf']:.2f}/n{te['n']}")
