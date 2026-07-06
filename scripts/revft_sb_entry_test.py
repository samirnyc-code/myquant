"""RevFT Signal Bar Entry Test — new entry logic vs baseline.

New entry: limit 1 tick above SB (signal bar) low, only fills if price ticks to SB low.
Tests two targets: signal price (scalp) and original target (full).
Compares baseline vs new entry per setup type with 5 key metrics.

FIXED: bars now use close times, so BarNum maps directly to bar index.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["MQ_APPLY_NEXT_DAY"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

import massive                                                      # noqa: E402
massive._TICKS_CONT_DIR = ROOT / "data" / "ticks_continuous"
from menthorq_edge_study import (load_mq, WIN_START, WIN_END,      # noqa: E402
                                 BARS_PQ, parse_signals)
from menthorq_sr_followup import offsets_for                       # noqa: E402

if len(sys.argv) > 2:
    REV_TXT = Path(sys.argv[1])
    OUT = ROOT / "docs" / "living" / sys.argv[2]
else:
    REV_TXT = Path(os.environ.get(
        "REVFT_SIGNAL_TXT",
        ROOT / "data" / "signals" /
        "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"))
    OUT = ROOT / "docs" / "living" / "revft_sb_entry_test_20260706.md"

L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


def log(m):
    print(f"[revft_sb_entry] {m}", flush=True)


def rrow(label, df_res):
    """Render a results row with 5 key metrics: n, ExpR ±CI, PF, Win%, net$."""
    if len(df_res) == 0:
        return f"| {label} | 0 | — | — | — | — |"

    n = len(df_res)
    r = df_res["Rmult"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    pnl = df_res["PnL"].to_numpy()
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    win_pct = 100.0 * (pnl > 0).sum() / n if n > 0 else 0

    lo, hi = r.mean() - ci, r.mean() + ci
    mark = " ✅" if lo > 0 else (" ❌" if hi < 0 else "")

    return (f"| {label} | {n} | {r.mean():+.3f} ±{ci:.3f}{mark} | {pf:.2f} | {win_pct:.1f}% | "
            f"${pnl.sum():,.0f} |")


# Load baseline signals and bars
sig = parse_signals(REV_TXT)
win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
emit(f"{len(sig)} RevFT signals total; {len(win)} in window\n")

bars = pd.read_parquet(BARS_PQ)
bars["DateTime"] = pd.to_datetime(bars["DateTime"])
day = bars["DateTime"].dt.normalize()
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}

# Load ticks for each day in window
dates = sorted(win["Date"].unique())
log(f"Loading ticks for {len(dates)} days...")
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
log(f"Loaded ticks for {len(ticks)} days")


def get_sb_extreme(signal_row, bars_on_day, is_long):
    """Get the signal bar extreme: low for a long, high for a short.

    BarNum is NT's 1-indexed bar count; pandas is 0-indexed, so the signal bar
    (the one whose close == SignalPrice, closing at the signal DateTime) is at
    iloc[BarNum - 1]. Verified 15/15 on in-window signals.
    """
    bar_num = int(signal_row["BarNum"])
    idx = bar_num - 1
    if idx < 0 or idx >= len(bars_on_day):
        return None
    bar = bars_on_day.iloc[idx]
    return float(bar["Low"]) if is_long else float(bar["High"])


def simulate_new_entry(signals_df, ticks_by_date, bars_by_date, tick_size=0.25):
    """Simulate trades with new entry: limit 1 tick above SB low.

    Returns a DataFrame with fills, entry times, and PnL for both targets.
    """
    results = []

    for idx, sig in signals_df.iterrows():
        trade_date = sig["Date"]
        sig_dt = sig["DateTime"]
        direction = sig["Direction"].upper()[0]  # 'L' or 'S'
        is_long = (direction == 'L')
        signal_price = float(sig["SignalPrice"])
        # CSV StopPrice is the setup EXTREME. Actual stop = extreme offset 1 tick
        # (long: extreme - 1t; short: extreme + 1t). Same stop as baseline.
        extreme = float(sig["StopPrice"])
        stop_price = extreme - tick_size if is_long else extreme + tick_size

        # Get signal bar low
        bars_on_day = bars_by_date.get(trade_date)
        if bars_on_day is None or len(bars_on_day) == 0:
            continue

        sb_ext = get_sb_extreme(sig, bars_on_day, is_long)
        if sb_ext is None:
            continue

        # New entry: limit 1 tick inside the SB extreme
        # (long: SB low + 1t; short: SB high - 1t)
        limit_price = sb_ext + tick_size if is_long else sb_ext - tick_size

        # Get ticks after signal bar close
        day_ticks = ticks_by_date.get(trade_date)
        if day_ticks is None or day_ticks.empty:
            continue

        ticks_after_sig = day_ticks[day_ticks["DateTime"] > sig_dt].copy()
        if ticks_after_sig.empty:
            continue

        ticks_after_sig = ticks_after_sig.reset_index(drop=True)
        prices = ticks_after_sig["Price"].to_numpy()
        times = ticks_after_sig["DateTime"].to_numpy()

        # Price must tick to the SB extreme for the limit to fill
        if is_long:
            # Long: price must reach SB low, limit buy at SB low + 1t
            if not np.any(prices <= sb_ext):
                continue
            touched_idx = np.where(prices <= sb_ext)[0][0]
            fill_mask = prices[touched_idx:] >= limit_price
            fill_idx_in_sub = np.where(fill_mask)[0]
            if len(fill_idx_in_sub) == 0:
                continue
            fill_idx = touched_idx + fill_idx_in_sub[0]
        else:
            # Short: price must reach SB high, limit sell at SB high - 1t
            if not np.any(prices >= sb_ext):
                continue
            touched_idx = np.where(prices >= sb_ext)[0][0]
            fill_mask = prices[touched_idx:] <= limit_price
            fill_idx_in_sub = np.where(fill_mask)[0]
            if len(fill_idx_in_sub) == 0:
                continue
            fill_idx = touched_idx + fill_idx_in_sub[0]

        # Entry filled
        entry_price = prices[fill_idx]
        entry_time = times[fill_idx]

        # Two targets:
        # Target 1: signal price (scalp)
        # Target 2: original target (1R from signal price)
        original_risk = abs(signal_price - stop_price)  # Risk if entered at signal price
        actual_risk = abs(entry_price - stop_price)  # Actual risk from new entry
        target1 = signal_price
        target2 = signal_price + (1.0 * original_risk) if is_long else signal_price - (1.0 * original_risk)

        # Find what hits FIRST: stop, target1, or target2
        pnl_scalp = None
        pnl_full = None
        rmult_scalp = None
        rmult_full = None

        # Scalp and Full are TWO INDEPENDENT strategies sharing the same entry.
        # Scan each separately for the first of {stop, its target} to hit.
        rdollar = actual_risk * 50 if actual_risk > 0 else np.nan
        scan = prices[fill_idx:]

        def resolve(exit_target):
            """First of {stop, exit_target} to hit. Returns (pnl, rmult) or (None, None)."""
            for p in scan:
                if is_long:
                    if p <= stop_price:
                        pnl = (stop_price - entry_price) * 50
                        return pnl, pnl / rdollar
                    if p >= exit_target:
                        pnl = (exit_target - entry_price) * 50
                        return pnl, pnl / rdollar
                else:
                    if p >= stop_price:
                        pnl = (entry_price - stop_price) * 50
                        return pnl, pnl / rdollar
                    if p <= exit_target:
                        pnl = (entry_price - exit_target) * 50
                        return pnl, pnl / rdollar
            return None, None  # neither hit by EOD

        pnl_scalp, rmult_scalp = resolve(target1)
        pnl_full, rmult_full = resolve(target2)

        results.append({
            "DateTime": sig_dt,
            "Date": trade_date,
            "SignalType": sig.get("SignalType", "Unknown"),
            "Direction": direction,
            "BarNum": int(sig["BarNum"]),
            "SBExtreme": sb_ext,
            "LimitPrice": limit_price,
            "EntryPrice": entry_price,
            "PnL_Scalp": pnl_scalp,
            "PnL_Full": pnl_full,
            "Rmult_Scalp": rmult_scalp,
            "Rmult_Full": rmult_full,
        })

    return pd.DataFrame(results)


# Run simulation
log("Simulating new entry logic...")
results = simulate_new_entry(win, ticks, bbd, tick_size=0.25)
log(f"Got {len(results)} new-entry fills out of {len(win)} signals")

if len(results) == 0:
    emit("No fills with new entry logic.")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"written {OUT}")
    sys.exit(0)

# Add metrics
results["PnL"] = results["PnL_Full"].fillna(0)
results["Rmult"] = results["Rmult_Full"].fillna(0)
results["CumPnL"] = results["PnL"].cumsum()

emit("# RevFT Signal Bar Entry Test — New Entry Method\n")
emit(f"**Date:** July 6, 2026")
emit(f"**Window:** {WIN_START.date()} – {WIN_END.date()}")
emit(f"**Signals tested:** {len(results)} new-entry fills out of {len(win)} total\n")

emit("## Results by Setup Type (Full Target: Original 1R)\n")
emit("| Setup Type | n | ExpR ±CI | PF | Win% | Net $ |")
emit("|---|---|---|---|---|---|")

for sig_type in sorted(results["SignalType"].unique()):
    subset = results[results["SignalType"] == sig_type]
    emit(rrow(f"**{sig_type}**", subset))

emit(rrow("**ALL TYPES**", results))
emit("")

# Scalp vs Full
emit("## Target Comparison\n")
emit("| Scenario | n | ExpR ±CI | PF | Win% | Net $ |")
emit("|---|---|---|---|---|---|")

scalp_data = results[results["Rmult_Scalp"].notna()].copy()
if len(scalp_data) > 0:
    scalp_data["Rmult"] = scalp_data["Rmult_Scalp"]
    scalp_data["PnL"] = scalp_data["PnL_Scalp"]
    emit(rrow("Scalp (→ Signal Price)", scalp_data))

full_data = results[results["Rmult_Full"].notna()].copy()
if len(full_data) > 0:
    full_data["Rmult"] = full_data["Rmult_Full"]
    full_data["PnL"] = full_data["PnL_Full"]
    emit(rrow("Full (→ Original 1R Target)", full_data))

OUT.write_text("\n".join(L), encoding="utf-8")
log(f"written {OUT}")
