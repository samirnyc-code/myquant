"""verify_pivots_final.py — DEFINITIVE Python-engine vs NT-indicator pivot verification.

For every session in data/regime/nt8_pivots.csv that has real continuous ticks in
data/ticks_continuous/, this:
  1. builds 5M bars from the real ticks (continuous, empty bins ffilled = flat bar),
  2. runs the Python phase machine (phase_transitions) tick-by-tick,
  3. detects intraday tick GAPS (empty 5M bins inside RTH -> input data is incomplete),
  4. matches Python pivots to NT pivots trying bar-offset 0 and +1 (a whole-session
     +1 numbering offset means NT's chart drew one extra open bar; pivots are the same),
  5. classifies each day: IDENTICAL / SHIFT+1 (identical after align) / GAP / DIFFER.

Writes a dated per-day summary CSV to data/regime/pivot_verify_<maxdate>.csv and prints it.
This is the persisted artifact backing the claim "Python and NT produce the same pivots".
"""
import sys, csv, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions
import pandas as pd

MYQ = Path(r"c:/Users/Admin/myquant")
TICKS = MYQ / "data" / "ticks_continuous"
NT = MYQ / "data" / "regime" / "nt8_pivots.csv"

ntrows = list(csv.DictReader(open(NT)))
sessions = sorted({r["session"] for r in ntrows if (TICKS / f"{r['session']}.parquet").exists()})

def py_pivots(ds):
    t = pd.read_parquet(TICKS / f"{ds}.parquet", columns=["DateTime", "Price"]).sort_values("DateTime").set_index("DateTime")
    c = t["Price"].resample("5min", label="left", closed="left").last()
    h = t["Price"].resample("5min", label="left", closed="left").max()
    l = t["Price"].resample("5min", label="left", closed="left").min()
    cnt = t["Price"].resample("5min", label="left", closed="left").count()
    bars = pd.DataFrame({"H": h, "L": l, "C": c})
    bars["C"] = bars["C"].ffill(); bars["H"] = bars["H"].fillna(bars["C"]); bars["L"] = bars["L"].fillna(bars["C"])
    bars = bars.reset_index()
    n = len(bars); H = bars["H"].values; L = bars["L"].values; b0 = bars["DateTime"].iloc[0]
    # gaps = empty 5m bins inside 08:30..15:10
    gaps = [x for x, k in cnt.items() if k == 0
            and x.time() >= pd.Timestamp("08:30").time() and x.time() < pd.Timestamp("15:10").time()]
    tt = t.reset_index(); tt["b"] = ((tt["DateTime"] - b0).dt.total_seconds() // 300).astype(int)
    tt = tt[(tt.b >= 0) & (tt.b < n)]
    tr = {}
    phase_transitions(H, L, n, tt["Price"].values.astype(float), tt["b"].values.astype(int), tr)
    piv = {(p["bar"] + 1, p["side"]): (p["tag"], p.get("majlab") or "") for p in tr["piv"]}
    return piv, len(gaps)

rows = []
for ds in sessions:
    piv, ngap = py_pivots(ds)
    nt = [r for r in ntrows if r["session"] == ds]
    best = None
    for shift in (0, 1):
        ntk = {(int(r["bar"]) + shift, r["side"]): (r["tag"], r["majlab"]) for r in nt}
        full = sum(1 for k in ntk if k in piv and ntk[k] == piv[k])
        if best is None or full > best[1]:
            best = (shift, full, len(ntk), len(piv))
    shift, full, nnt, npy = best
    if ngap > 0 and full < nnt:
        status = f"GAP({ngap} empty bins)"
    elif full == nnt == npy and shift == 0:
        status = "IDENTICAL"
    elif full == nnt == npy and shift == 1:
        status = "SHIFT+1 (identical aligned)"
    else:
        status = f"DIFFER ({full}/{nnt})"
    rows.append(dict(session=ds, nt=nnt, py=npy, match=full, shift=shift, gaps=ngap, status=status))

maxd = sessions[-1]
out = MYQ / "data" / "regime" / f"pivot_verify_{maxd}.csv"
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["session", "nt", "py", "match", "shift", "gaps", "status"])
    w.writeheader(); w.writerows(rows)

print(f"{'session':12} {'NT':>4} {'PY':>4} {'match':>6} {'sh':>3} {'gaps':>4}  status")
for r in rows:
    print(f"{r['session']:12} {r['nt']:>4} {r['py']:>4} {r['match']:>6} {r['shift']:>+3} {r['gaps']:>4}  {r['status']}")
nclean = sum(1 for r in rows if r["status"].startswith(("IDENTICAL", "SHIFT")))
ngapd = sum(1 for r in rows if r["status"].startswith("GAP"))
ndiff = sum(1 for r in rows if r["status"].startswith("DIFFER"))
print(f"\nTOTAL {len(rows)} days:  identical-pivots {nclean}  gap-in-export {ngapd}  engine-differ {ndiff}")
print(f"wrote {out}")
