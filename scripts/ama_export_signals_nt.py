#!/usr/bin/env python3
"""
ama_export_signals_nt.py
Export AMA Breakouts PB6 signals to a CSV file for the AMASignalOverlay NT8 indicator.

The indicator reads from:
    %USERPROFILE%\\Documents\\NinjaTrader 8\\ama_signals_{TAG}.csv

This script writes to:
    data/nt_import/ama_signals_{TAG}.csv          (always)
    ~/Documents/NinjaTrader 8/ama_signals_{TAG}.csv  (if NT8 dir exists on this machine)

CSV column layout (matches AMASignalOverlay.cs field order):
    0  SignalNum       8  StopPrice       14 PnL_R
    1  SignalType      9  TargetMode      15 Date
    2  Direction       10 TargetMult      16 FilterStatus
    3  SignalDateTime  11 TargetPoints
    4  EntryBarNum     12 SBRange   ← signal bar H-L (pts)
    5  SignalPrice     13 EBRange   ← entry bar H-L (pts)
    6  StopMode
    7  StopOffset

Usage examples:
    python scripts/ama_export_signals_nt.py
    python scripts/ama_export_signals_nt.py --tag 2024 --from 2024-01-01 --to 2024-12-31
    python scripts/ama_export_signals_nt.py --types BO FT --stop-offset 2 --target-mult 1.5
    python scripts/ama_export_signals_nt.py --results data/sim_results.csv --tag full
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ama_setups import AMAConfig, AMATradeParams, detect, to_signal_rows

BARS_DIR = REPO / "data" / "bars"
OUT_DIR  = REPO / "data" / "nt_import"
NT8_DIR  = Path.home() / "Documents" / "NinjaTrader 8"
TICK     = 0.25

# Map CLI type names → AMA signal integer codes used by to_signal_rows()
# BO+FT: ±1 code with include_ft=True (FT is a flag, not a separate code)
# OB includes OB_Doji (code ±4) automatically
TYPE_CODES: dict[str, tuple[int, ...]] = {
    "BO":    (1, -1),
    "FT":    (),        # controlled via include_ft flag, not a signal code
    "OB":    (3, -3, 4),
    "BigBO": (5, -5),
    "CX":    (2, -2),
}


CONT_PATH = BARS_DIR / "_continuous.parquet"


def load_bars() -> pd.DataFrame:
    """Load the stitched continuous contract. Falls back to individual-file concat
    only if _continuous.parquet hasn't been built yet."""
    if CONT_PATH.exists():
        bars = pd.read_parquet(CONT_PATH)
        bars = bars.drop(columns=["Contract"], errors="ignore")
        bars = bars.sort_values("DateTime").reset_index(drop=True)
        return bars
    # Fallback: concat individual contract files (pre-continuous-build state)
    files = sorted(f for f in BARS_DIR.glob("*.parquet")
                   if not f.name.startswith("_"))
    if not files:
        raise FileNotFoundError(f"No bar files found in {BARS_DIR}")
    bars = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    bars = bars.drop_duplicates("DateTime", keep="last")
    bars = bars.sort_values("DateTime").reset_index(drop=True)
    return bars


