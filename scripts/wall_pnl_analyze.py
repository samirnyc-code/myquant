"""Analyze wall_pnl_3way.csv HONESTLY: (1) audit whether the day-sets are constant
across sources, (2) compare sources ONLY on common days, (3) break down by
strategy (bps / bcs) with metrics. No TD pulls — reads the CSV.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data/options_sim/wall_pnl_3way.csv"
SRC = ["gx", "td", "mq", "fx"]
LAB = {"gx": "gexlog", "td": "ThetaData", "mq": "MenthorQ", "fx": "fixed-off"}


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
for r in rows:
    for k in r:
        if k != "date":
            r[k] = f(r[k])

# ---- 1. constancy audit ----
print(f"total days in file: {len(rows)}")
priced = {s: [r for r in rows if r.get(f"{s}_pnl") is not None] for s in SRC}
print("\nDAY-SET AUDIT (why totals weren't comparable):")
for s in SRC:
    itm = sum(1 for r in rows if r.get(f"{s}_otm") is False)
    print(f"  {LAB[s]:>10}: priced {len(priced[s]):>3}/{len(rows)}   ITM-skipped {itm:>2}")


def metrics(subset, s, leg):
    v = [r[f"{s}_{leg}"] for r in subset if r.get(f"{s}_{leg}") is not None]
    if not v:
        return None
    wins = sum(1 for x in v if x > 0)
    return dict(n=len(v), total=sum(v), avg=sum(v) / len(v),
                win=100 * wins / len(v), best=max(v), worst=min(v))


def show(subset, srcs, title):
    print(f"\n{'='*74}\n{title}  (n={len(subset)} common days)\n{'='*74}")
    print(f"{'source':>10} {'leg':>5} {'total$':>9} {'avg$':>7} {'win%':>6} {'best$':>7} {'worst$':>8}")
    for s in srcs:
        for leg in ("bps", "bcs", "pnl"):
            m = metrics(subset, s, leg)
            if m:
                nm = {"bps": "BullPut", "bcs": "BearCall", "pnl": "TOTAL"}[leg]
                print(f"{LAB[s]:>10} {nm:>5} {m['total']:>9,.0f} {m['avg']:>7,.0f} "
                      f"{m['win']:>5.0f}% {m['best']:>7,.0f} {m['worst']:>8,.0f}")
        print()


# ---- 2. gexlog vs ThetaData on COMMON days ----
common_gt = [r for r in rows if r.get("gx_pnl") is not None and r.get("td_pnl") is not None]
show(common_gt, ["gx", "td"], "gexlog vs ThetaData — CONSTANT day-set")
same = sum(1 for r in common_gt if r["gx_pw"] == r["td_pw"] and r["gx_cw"] == r["td_cw"])
gt_gap = sum(r["gx_pnl"] for r in common_gt) - sum(r["td_pnl"] for r in common_gt)
print(f"  identical-wall days: {same}/{len(common_gt)}  (P&L identical on those)")
print(f"  net gap (gx-td) over the SAME days: {gt_gap:+,.0f}")

# ---- 3. all-four on FULLY common days ----
common_all = [r for r in rows if all(r.get(f"{s}_pnl") is not None for s in SRC)]
show(common_all, SRC, "All 4 sources — FULLY common day-set")
# strike-distance on the common set (the width confound)
import statistics as st
print("  avg short-strike distance from spot (points):")
for s in SRC:
    pd = [r["spot"] - r[f"{s}_pw"] for r in common_all]
    cd = [r[f"{s}_cw"] - r["spot"] for r in common_all]
    print(f"    {LAB[s]:>10}: put {st.mean(pd):.0f}  call {st.mean(cd):.0f}")
