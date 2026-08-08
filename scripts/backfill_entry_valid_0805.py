"""One-time backfill: flag the 08-05 open-centered trades as entry_valid=False.

Those 4 trades (openic_p/c, openfly_p/c) fired 09:29–09:35 CT — 24–30 min after the
09:05 WAIT not_before — because the live feed was dead until 09:26 (open_spot stamped
09:26). They are STRIKE-AT-FIRE (vertical_dynamic) structures, so a late entry means
the strike was struck off a drifted spot: NOT a clean open-centering datapoint. They
predate the entry_valid tag (S99), so the daemon never flagged them; this corrects the
record so the centering A/B stops counting them. The gexlog trade that day (gx_bcs) is
a FIXED-strike wall order, so its late fill does not corrupt the strike — left valid.

Idempotent. Run once:  .venv/Scripts/python.exe scripts/backfill_entry_valid_0805.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log" / "trades.parquet"
TARGETS = {"openic_p", "openic_c", "openfly_p", "openfly_c"}
NOTE = "late entry +24–30min (feed dead until 09:26; strike struck off drifted spot) — backfilled S99"


def main():
    df = pd.read_parquet(LOG)
    if "entry_valid" not in df.columns:
        df["entry_valid"] = pd.NA
        df["entry_lag_min"] = pd.NA
        df["feed_age_s"] = pd.NA
        df["entry_note"] = pd.NA
    d = df.entry_dt.astype(str).str[:10]
    mask = (d == "2026-08-05") & df.strategy_id.isin(TARGETS)
    print(f"matching 08-05 open trades: {int(mask.sum())}")
    df.loc[mask, "entry_valid"] = False
    df.loc[mask, "entry_note"] = NOTE
    df.to_parquet(LOG, index=False)
    print(df.loc[mask, ["entry_dt", "strategy_id", "pnl", "entry_valid", "entry_note"]].to_string(index=False))
    print("backfilled.")


if __name__ == "__main__":
    main()