def add_bar_ranges(signals: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """
    Add SBRange (signal bar High-Low) and EBRange (entry/fill bar High-Low).

    SignalDateTime = the signal bar's label (S60: close-labelled; matches
    bars.DateTime). Entry bar label = SignalDateTime + 5 min (the next bar) —
    relative arithmetic between labels is convention-invariant.
    """
    # Continuous contract has no duplicates; index directly
    bar_hl = bars.set_index("DateTime")[["High", "Low"]]

    sig_dt   = pd.to_datetime(signals["SignalDateTime"])
    entry_dt = sig_dt + pd.Timedelta(minutes=5)

    sb_high = sig_dt.map(bar_hl["High"])
    sb_low  = sig_dt.map(bar_hl["Low"])
    eb_high = entry_dt.map(bar_hl["High"])
    eb_low  = entry_dt.map(bar_hl["Low"])

    signals = signals.copy()
    signals["SBRange"] = (sb_high - sb_low).round(2)
    signals["EBRange"] = (eb_high - eb_low).round(2)   # NaN for last bar in dataset
    return signals


def join_pnl(signals: pd.DataFrame, results_path: str) -> pd.DataFrame:
    """
    Optionally join simulation PnL_R from a results CSV.
    The results CSV must have at least: SignalNum, PnL_R columns.
    """
    res = pd.read_csv(results_path)
    if "SignalNum" not in res.columns or "PnL_R" not in res.columns:
        print(f"  WARNING: results file missing SignalNum or PnL_R — skipping PnL join")
        return signals
    res = res[["SignalNum", "PnL_R"]].drop_duplicates("SignalNum")
    signals = signals.merge(res, on="SignalNum", how="left", suffixes=("_old", ""))
    if "PnL_R_old" in signals.columns:
        signals.drop(columns=["PnL_R_old"], inplace=True)
    print(f"  Joined PnL_R for {res['SignalNum'].nunique()} signals")
    return signals


def build_signal_codes(types: list[str]) -> tuple[tuple[int, ...], bool]:
    """Convert CLI type list to (signal_codes_tuple, include_ft)."""
    codes: list[int] = []
    # BO+FT is one setup — "BO" and "FT" both mean include BO+FT setups.
    include_ft = "BO" in types or "FT" in types
    for t in types:
        codes.extend(TYPE_CODES.get(t, ()))
    if not codes and not include_ft:
        # Default: everything
        codes = [1, -1, 3, -3, 4, 5, -5]
        include_ft = True
    # BO codes must be present when BO+FT setups are requested
    if include_ft and 1 not in codes:
        codes.extend([1, -1])
    return tuple(set(codes)), include_ft


def export(args: argparse.Namespace) -> None:
    print("Loading bar data...")
    bars = load_bars()
    print(f"  {len(bars):,} bars  "
          f"{bars['DateTime'].min().date()} — {bars['DateTime'].max().date()}")

    cfg = AMAConfig()
    tp  = AMATradeParams(
        stop_offset_ticks=args.stop_offset,
        target_mode=args.target_mode,
        target_mult=args.target_mult,
    )

    print("Detecting signals...")
    detected = detect(bars, cfg)

    sig_codes, include_ft = build_signal_codes(args.types)
    print(f"  Signal codes: {sorted(sig_codes)}  include_ft={include_ft}")

    print("Building signal rows...")
    signals = to_signal_rows(
        detected, bars, tp,
        signal_types=sig_codes,
        include_ft=include_ft,
        include_flip=False,
    )
    print(f"  {len(signals):,} signals before date filter")

    # Date filter
    if args.from_date:
        signals = signals[signals["Date"].astype(str) >= args.from_date]
    if args.to_date:
        signals = signals[signals["Date"].astype(str) <= args.to_date]
    signals = signals.reset_index(drop=True)
    print(f"  {len(signals):,} signals after date filter")

    # Add bar geometry columns
    print("Adding SBRange / EBRange...")
    signals = add_bar_ranges(signals, bars)

    # PnL_R — empty unless a results file is provided
    if args.results:
        print(f"Joining PnL from {args.results}...")
        signals = join_pnl(signals, args.results)
    if "PnL_R" not in signals.columns:
        signals["PnL_R"] = np.nan

    # ── Build export DataFrame in exact column order the NT8 indicator expects ──
    out = pd.DataFrame({
        "SignalNum":      signals["SignalNum"],
        "SignalType":     signals["SignalType"],
        "Direction":      signals["Direction"],
        "SignalDateTime": pd.to_datetime(signals["SignalDateTime"])
                            .dt.strftime("%Y-%m-%d %H:%M:%S"),
        "EntryBarNum":    signals["EntryBarNum"],
        "SignalPrice":    signals["SignalPrice"],
        "StopMode":       signals["StopMode"],
        "StopOffset":     signals["StopOffset"],
        "StopPrice":      signals["StopPrice"],
        "TargetMode":     signals["TargetMode"],
        "TargetMult":     signals["TargetMult"],
        "TargetPoints":   signals["TargetPoints"],
        "SBRange":        signals["SBRange"],
        "EBRange":        signals["EBRange"],
        "PnL_R":          signals["PnL_R"].round(4),
        "Date":           signals["Date"],
        "FilterStatus":   signals["FilterStatus"],
    })

    filename = f"ama_signals_{args.tag}.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = OUT_DIR / filename
    out.to_csv(local_path, index=False, float_format="%.4g", na_rep="")
    print(f"\nWritten: {local_path}  ({len(out):,} rows)")

    if not args.no_copy:
        if NT8_DIR.exists():
            nt_path = NT8_DIR / filename
            shutil.copy(local_path, nt_path)
            print(f"Copied:  {nt_path}")
        else:
            print(f"NT8 dir not found ({NT8_DIR}) — skipping auto-copy")
            print(f"  Manual copy:  cp '{local_path}' '/path/to/NinjaTrader 8/{filename}'")

    # Summary
    print("\nSignals by type and direction:")
    summary = signals.groupby(["SignalType", "Direction"]).size().rename("count")
    print(summary.to_string())
    print(f"\nTotal: {len(signals):,}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Export AMA Breakouts PB6 signals for NT8 AMASignalOverlay indicator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--tag",
                   default="default",
                   help="Output filename tag → ama_signals_TAG.csv (default: default)")
    p.add_argument("--from", dest="from_date", default=None,
                   metavar="YYYY-MM-DD",
                   help="Exclude signals before this date")
    p.add_argument("--to",   dest="to_date",   default=None,
                   metavar="YYYY-MM-DD",
                   help="Exclude signals after this date")
    p.add_argument("--types", nargs="+",
                   default=["BO", "FT", "OB", "BigBO"],
                   choices=["BO", "FT", "OB", "BigBO", "CX"],
                   metavar="TYPE",
                   help="Signal types to include: BO FT OB BigBO CX  (default: BO FT OB BigBO)")
    p.add_argument("--stop-offset",  type=int,   default=1,
                   help="Stop offset in ticks (default 1)")
    p.add_argument("--target-mult",  type=float, default=1.0,
                   help="Target multiplier (default 1.0)")
    p.add_argument("--target-mode",
                   default="BarRange", choices=["BarRange", "BodyRange"],
                   help="Target mode (default BarRange)")
    p.add_argument("--results",
                   default=None, metavar="FILE",
                   help="CSV with SignalNum+PnL_R columns — joins PnL into export")
    p.add_argument("--no-copy", action="store_true",
                   help="Skip copying to ~/Documents/NinjaTrader 8/")
    args = p.parse_args()
    export(args)


if __name__ == "__main__":
    main()
