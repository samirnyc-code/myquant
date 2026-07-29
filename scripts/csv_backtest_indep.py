"""NT MyReversals RTH export — INDEPENDENT-trade backtest (each setup is its own trade,
NO opposite-signal cancellation, overlaps allowed).

Entry : pending limit at LMT fills on the pullback tick-through (away-move beyond the signal
        bar, then long Low<LMT / short High>LMT). Order-expiry X = cancel if not filled within
        X bars of the signal (bars_to_fill > X -> no trade). X=None = never expire (session).
Exit  : first of  stop (touch: long Low<=stop / short High>=stop),  target (T*risk, touch),
        EOD (last-bar close). Entry bar included in exit scan, stop priority intrabar (conservative).
        risk = |LMT-stop| = 1R.  Frictionless, R-based (ES $50/pt for the $ column).

PART A: target sweep, ALL + by type (Trap/BO/IB), X=None.
PART B: order-expiry sweep — cancel unfilled limit after X bars — across targets.
Saves dated CSVs.
"""
import json, glob, csv
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
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

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.loads(open(WT / f"data/annotations/book_review/{dt}.json").read())["bars"]
    return cache[dt]

def trade(s, T, X):
    """Return dict(R, why, btf) or None if never filled / expired."""
    b = bars(s["date"]); n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["long"]; stop = s["stop"]
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
    btf = fb - ft
    if X is not None and btf > X:
        return None                              # order pulled before it filled
    entry = lmt; risk = abs(entry - stop)
    tgt = None if T is None else (entry + T * risk if long else entry - T * risk)
    for j in range(fb, n):                        # exit scan (entry bar included, stop priority)
        hi, lo = b[j][3], b[j][4]
        if long:
            if lo <= stop: return dict(R=-1.0, why="stop", btf=btf, risk=risk, rt=s["rt"])
            if tgt is not None and hi >= tgt: return dict(R=T, why="target", btf=btf, risk=risk, rt=s["rt"])
        else:
            if hi >= stop: return dict(R=-1.0, why="stop", btf=btf, risk=risk, rt=s["rt"])
            if tgt is not None and lo <= tgt: return dict(R=T, why="target", btf=btf, risk=risk, rt=s["rt"])
    r = (b[n - 1][5] - entry) / risk * (1 if long else -1)   # EOD close
    return dict(R=round(r, 3), why="eod", btf=btf, risk=risk, rt=s["rt"])

def agg(trs):
    n = len(trs)
    if n == 0: return (0, 0, 0.0, 0.0, 0.0)
    wins = sum(1 for t in trs if t["R"] > 0)
    totR = sum(t["R"] for t in trs)
    usd = sum(t["R"] * t["risk"] * 50 for t in trs)
    return (n, 100 * wins / n, totR / n, totR, usd)

TARGETS = [1, 1.5, 2, 2.5, 3, 4, 5, None]
TL = lambda T: "EOD" if T is None else f"{T}R"

# ---- PART A ----
print("PART A — INDEPENDENT target sweep, by type (no order-expiry, no opp-cancel)\n")
print(f"{'tgt':>5} | {'ALL n':>5} {'win%':>4} {'avgR':>5} {'totR':>7} {'$/ES':>8} | "
      f"{'Trap totR':>9} {'BO totR':>8} {'IB totR':>7}")
rowsA = []
for T in TARGETS:
    trs = [t for t in (trade(s, T, None) for s in sigs) if t]
    n, win, avgR, totR, usd = agg(trs)
    tr_t = agg([t for t in trs if t["rt"] == "Trap"])
    tr_b = agg([t for t in trs if t["rt"] == "BO"])
    tr_i = agg([t for t in trs if t["rt"] == "IB"])
    print(f"{TL(T):>5} | {n:>5} {win:>4.0f} {avgR:>5.2f} {totR:>7.1f} {usd:>8,.0f} | "
          f"{tr_t[3]:>9.1f} {tr_b[3]:>8.1f} {tr_i[3]:>7.1f}")
    rowsA.append(dict(target=TL(T), n=n, win_pct=round(win, 1), avg_R=round(avgR, 3),
                      tot_R=round(totR, 2), usd=round(usd), Trap_totR=round(tr_t[3], 2),
                      BO_totR=round(tr_b[3], 2), IB_totR=round(tr_i[3], 2)))

# ---- PART B: order-expiry sweep ----
XS = [2, 3, 4, 5, 6, 8, 10, 15, 20, None]
XL = lambda X: "none" if X is None else str(X)
print("\n\nPART B — ORDER-EXPIRY sweep (cancel unfilled limit after X bars): totR by target\n")
hdr = "  X\\tgt |" + "".join(f"{TL(T):>7}" for T in TARGETS)
print(hdr); print("  " + "-" * (len(hdr) - 2))
rowsB = []
for X in XS:
    line = f"  {XL(X):>5} |"
    rec = dict(X=XL(X))
    for T in TARGETS:
        trs = [t for t in (trade(s, T, X) for s in sigs) if t]
        totR = sum(t["R"] for t in trs)
        line += f"{totR:>7.1f}"
        rec[TL(T)] = round(totR, 2)
    print(line); rowsB.append(rec)

# trade count by expiry (target-independent — entry is same regardless of T)
print("\n  trades entered by X (fill within X bars):")
for X in XS:
    n = sum(1 for s in sigs if (trade(s, 1, X) is not None))
    print(f"    X={XL(X):>4}: {n} trades")

# ---- PART C: quality by fill speed (X=None, a mid target) ----
print("\n\nPART C — avg R by bars-to-fill bucket (are late fills worse?)  [target = 2R]")
trs = [t for t in (trade(s, 2, None) for s in sigs) if t]
buckets = [("2-3", 2, 3), ("4-5", 4, 5), ("6-10", 6, 10), ("11-20", 11, 20), (">20", 21, 999)]
print(f"    {'fill bars':>9} {'n':>3} {'win%':>5} {'avgR':>6} {'totR':>7}")
for lab, lo, hi in buckets:
    sub = [t for t in trs if lo <= t["btf"] <= hi]
    n, win, avgR, totR, _ = agg(sub)
    print(f"    {lab:>9} {n:>3} {win:>5.0f} {avgR:>6.2f} {totR:>7.1f}")

with open(WT / f"data/signals/csv_indep_targetsweep_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rowsA[0])); w.writeheader(); w.writerows(rowsA)
with open(WT / f"data/signals/csv_indep_expirysweep_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rowsB[0])); w.writeheader(); w.writerows(rowsB)
print(f"\nsaved csv_indep_targetsweep_{_date.today()}.csv + csv_indep_expirysweep_{_date.today()}.csv")
