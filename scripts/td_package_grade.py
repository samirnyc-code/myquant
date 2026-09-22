"""Package-level fill grading (ThetaData suggestion #2) — grade combo trades
(flies/condors/verticals) at the NET PACKAGE price vs the package NBBO built from
the legs' 1-second windows, since IB's per-leg prices are an allocation artifact.

Reads data/thetadata/fill_grade_v2.csv (per-leg fills + each leg's window min/max
bid/ask from td_fill_grade_v2.py). No new TD pulls. Groups by (trade_id, event):
  net_fill      = Σ (fill if SELL else -fill)                 # credit received to open / paid to close
  best_credit   = Σ (max_bid if SELL else -min_ask)          # best obtainable in the window
  worst_credit  = Σ (min_bid if SELL else -max_ask)          # worst obtainable in the window
A package is 'achievable' (not too-good) if net_fill <= best_credit; 'within band' if
worst_credit <= net_fill <= best_credit.
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/thetadata/fill_grade_v2.csv"
OUT = ROOT / "data/thetadata/package_grade_v2.csv"


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
groups = defaultdict(list)
for r in rows:
    groups[(r["trade_id"], r["event"])].append(r)

out, n_ok, n_toogood, n_partial = [], 0, 0, 0
for (tid, ev), legs in groups.items():
    if any(f(l.get("win_max_bid")) is None for l in legs):
        n_partial += 1
        continue  # a leg missing its window — can't grade the package cleanly
    net_fill = best = worst = 0.0
    for l in legs:
        px = f(l["fill"])
        if l["side_action"] == "SELL":
            net_fill += px; best += f(l["win_max_bid"]); worst += f(l["win_min_bid"])
        else:
            net_fill -= px; best -= f(l["win_min_ask"]); worst -= f(l["win_max_ask"])
    achievable = net_fill <= best + 1e-6
    within = (worst - 1e-6) <= net_fill <= (best + 1e-6)
    n_ok += achievable
    n_toogood += (not achievable)
    out.append(dict(trade_id=tid, event=ev, strategy=legs[0]["strategy"], nlegs=len(legs),
                    net_fill=round(net_fill, 2), pkg_worst=round(worst, 2), pkg_best=round(best, 2),
                    achievable=achievable, within_band=within))

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["trade_id", "event", "strategy", "nlegs",
                                       "net_fill", "pkg_worst", "pkg_best", "achievable", "within_band"])
    w.writeheader(); w.writerows(out)

tot = len(out)
within = sum(1 for o in out if o["within_band"])
multi = [o for o in out if o["nlegs"] > 1]
print(f"packages graded: {tot} (+{n_partial} skipped: a leg missing its window)")
print(f"  multi-leg packages: {len(multi)}")
print(f"  achievable (net fill not better than the window's best obtainable): {n_ok}/{tot}")
print(f"  within the package NBBO band [worst,best]: {within}/{tot}")
if n_toogood:
    print(f"  !! too-good (net fill beats the whole-second best — investigate): {n_toogood}")
    for o in out:
        if not o["achievable"]:
            print(f"    {o['trade_id']} {o['event']} {o['strategy']}: net {o['net_fill']} > best {o['pkg_best']}")
print(f"-> {OUT}")
