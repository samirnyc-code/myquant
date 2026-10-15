"""analyze_strategy_rollover_stack.py -- follow-up to analyze_strategy_rollover.py.

Tests the STACKED (combined, non-overlapping) effect of the two clearest cut
candidates found there (eodfly_p, gx_bps -- both net-negative AND negative in
2+ of the 3 months on file) plus the POP<0.50 continuous filter, individually
and combined, so the reported deltas aren't additive double-counts.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_strategy_rollover import load_all

d = load_all()
base = d.pnl.sum()
pop = pd.to_numeric(d["pop"], errors="coerce")

rules = {
    "drop eodfly_p only": d.strategy_id == "eodfly_p",
    "drop gx_bps only": d.strategy_id == "gx_bps",
    "drop eodfly_p + gx_bps": d.strategy_id.isin(["eodfly_p", "gx_bps"]),
    "drop eodfly_p + gx_bps + POP<0.50": d.strategy_id.isin(["eodfly_p", "gx_bps"]) | (pop < 0.5),
    "drop eodic_c + openic_c too (4 weakest)": d.strategy_id.isin(
        ["eodfly_p", "gx_bps", "eodic_c", "openic_c"]),
}
print(f"base realized: ${base:,.0f}  n={len(d)}\n")
for label, mask in rules.items():
    kept = d[~mask]
    print(f"{label:42s}  n_skip={mask.sum():3d}  kept_pnl=${kept.pnl.sum():>8,.0f}  "
          f"delta=${kept.pnl.sum()-base:>+7,.0f}  kept_n={len(kept)}  kept_win%={100*(kept.pnl>0).mean():.0f}")
