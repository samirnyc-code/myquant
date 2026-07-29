"""For the NT-export setups that NEVER filled in-session, how much 'front run' (moving the
limit toward price) would have been needed to fill, as a % of ABR(8) at the signal bar.

Fill model (same as the study): after the signal bar, price must make a fresh away-extreme
beyond the signal bar (reversal dir), then tick THROUGH the limit (long Low<LMT / short High>LMT).

Front run for an unfilled setup = the shortfall between LMT and the CLOSEST the pullback came
after the away-move:
  - SHORT (sell-limit above): shortfall = LMT - max(High) over bars after the away bar
  - LONG  (buy-limit below) : shortfall = min(Low) - LMT over bars after the away bar
Setups that never made the away-move made NO pullback attempt -> reported separately (N/A).
ABR(8) = rolling 8-bar mean of (High-Low) on the CONTINUOUS RTH series (matches the indicator).
Saves a dated CSV.
"""
import json, glob, csv, statistics as st
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent

# continuous ABR(8): concat all day bars in date order, rolling mean of range
abr8 = {}
prev = []
for fp in sorted(glob.glob(str(WT / "data/annotations/book_review/2*.json"))):
    d = json.loads(open(fp).read()); dt = d["date"]
    for bi, bar in enumerate(d["bars"]):
        rng = bar[3] - bar[4]
        prev.append(rng)
        if len(prev) >= 8:
            abr8[(dt, bi)] = sum(prev[-8:]) / 8.0

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
                     time=tm, bn=int(bn), ft=int(bn) - 1, stop=num(stop), lmt=num(lmt)))

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.loads(open(WT / f"data/annotations/book_review/{dt}.json").read())["bars"]
    return cache[dt]

def analyze(s):
    b = bars(s["date"]); n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["long"]
    slo, shi = b[ft][4], b[ft][3]
    away_i = None; filled = False; closest = None
    for i in range(ft + 1, n):
        hi, lo = b[i][3], b[i][4]
        if long:
            if away_i is not None:
                if lo < lmt: filled = True; break
                closest = lo if closest is None else min(closest, lo)   # lowest low after away
            if hi > shi and away_i is None: away_i = i
        else:
            if away_i is not None:
                if hi > lmt: filled = True; break
                closest = hi if closest is None else max(closest, hi)   # highest high after away
            if lo < slo and away_i is None: away_i = i
    if filled:
        return None
    if away_i is None:
        return dict(kind="no_pullback")
    if closest is None:                       # away was the last bar; no post-away bar
        return dict(kind="no_pullback")
    short_pts = (lmt - closest) if not long else (closest - lmt)   # >0 = how far price missed by
    a = abr8.get((s["date"], ft))
    return dict(kind="short", pts=round(short_pts, 2),
                pct=(round(100 * short_pts / a, 1) if a else None), abr8=(round(a, 2) if a else None))

rows = []
never = 0
for k, s in enumerate(sigs, 1):
    r = analyze(s)
    if r is None:
        continue
    never += 1
    rows.append(dict(n=k, date=s["date"], time=s["time"], bar=s["bn"],
                     dir="L" if s["long"] else "S", type=s["rt"], lmt=s["lmt"],
                     kind=r["kind"], shortfall_pts=r.get("pts", ""), abr8=r.get("abr8", ""),
                     frontrun_pct_abr8=r.get("pct", "")))

with open(WT / f"data/signals/csv_frontrun_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

short_rows = [r for r in rows if r["kind"] == "short" and r["frontrun_pct_abr8"] != ""]
nopb = [r for r in rows if r["kind"] == "no_pullback"]
pcts = sorted(r["frontrun_pct_abr8"] for r in short_rows)

print(f"NEVER-FILLED setups: {never} of {len(sigs)}")
print(f"  - made a pullback attempt but fell short: {len(short_rows)}  (front-run measurable)")
print(f"  - never moved away (no pullback at all):  {len(nopb)}  (front-run N/A)\n")

print("FRONT RUN NEEDED to fill (as % of ABR8), for the 'fell short' group:")
if pcts:
    print(f"  median {st.median(pcts):.1f}%   mean {sum(pcts)/len(pcts):.1f}%   "
          f"min {min(pcts):.1f}%   max {max(pcts):.1f}%")
    print("\n  cumulative fills if you front-run by up to X% of ABR8:")
    for thr in (10, 25, 50, 75, 100, 150, 200):
        c = sum(1 for x in pcts if x <= thr)
        print(f"    <= {thr:>3}% ABR8 : {c:>2} / {len(pcts)}  ({100*c/len(pcts):.0f}% of the fell-short group)")

print("\n  per-setup (fell-short), sorted by front-run needed:")
print(f"    {'date':<10} {'b#':>3} {'d':<1} {'type':<4} {'shortfall':>9} {'ABR8':>6} {'%ABR8':>7}")
for r in sorted(short_rows, key=lambda x: x["frontrun_pct_abr8"]):
    print(f"    {r['date']:<10} {r['bar']:>3} {r['dir']:<1} {r['type']:<4} "
          f"{r['shortfall_pts']:>9} {r['abr8']:>6} {r['frontrun_pct_abr8']:>6}%")
print(f"\nsaved data/signals/csv_frontrun_{_date.today()}.csv")
