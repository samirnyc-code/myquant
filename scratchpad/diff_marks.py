"""Diff indicator marks (C#) vs research engine (Python) for one day.
  python scratchpad/diff_marks.py YYYY-MM-DD
Reads scratchpad/marks_py_<date>.csv and data/regime/nt8_marks.csv (filtered to date)."""
import sys, pandas as pd
day = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"
py = pd.read_csv(f"scratchpad/marks_py_{day}.csv")
py = py[py.event == "pivot"].copy()
try:
    nt = pd.read_csv("data/regime/nt8_marks.csv")
except FileNotFoundError:
    print("nt8_marks.csv not found — recompile the indicator + run Tick Replay on", day); sys.exit(0)
nt = nt[(nt.event == "pivot") & (nt.date == day)].copy()
CMP = ["minor_tag", "disp", "is_major", "major_lab"]
for df in (py, nt):
    df["key"] = df.bar.astype(str) + df.side
    for c in ["minor_tag", "disp", "major_lab"]:
        df[c] = df[c].fillna("").astype(str)
    df["is_major"] = df["is_major"].fillna(0).astype(int)
m = py.merge(nt, on="key", how="outer", suffixes=("_py", "_nt"), indicator=True)
only_py = m[m._merge == "left_only"]
only_nt = m[m._merge == "right_only"]
both = m[m._merge == "both"]
mism = []
for _, r in both.iterrows():
    diffs = [f"{c}: py={r[c+'_py']!r} nt={r[c+'_nt']!r}" for c in CMP if str(r[c+'_py']) != str(r[c+'_nt'])]
    if diffs: mism.append((r["key"], diffs))
print(f"=== {day}  py_pivots={len(py)}  nt_pivots={len(nt)} ===")
print(f"pivots only in PYTHON engine (missing/moved in indicator): {len(only_py)}")
for k in only_py.key.tolist(): print("   py-only", k)
print(f"pivots only in INDICATOR: {len(only_nt)}")
for k in only_nt.key.tolist(): print("   nt-only", k)
print(f"label mismatches on shared pivots: {len(mism)}")
for k, ds in mism: print(f"   b{k}: " + " | ".join(ds))
if not len(only_py) and not len(only_nt) and not mism:
    print("   ✓ IDENTICAL — port faithful on this day")
