"""Diff NT indicator pivots (nt8_pivots.csv) vs Python engine pivots (py_pivots.csv)
over the overlapping sessions. Reports: pivots only-in-NT, only-in-Py, and matched
pivots whose tag/major/majlab differ. Key = (session, bar, side).
"""
import csv
from pathlib import Path
REG = Path(r"c:/Users/Admin/myquant/data/regime")


def load(p, cols):
    d = {}
    for r in csv.DictReader(open(p)):
        d[(r["session"], r["bar"], r["side"])] = {c: r.get(c, "") for c in cols}
    return d

nt = load(REG / "nt8_pivots.csv", ["tag", "major", "majlab"])
py = load(REG / "py_pivots.csv", ["tag", "major", "majlab"])
sess_nt = {k[0] for k in nt}; sess_py = {k[0] for k in py}
overlap = sorted(sess_nt & sess_py)
print(f"NT sessions {len(sess_nt)}, Py sessions {len(sess_py)}, overlap {len(overlap)}: {overlap[0]}..{overlap[-1]}")

ntk = {k for k in nt if k[0] in overlap}; pyk = {k for k in py if k[0] in overlap}
only_nt = sorted(ntk - pyk); only_py = sorted(pyk - ntk); both = sorted(ntk & pyk)
print(f"\npivots (overlap): NT {len(ntk)}  Py {len(pyk)}  matched-bars {len(both)}")
print(f"  only in NT (Py has no pivot there): {len(only_nt)}")
print(f"  only in Py (NT has no pivot there): {len(only_py)}")

difftag = [k for k in both if nt[k]["tag"] != py[k]["tag"]]
diffmaj = [k for k in both if nt[k]["major"] != py[k]["major"]]
difflab = [k for k in both if (nt[k]["majlab"] or "") != (py[k]["majlab"] or "")]
print(f"\nmatched but DIFFER:  tag {len(difftag)}  major-flag {len(diffmaj)}  majlab {len(difflab)}")

def show(title, keys, n=40):
    print(f"\n--- {title} ({len(keys)}) ---")
    for k in keys[:n]:
        print(f"  {k[0]} b{k[1]} {k[2]}:  NT[tag={nt[k]['tag']} maj={nt[k]['major']} lab={nt[k]['majlab']}]  "
              f"PY[tag={py[k]['tag']} maj={py[k]['major']} lab={py[k]['majlab']}]")
    if len(keys) > n: print(f"  ... +{len(keys)-n} more")

show("majlab differs (HH/LL/HL/LH/OH/OL/blank)", difflab)
show("major-flag differs", [k for k in diffmaj if k not in difflab])
show("tag differs", difftag)
def showmiss(title, keys, d, n=30):
    print(f"\n--- {title} ({len(keys)}) ---")
    for k in keys[:n]:
        print(f"  {k[0]} b{k[1]} {k[2]}:  tag={d[k]['tag']} maj={d[k]['major']} lab={d[k]['majlab']}")
    if len(keys) > n: print(f"  ... +{len(keys)-n} more")
showmiss("only in NT (extra pivot vs Py)", only_nt, nt)
showmiss("only in Py (NT missing pivot)", only_py, py)
