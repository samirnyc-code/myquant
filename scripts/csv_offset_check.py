"""Investigate a possible contract-rollover / price OFFSET between the NT export and ChartSim.

BTCPrice in the export = the signal (FT) bar's CLOSE. So for each setup,
  diff = BTCPrice - ChartSim_bars[FT].close
should be ~0 if the export and ChartSim are the same contract. A non-zero, consistent diff
before a roll date (and ~0 after) = a calendar-spread offset from ChartSim rolling JUN->SEP.
Also checks LMT vs the FT-bar range location. Prints per-date means; saves CSV.
"""
import json, glob, csv, statistics as st
from pathlib import Path
from collections import defaultdict
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
f = next(x for x in glob.glob(str(WT / "data/signals/*.txt"))
         if "LMTPrice" in open(x, encoding="utf-8").read(400))   # the 9-col export with the limit
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    d, m, y = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(date=f"{y}-{m}-{d}", ft=int(bn) - 1, btc=num(btc), lmt=num(lmt), stop=num(stop)))

print(f"file: {Path(f).name}\nparsed {len(sigs)} setups\n")

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.loads((WT / f"data/annotations/book_review/{dt}.json").read_text())["bars"]
    return cache[dt]

byd = defaultdict(list)
rows = []
for s in sigs:
    b = bars(s["date"])
    if s["ft"] >= len(b):
        continue
    ftbar = b[s["ft"]]
    diff = round(s["btc"] - ftbar[5], 2)                      # BTC vs FT close
    byd[s["date"]].append(diff)
    rows.append(dict(date=s["date"], ft_bar=s["ft"] + 1, btc=s["btc"], ft_close=ftbar[5],
                     diff=diff, lmt=s["lmt"], ft_low=ftbar[4], ft_high=ftbar[3]))

print(f"{'date':<11} {'n':>2}  {'meanDiff':>8}  {'maxAbs':>7}   (BTC - ChartSim FT-close; ~0 = aligned)")
for dt in sorted(byd):
    v = byd[dt]
    flag = "   <== OFFSET" if abs(st.mean(v)) > 0.5 else ""
    print(f"{dt:<11} {len(v):>2}  {st.mean(v):>8.2f}  {max(abs(x) for x in v):>7.2f}{flag}")

alld = [r["diff"] for r in rows]
print(f"\nALL setups: mean diff {st.mean(alld):.2f}, "
      f"within +-0.25 (1 tick): {sum(1 for x in alld if abs(x) <= 0.25)}/{len(alld)}, "
      f"abs>1pt: {sum(1 for x in alld if abs(x) > 1)}")

with open(WT / f"data/signals/csv_offset_check_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f"\nsaved data/signals/csv_offset_check_{_date.today()}.csv")
