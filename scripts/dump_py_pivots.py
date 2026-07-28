"""Dump the Python regime engine's pivots (from book_review day JSONs) to a CSV that
matches the NT indicator's nt8_pivots.csv schema, so the two can be diffed to find
HH/LL labelling divergences.  Output: <myquant>/data/regime/py_pivots.csv
Schema: session,bar,side,tag,major,majlab   (bar 1-based to match NT p.Bar+1)
"""
import json, glob, os, csv
from pathlib import Path

DAYS = Path(r"C:/Users/Admin/myquant-regime/data/annotations/book_review")
OUT = Path(r"C:/Users/Admin/myquant/data/regime/py_pivots.csv")
files = sorted(f for f in glob.glob(str(DAYS / "2*.json")) if "index" not in os.path.basename(f))
n = 0
with open(OUT, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["session", "bar", "side", "tag", "major", "majlab"])
    for f in files:
        d = json.load(open(f))
        for p in d.get("pivots", []):
            w.writerow([d["date"], p["b"] + 1, p["side"], p.get("tag", ""),
                        1 if p.get("major") else 0, p.get("lab", "")])
            n += 1
print(f"wrote {OUT}  {n} pivots over {len(files)} sessions")
