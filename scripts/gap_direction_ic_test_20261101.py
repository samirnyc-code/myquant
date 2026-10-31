"""Test: does the EOD-anchored condor carry gap risk that the Open-anchored
condor doesn't, because EOD strikes are set from the PRIOR close (before the
gap is known) while Open strikes are set from TODAY's open (after the gap is
known, so the gap is already priced in)?

Mechanism being tested: on a gap-DOWN day, the EOD condor's short put
(struck at prior_close - EM) sits closer to where price actually opens than
it would on a flat day -- less real buffer than the EM width implies. The
Open condor's short put (struck at open - EM) always has the full EM width of
real buffer, regardless of the gap, because it's measured from where trading
actually starts. Mirror logic for gap-UP days and the call side.

If this mechanism is real: EOD-anchored puts should underperform Open-
anchored puts specifically on gap-DOWN days (and the gap should matter less
or not at all on gap-UP/flat days for the put side). Mirror for calls on
gap-UP days.

Only looks at the 'ic' width (eodic/openic) -- the fly's short strike isn't
EM-based at all, so this mechanism doesn't apply to it.

Run: .venv/Scripts/python.exe scripts/gap_direction_ic_test_20261101.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gexlog_guidance_recalc_20261031 import load_trades, load_brief_days  # noqa: E402

OUT_DIR = ROOT / "data" / "options_log" / "_analysis"


def main():
    trades = load_trades()
    brief = load_brief_days()

    ic = trades[trades["width"] == "ic"].copy()
    day_side = ic.groupby(["date", "anchor", "side"])["pnl"].sum().reset_index()
    wide = day_side.pivot_table(index="date", columns=["anchor", "side"], values="pnl")
    wide.columns = [f"{a}_{s}" for a, s in wide.columns]

    b = brief[["date", "spx_open", "prior_close", "expectedMove"]].copy()
    b["gap"] = b["spx_open"] - b["prior_close"]
    b["gap_pct_of_em"] = (b["gap"] / b["expectedMove"]).round(3)  # signed: negative = gap down

    m = wide.reset_index().merge(b, on="date", how="inner").dropna(subset=["gap_pct_of_em"])

    bins = [-10, -0.3, -0.1, 0.1, 0.3, 10]
    labels = ["gap down >30%EM", "gap down 10-30%EM", "flat (<10%EM)", "gap up 10-30%EM", "gap up >30%EM"]
    m["gap_dir_bucket"] = pd.cut(m["gap_pct_of_em"], bins=bins, labels=labels)

    put_cols = [c for c in ["eod_put", "open_put"] if c in m.columns]
    call_cols = [c for c in ["eod_call", "open_call"] if c in m.columns]

    put_table = m.groupby("gap_dir_bucket")[put_cols].agg(["count", "mean", "sum"])
    call_table = m.groupby("gap_dir_bucket")[call_cols].agg(["count", "mean", "sum"])

    print("=== PUT side (eodic_p vs openic_p), by gap direction/size ===")
    print(put_table.to_string())
    print("\n=== CALL side (eodic_c vs openic_c), by gap direction/size ===")
    print(call_table.to_string())

    # focused test: gap-DOWN days specifically, eod_put vs open_put
    down = m[m["gap_pct_of_em"] < -0.1]
    up = m[m["gap_pct_of_em"] > 0.1]
    print(f"\n=== Focused: gap-DOWN days (n={len(down)}) ===")
    print(f"eod_put total/avg: {down['eod_put'].sum():.2f} / {down['eod_put'].mean():.2f}")
    print(f"open_put total/avg: {down['open_put'].sum():.2f} / {down['open_put'].mean():.2f}")
    print(f"\n=== Focused: gap-UP days (n={len(up)}) ===")
    print(f"eod_call total/avg: {up['eod_call'].sum():.2f} / {up['eod_call'].mean():.2f}")
    print(f"open_call total/avg: {up['open_call'].sum():.2f} / {up['open_call'].mean():.2f}")

    m.to_csv(OUT_DIR / "gap_direction_ic_test_20261101.csv", index=False)


if __name__ == "__main__":
    main()
