"""Check, across ALL signals in the NT MyReversals RTH export, which bar+field the
LMT / stop / BTC prices actually come from — to test the 'LMT is from the rev bar'
claim per RevType. Offset is relative to BarNo (ChartSim open-time index):
0 = BarNo, -1 = FT bar (BarNo-1), -2 = rev bar (BarNo-2). Saves a dated CSV."""
import json, glob, collections, csv
from datetime import date as _date

WT = __import__("pathlib").Path(__file__).resolve().parent.parent
f = sorted(glob.glob(str(WT / "data/signals/*RTH*Days.txt")))[-1]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    d, m, y = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, dr=dr, date=f"{y}-{m}-{d}", bn=int(bn),
                     btc=num(btc), stop=num(stop), lmt=num(lmt)))
print("signals", len(sigs))

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.load(open(WT / f"data/annotations/book_review/{dt}.json"))["bars"]
    return cache[dt]

FIELDS = ["O", "H", "L", "C"]
def find(dt, bn, price):
    b = bars(dt); hits = []
    for off in (0, -1, -2, -3):
        i = bn + off
        if 0 <= i < len(b):
            for fi, fn in enumerate(FIELDS):
                if abs(b[i][2 + fi] - price) < 0.13:   # within half a tick
                    hits.append(f"{off}:{fn}")
    return hits

rows = []
for what in ("lmt", "stop", "btc"):
    print(f"\n===== {what.upper()} matches (offset:field) by type =====")
    for rt in ("Trap", "BO", "IB"):
        cnt = collections.Counter(); tot = 0; nomatch = 0
        for s in sigs:
            if s["rt"] != rt:
                continue
            tot += 1
            h = find(s["date"], s["bn"], s[what])
            if not h:
                nomatch += 1
            for k in h:
                cnt[k] += 1
        print(f"  {rt} (n={tot}, no-match={nomatch}): " +
              ", ".join(f"{k}={v}" for k, v in cnt.most_common()))
        rows.append(dict(price=what, type=rt, n=tot, no_match=nomatch,
                         matches="; ".join(f"{k}={v}" for k, v in cnt.most_common())))

out = WT / f"data/signals/lmt_source_check_{_date.today()}.csv"
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["price", "type", "n", "no_match", "matches"])
    w.writeheader(); w.writerows(rows)
print("\nsaved", out)
