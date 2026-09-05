"""One-off backfill: relabel STMR trade grades 'A/B' -> 'n/a'.

STMR (bps_stmr) fires on one fixed condition, so it carries no entry-quality
grade. Historic rows were hardcoded 'A/B' (options_sim_daemon), which polluted
the dashboard grade-calibration panel. This rewrites them to 'n/a' to match the
source going forward. Writes a timestamped backup first, prints before/after.

Idempotent: re-running finds 0 'A/B' rows and no-ops.
"""
import datetime as dt
import shutil
from pathlib import Path

import pandas as pd

PARQ = Path("data/options_log/trades.parquet")
df = pd.read_parquet(PARQ)

mask = df["grade"].astype(str).str.strip() == "A/B"
print(f"rows with grade 'A/B': {int(mask.sum())}")
if mask.any():
    print(df.loc[mask, ["trade_id", "strategy_id", "grade", "pnl"]].to_string(index=False))

if mask.any():
    # verify they are all STMR before touching anything
    non_stmr = df.loc[mask & (df["strategy_id"] != "bps_stmr")]
    if len(non_stmr):
        raise SystemExit(f"ABORT: {len(non_stmr)} 'A/B' rows are NOT bps_stmr — inspect first:\n"
                         f"{non_stmr[['trade_id','strategy_id']].to_string(index=False)}")
    bak = PARQ.with_suffix(f".parquet.bak_{dt.datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(PARQ, bak)
    print(f"backup -> {bak}")
    df.loc[mask, "grade"] = "n/a"
    df.to_parquet(PARQ, index=False)
    print(f"rewrote {int(mask.sum())} rows -> 'n/a'; saved {PARQ}")
else:
    print("nothing to do")

# confirm
after = pd.read_parquet(PARQ)
print("\ngrade counts after:")
print(after["grade"].astype(str).str.strip().value_counts().to_string())
