"""Full MyReversals export backtest on NT-tick bars (es_5m_rth) — by-type $ metrics.

Bars: research/scalp_swing/es_5m_rth.parquet (NT ticks, continuous). NO Databento.
Alignment: each signal is anchored to the bars via its own BTC (= signal-bar close):
  shift = bar_close[ft] - BTC ; LMT/stop shifted by `shift` onto the bar scale.
  This auto-corrects any contract/rollover offset (BTC pins it) — see the offset report.

Entry: pullback tick-through at LMT (away-move beyond signal bar, then long Low<LMT /
       short High>LMT). Entry = LMT. risk=|LMT-stop|=1R.
Exit : first of stop (touch) / target (T*risk, touch) / EOD close. Entry bar incl, stop first.
Sizing: 1 ES, $50/pt, $17.5 round-turn. Independent trades (no opp-cancel).
"""
import glob, sys
from pathlib import Path
import pandas as pd, statistics as st

ROOT = Path(r"c:\Users\Admin\myquant")
PT, RT = 50.0, 17.5
CUTOFF = sys.argv[1] if len(sys.argv) > 1 else None   # keep dates <= cutoff (dd within file already <= 6/16)

# --- bars ---
b = pd.read_parquet(ROOT / "research/scalp_swing/es_5m_rth.parquet")
b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
DAYS = {}
for d, g in b.groupby("Date"):
    g = g.sort_values("bar")
    DAYS[d] = list(zip(g["bar"].astype(int), g.Open.values, g.High.values, g.Low.values, g.Close.values))
# index by bar number for O(1)
DAYARR = {d: {bar: (o, h, l, c) for (bar, o, h, l, c) in rows} for d, rows in DAYS.items()}
DAYMAX = {d: max(x[0] for x in rows) for d, rows in DAYS.items()}

# --- signals ---
f = [x for x in glob.glob(str(ROOT / "data/signals/*.txt"))
     if "LMTPrice" in open(x, encoding="utf-8").read(400) and "JUN26" in x and "1830" in x][0]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, btc=num(btc), stop=num(stop), lmt=num(lmt)))
if CUTOFF:
    sigs = [s for s in sigs if s["date"] <= CUTOFF]
sigs.sort(key=lambda s: (s["date"], s["ft"]))
print(f"file: {Path(f).name}\nsignals: {len(sigs)}  ({sigs[0]['date']} .. {sigs[-1]['date']})\n")

# --- offset report (BTC vs bar close at ft) ---
byyear = {}
missing = 0
for s in sigs:
    da = DAYARR.get(s["date"])
    if not da or s["ft"] not in da:
        missing += 1; s["_ok"] = False; continue
    s["_ok"] = True; s["_close"] = da[s["ft"]][3]
    s["_shift"] = round(da[s["ft"]][3] - s["btc"], 2)
    byyear.setdefault(s["date"][:4], []).append(s["_shift"])
print("OFFSET (bar_close - BTC) by year — should be ~constant per contract era:")
for y in sorted(byyear):
    v = byyear[y]
    print(f"  {y}: n={len(v):>4} mean={st.mean(v):>8.2f} med={st.median(v):>8.2f} "
          f"min={min(v):>8.2f} max={max(v):>8.2f} |>2pt from med|={sum(1 for x in v if abs(x-st.median(v))>2)}")
print(f"  (missing bar for {missing} signals — skipped)\n")


def trade(s, T):
    da = DAYARR[s["date"]]; n = DAYMAX[s["date"]]; ft = s["ft"]; long = s["long"]
    sh = s["_shift"]
    lmt = s["lmt"] + sh; stop = s["stop"] + sh          # onto bar scale
    sb = da[ft]; slo, shi = sb[2], sb[1]; away = False; fb = None
    for i in range(ft + 1, n + 1):
        if i not in da: continue
        hi, lo = da[i][1], da[i][2]
        if long:
            if away and lo < lmt: fb = i; break
            if hi > shi: away = True
        else:
            if away and hi > lmt: fb = i; break
            if lo < slo: away = True
    if fb is None:
        return None
    entry = lmt; risk = abs(entry - stop)
    tgt = None if T is None else (entry + T * risk if long else entry - T * risk)
    exitpx = None
    for j in range(fb, n + 1):
        if j not in da: continue
        hi, lo = da[j][1], da[j][2]
        if long:
            if lo <= stop: exitpx = stop; break
            if tgt is not None and hi >= tgt: exitpx = tgt; break
        else:
            if hi >= stop: exitpx = stop; break
            if tgt is not None and lo <= tgt: exitpx = tgt; break
    if exitpx is None:
        last = max(k for k in da); exitpx = da[last][3]
    pts = (exitpx - entry) if long else (entry - exitpx)
    return dict(usd=round(pts * PT - RT, 2), rt=s["rt"], risk=risk)


def metrics(trs):
    n = len(trs)
    if n == 0: return None
    us = [t["usd"] for t in trs]
    net = sum(us); wins = [x for x in us if x > 0]; losses = [x for x in us if x <= 0]
    gw, gl = sum(wins), -sum(losses)
    pf = gw / gl if gl else float("inf")
    eq = pk = dd = 0.0
    for x in us:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    sh = st.mean(us) / st.pstdev(us) if n > 1 and st.pstdev(us) else 0.0
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100*len(wins)/n),
                avg=round(net/n), dd=round(dd), nd=(round(net/dd, 2) if dd else float('inf')), sh=round(sh, 2))


def prow(lab, m):
    if not m: print(f"  {lab:<14} (no trades)"); return
    nd = "inf" if m["nd"] == float("inf") else f"{m['nd']:.2f}"
    print(f"  {lab:<14} {m['n']:>4} {m['net']:>9,} {m['pf']:>5.2f} {m['win']:>4}% "
          f"{m['avg']:>5,} {m['dd']:>9,} {nd:>6} {m['sh']:>6.2f}")

ok = [s for s in sigs if s.get("_ok")]
types = sorted(set(s["rt"] for s in ok))
HDR = f"  {'group':<14} {'n':>4} {'net$':>9} {'PF':>5} {'win':>5} {'$/t':>5} {'maxDD$':>9} {'nd':>6} {'Shrp':>6}"
print(f"BY TYPE — 1 ES, $50/pt, $17.5 RT. Types: {types}\n")
for T, tlab in [(1, "1R"), (2, "2R"), (None, "EOD")]:
    print(f"target = {tlab}"); print(HDR)
    all_tr = [trade(s, T) for s in ok]; all_tr = [t for t in all_tr if t]
    for rt in types:
        prow(f"{rt}", metrics([t for t in all_tr if t["rt"] == rt]))
    prow("ALL", metrics(all_tr))
    # direction
    for lng, lab in [(True, "longs"), (False, "shorts")]:
        prow(lab, metrics([trade(s, T) for s in ok if s["long"] == lng and trade(s, T)]))
    print()
