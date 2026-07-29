"""NT MyReversals RTH export — INDEPENDENT-trade backtest reported in $ (the usual metrics).

Each setup is its own trade (no opposite-cancel, overlaps allowed).
Entry : pullback tick-through at LMT (away-move beyond signal bar, then long Low<LMT / short High>LMT).
Exit  : first of stop (touch) / target (T*risk, touch) / EOD close. Entry bar included, stop priority.
Sizing: 1 ES contract, $50/pt.  Cost: $30 round-turn (commission + ~1 tick slippage), like the 2E book.
Metrics: Net$, PF, Win%, avg$/trade, MaxDD$ (equity peak-to-trough, trades in entry order), Net/DD, Sharpe(per-trade).
Saves dated CSVs.
"""
import json, glob, csv, statistics as st
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
PT = 50.0        # $/point, 1 ES
RT = 17.5        # round-turn cost $ (commission + slippage)
f = sorted(glob.glob(str(WT / "data/signals/*RTH*Days.txt")))[-1]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, stop=num(stop), lmt=num(lmt)))
sigs.sort(key=lambda s: (s["date"], s["ft"]))     # entry order for the equity curve
import sys
CUTOFF = sys.argv[1] if len(sys.argv) > 1 else None     # e.g. "2026-06-16" -> keep dates strictly after
if CUTOFF:
    n0 = len(sigs); sigs = [s for s in sigs if s["date"] > CUTOFF]
    print(f"[FILTER: {len(sigs)}/{n0} setups, dates AFTER {CUTOFF}]\n")

cache = {}
def day(dt):
    if dt not in cache:
        cache[dt] = json.loads(open(WT / f"data/annotations/book_review/{dt}.json").read())
    return cache[dt]

def trade(s, T):
    """Return net $ for one ES contract, or None if never filled."""
    d = day(s["date"]); b = d["bars"]; n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["long"]; stop = s["stop"]
    slo, shi = b[ft][4], b[ft][3]; away = False; fb = None
    for i in range(ft + 1, n):
        hi, lo = b[i][3], b[i][4]
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
    for j in range(fb, n):
        hi, lo = b[j][3], b[j][4]
        if long:
            if lo <= stop: exitpx = stop; break
            if tgt is not None and hi >= tgt: exitpx = tgt; break
        else:
            if hi >= stop: exitpx = stop; break
            if tgt is not None and lo <= tgt: exitpx = tgt; break
    if exitpx is None:
        exitpx = b[n - 1][5]
    pts = (exitpx - entry) if long else (entry - exitpx)
    return round(pts * PT - RT, 2)

def metrics(pnls):
    n = len(pnls)
    if n == 0:
        return None
    net = sum(pnls)
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    gw = sum(wins); gl = -sum(losses)
    pf = (gw / gl) if gl else float("inf")
    eq = 0.0; peak = 0.0; maxdd = 0.0
    for x in pnls:
        eq += x; peak = max(peak, eq); maxdd = max(maxdd, peak - eq)
    sharpe = (st.mean(pnls) / st.pstdev(pnls)) if n > 1 and st.pstdev(pnls) else 0.0
    return dict(n=n, net=round(net), pf=round(pf, 2), win=round(100 * len(wins) / n),
                avg=round(net / n), maxdd=round(maxdd),
                nd=(round(net / maxdd, 2) if maxdd else float("inf")), sharpe=round(sharpe, 2))

def run(T, filt=None):
    pnls = []
    for s in sigs:
        if filt and not filt(s): continue
        v = trade(s, T)
        if v is not None: pnls.append(v)
    return metrics(pnls)

def prow(lab, m):
    if not m:
        print(f"  {lab:<20} (no trades)"); return
    nd = "inf" if m["nd"] == float("inf") else f"{m['nd']:.2f}"
    print(f"  {lab:<20} {m['n']:>3} {m['net']:>8,} {m['pf']:>5.2f} {m['win']:>4}% "
          f"{m['avg']:>6,} {m['maxdd']:>8,} {nd:>6} {m['sharpe']:>6.2f}")

TARGETS = [1, 1.5, 2, 2.5, 3, 4, 5, None]
TL = lambda T: "EOD" if T is None else f"{T}R"
HDR = f"  {'config':<20} {'n':>3} {'net$':>8} {'PF':>5} {'win':>5} {'$/tr':>6} {'maxDD$':>8} {'net/DD':>6} {'Sharpe':>6}"

print(f"ES 1 contract, $50/pt, ${RT:g} round-turn cost. maxDD$ = equity peak-to-trough (entry order).\n")
print("TARGET SWEEP (all types, independent trades)"); print(HDR)
sweep = []
for T in TARGETS:
    m = run(T); prow(TL(T), m)
    if m: sweep.append(dict(config=TL(T), **m))

print("\nBY TYPE @ 1R target"); print(HDR)
for rt in ("Trap", "BO", "IB"):
    prow(f"{rt} @ 1R", run(1, lambda s, rt=rt: s["rt"] == rt))
prow("ALL @ 1R", run(1))
# direction split @ 1R
for lng, lab in [(True, "longs @ 1R"), (False, "shorts @ 1R")]:
    prow(lab, run(1, lambda s, lng=lng: s["long"] == lng))

print("\nBY TYPE @ EOD hold"); print(HDR)
for rt in ("Trap", "BO", "IB"):
    prow(f"{rt} only", run(None, lambda s, rt=rt: s["rt"] == rt))

print("\nHEADLINE CONFIGS"); print(HDR)
def gate_dropTrap(s): return s["rt"] != "Trap"
def gate_againstMA(s):
    d = day(s["date"]); sma = d.get("sma20"); c = d["bars"][s["ft"]][5]
    return sma is not None and ((c < sma) if s["long"] else (c > sma))
prow("ALL @ EOD", run(None))
prow("dropTrap @ EOD", run(None, gate_dropTrap))
prow("dropTrap @ 1R", run(1, gate_dropTrap))
prow("BO+IB againstMA EOD", run(None, lambda s: gate_dropTrap(s) and gate_againstMA(s)))
prow("BO only @ EOD", run(None, lambda s: s["rt"] == "BO"))
prow("IB only @ EOD", run(None, lambda s: s["rt"] == "IB"))

with open(WT / f"data/signals/csv_dollars_sweep_{_date.today()}.csv", "w", newline="") as fh:
    if sweep:
        w = csv.DictWriter(fh, fieldnames=list(sweep[0])); w.writeheader(); w.writerows(sweep)
print(f"\nsaved data/signals/csv_dollars_sweep_{_date.today()}.csv")
