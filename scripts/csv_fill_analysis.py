"""Fill analysis of the NT MyReversals RTH export LMT prices as PULLBACK entries.

A fill requires a genuine pullback: price must first trade AWAY from the LMT in the
reversal direction (a fresh extreme beyond the signal bar), THEN return to touch the
LMT. The bar immediately after the signal cannot be a fill (price hasn't left the
level yet) -> minimum 2 bars out.

Geometry (verified across all 117): longs place LMT BELOW the signal close (buy-limit,
reversal dir = up); shorts place LMT ABOVE (sell-limit, reversal dir = down). So:
  - LONG : away = a later bar High > signal-bar High; then fill when a bar Low  <= LMT
  - SHORT: away = a later bar Low  < signal-bar Low ; then fill when a bar High >= LMT
Rules:
  - Scan from the bar AFTER the signal/FT bar (FT = BarNo-1). Same session only.
  - bars_to_fill = fill_bar_index - ft_bar_index.
Saves a dated per-signal CSV + prints summary tables.
"""
import json, glob, csv, statistics as st
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
TL = {"BO": "B", "Trap": "T", "IB": "I", "OB": "O"}
f = sorted(glob.glob(str(WT / "data/signals/*RTH*Days.txt")))[-1]

sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    d, m, y = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, dr=dr.lower()[0], date=f"{y}-{m}-{d}",
                     ft=int(bn) - 1, lmt=num(lmt)))

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.load(open(WT / f"data/annotations/book_review/{dt}.json"))["bars"]
    return cache[dt]

rows = []
for s in sigs:
    b = bars(s["date"]); n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["dr"] == "l"
    slow, shigh = b[ft][4], b[ft][3]                 # signal (setup) bar extremes
    btf = None; away = False
    for i in range(ft + 1, n):                       # from the bar AFTER the signal closes
        hi, lo = b[i][3], b[i][4]
        if long:
            if away and lo < lmt:                    # ticks THROUGH the buy-limit (not just touch)
                btf = i - ft; break
            if hi > shigh:                           # price first pushes UP (away), makes the pullback real
                away = True
        else:
            if away and hi > lmt:                    # ticks THROUGH the sell-limit
                btf = i - ft; break
            if lo < slow:                            # price first drops (away)
                away = True
    rows.append(dict(date=s["date"], type=s["rt"], dir="L" if long else "S",
                     ft_bar=ft + 1, lmt=lmt, filled=btf is not None, bars_to_fill=btf))

with open(WT / f"data/signals/csv_fill_analysis_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def summarize(label, rs):
    n = len(rs); fl = [r for r in rs if r["filled"]]; nf = n - len(fl)
    btf = [r["bars_to_fill"] for r in fl]
    med = st.median(btf) if btf else 0
    mean = sum(btf) / len(btf) if btf else 0
    print(f"{label:<10} n={n:<4} filled={len(fl):<4}({100*len(fl)/n:4.0f}%)  "
          f"never={nf:<4}({100*nf/n:4.0f}%)  bars-to-fill med={med:>4.1f} mean={mean:>4.1f} "
          f"min={min(btf) if btf else 0} max={max(btf) if btf else 0}")

print(f"\n=== FILL ANALYSIS - {len(rows)} NT-export signals, limit pullback, same session ===")
print("(fill = pullback ticks THROUGH LMT: long Low<LMT / short High>LMT, after an away-move)\n")
summarize("ALL", rows)
for rt in ("Trap", "BO", "IB"):
    summarize(rt, [r for r in rows if r["type"] == rt])
print()
for d in ("L", "S"):
    summarize("long" if d == "L" else "short", [r for r in rows if r["dir"] == d])

# bars-to-fill distribution buckets
print("\nbars-to-fill distribution (filled only):")
btf = [r["bars_to_fill"] for r in rows if r["filled"]]
buckets = [("1", lambda x: x == 1), ("2-3", lambda x: 2 <= x <= 3), ("4-5", lambda x: 4 <= x <= 5),
           ("6-10", lambda x: 6 <= x <= 10), ("11-20", lambda x: 11 <= x <= 20), (">20", lambda x: x > 20)]
for lab, fn in buckets:
    c = sum(1 for x in btf if fn(x))
    print(f"  {lab:<6} {c:>3} ({100*c/len(btf):4.0f}% of filled)")
print(f"\nsaved data/signals/csv_fill_analysis_{_date.today()}.csv")
