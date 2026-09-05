"""Remove the STMR strategy from the trade book entirely (user decision 2026-09-05).

STMR (bps_stmr) is being retired from the sim book / results / automations; a
separate SPY-call tool will replace it once a reliable live SPY options quote
source exists. This drops ALL bps_stmr rows (sim + real_paper) from
trades.parquet after a timestamped backup. Idempotent: re-running finds none.
"""
import datetime as dt
import shutil
from pathlib import Path

import pandas as pd

PARQ = Path("data/options_log/trades.parquet")
df = pd.read_parquet(PARQ)
mask = df["strategy_id"].astype(str) == "bps_stmr"
print(f"bps_stmr rows found: {int(mask.sum())}")
if mask.any():
    print(df.loc[mask, ["trade_id", "source", "entry_dt", "exit_dt", "pnl"]].to_string(index=False))
    bak = PARQ.with_suffix(f".parquet.bak_{dt.datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(PARQ, bak)
    print(f"backup -> {bak}")
    df = df[~mask].reset_index(drop=True)
    df.to_parquet(PARQ, index=False)
    print(f"removed {int(mask.sum())} rows; book now {len(df)} trades; saved {PARQ}")
else:
    print("nothing to remove")

after = pd.read_parquet(PARQ)
print("\nstrategy_id counts after:")
print(after["strategy_id"].astype(str).value_counts().to_string())
