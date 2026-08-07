"""Run the Python phase machine on the REAL continuous ticks (not Databento proxy) for
the overlap days, dump pivots, and diff vs the NT indicator export (nt8_pivots.csv).
Goal: confirm real-tick pivots match NT before regenerating all of ChartSim.
"""
import sys, csv
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from regime_second_entry_study import phase_transitions

MYQ = Path(r"c:/Users/Admin/myquant")
TICKS = MYQ / "data" / "ticks_continuous"
NT = MYQ / "data" / "regime" / "nt8_pivots.csv"

# NT sessions to compare
ntrows = list(csv.DictReader(open(NT)))
nt_sessions = sorted({r["session"] for r in ntrows})
overlap = [s for s in nt_sessions if (TICKS / f"{s}.parquet").exists()]
print(f"NT sessions {len(nt_sessions)}; with real ticks: {len(overlap)}: {overlap}")

py_rows = []
for ds in overlap:
    t = pd.read_parquet(TICKS / f"{ds}.parquet", columns=["DateTime", "Price"]).sort_values("DateTime")
    t = t.set_index("DateTime")
    c = t["Price"].resample("5min", label="left", closed="left").last()
    h = t["Price"].resample("5min", label="left", closed="left").max()
    l = t["Price"].resample("5min", label="left", closed="left").min()
    # keep a CONTINUOUS bar array (do NOT drop empty bins — that shifts bar indices vs NT);
    # empty 5m bins carry the prior close as H=L (NT synthesizes a flat bar).
    bars = pd.DataFrame({"H": h, "L": l, "C": c})
    bars["C"] = bars["C"].ffill()
    bars["H"] = bars["H"].fillna(bars["C"]); bars["L"] = bars["L"].fillna(bars["C"])
    bars = bars.reset_index()
    n = len(bars)
    H = bars["H"].values; L = bars["L"].values
    bart0 = bars["DateTime"].iloc[0]
    # map each tick to its bar index
    tt = t.reset_index()
    tt["b"] = ((tt["DateTime"] - bart0).dt.total_seconds() // 300).astype(int)
    tt = tt[(tt["b"] >= 0) & (tt["b"] < n)]
    tP = tt["Price"].values.astype(float); tbar = tt["b"].values.astype(int)
    trace = {}
    phase_transitions(H, L, n, tP, tbar, trace)
    for p in trace["piv"]:
        py_rows.append((ds, p["bar"] + 1, p["side"], p["tag"],
                        1 if p["major"] else 0, p.get("majlab") or ""))

# diff vs NT
nt = {(r["session"], r["bar"], r["side"]): (r["tag"], r["major"], r["majlab"]) for r in ntrows if r["session"] in overlap}
py = {(s, str(b), sd): (tg, str(mj), lab) for (s, b, sd, tg, mj, lab) in py_rows}
both = sorted(set(nt) & set(py))
only_nt = sorted(set(nt) - set(py)); only_py = sorted(set(py) - set(nt))
tagdiff = [k for k in both if nt[k][0] != py[k][0]]
majdiff = [k for k in both if nt[k][1] != py[k][1]]
labdiff = [k for k in both if nt[k][2] != py[k][2]]
print("\nPER-DAY (matched / onlyNT / onlyPy):")
for ds in overlap:
    m = sum(1 for k in both if k[0] == ds); on = sum(1 for k in only_nt if k[0] == ds); op = sum(1 for k in only_py if k[0] == ds)
    flag = "  <== clean" if (on + op) <= 2 else ""
    print(f"  {ds}: {m:3d} / {on:2d} / {op:2d}{flag}")
print(f"\nREAL-TICK Python vs NT (overlap {len(overlap)} days):")
print(f"  NT pivots {len(nt)}  Py pivots {len(py)}  matched-bar {len(both)}")
print(f"  only NT {len(only_nt)}  only Py {len(only_py)}")
print(f"  matched but differ: tag {len(tagdiff)}  major {len(majdiff)}  majlab {len(labdiff)}")
for title, ks in [("tag differ", tagdiff), ("major differ", majdiff),
                  ("majlab differ (excl blank-vs-uppercase-minor)",
                   [k for k in labdiff if nt[k][1] == "1" or py[k][1] == "1"]),
                  ("only NT", only_nt), ("only Py", only_py)]:
    print(f"\n-- {title} ({len(ks)}) --")
    for k in ks[:25]:
        print(f"   {k}: NT{nt.get(k)}  PY{py.get(k)}")
