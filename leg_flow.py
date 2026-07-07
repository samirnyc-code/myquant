"""
leg_flow.py — Tick-rule order flow features from per-day tick parquets.

Tick data is available as DateTime/Price/Volume per-day parquets in
data/ticks_continuous/. Bid/Ask is NOT available so we use the tick rule:
  uptick  → buy;  downtick → sell;  same price → carry prior direction.

Accuracy is ~70-85% vs true delta (spec §4.2, tier 2). Use delta *shape
and slope across legs*, not absolute values.

Primary entry points
--------------------
build_bar_flow(tick_dir, date_range) -> polars.DataFrame
    Aggregate tick data to per-5M-bar order-flow features.

bar_flow_to_pandas(pl_df) -> pd.DataFrame
    Convert polars output to pandas for joining with bars_5m.

join_flow_to_bars(bars_5m, bar_flow_pd) -> pd.DataFrame
    Left-join flow features onto a bars DataFrame by DateTime.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
import polars as pl

TICK_DIR    = Path(__file__).parent / "data" / "ticks_continuous"
TICK_SIZE   = 0.25
RTH_START   = "08:30:00"
RTH_END     = "15:15:00"
BAR_PERIOD  = "5m"


# ── Tick-rule classification ──────────────────────────────────────────────────

def _classify_ticks_polars(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add a 'side' column (+1 buy, -1 sell) using the tick rule.
    Input must have columns: DateTime, Price, Volume (sorted ascending).
    """
    price = df["Price"].to_numpy()
    n     = len(price)
    side  = np.zeros(n, dtype=np.int8)

    prev_dir = 1  # start bullish
    for i in range(1, n):
        if price[i] > price[i - 1]:
            prev_dir = 1
        elif price[i] < price[i - 1]:
            prev_dir = -1
        side[i] = prev_dir
    side[0] = prev_dir  # first tick inherits first detected direction

    return df.with_columns(pl.Series("side", side, dtype=pl.Int8))


# ── Date helpers ──────────────────────────────────────────────────────────────

def _iter_dates(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _tick_path(d: date) -> Path:
    return TICK_DIR / f"{d.isoformat()}.parquet"


# ── Per-day processing ────────────────────────────────────────────────────────

def _process_day(d: date) -> pl.DataFrame | None:
    path = _tick_path(d)
    if not path.exists():
        return None

    df = pl.read_parquet(path)

    # Normalise column names
    df = df.rename({c: c for c in df.columns})  # no-op; ensure schema
    required = {"DateTime", "Price", "Volume"}
    if not required.issubset(set(df.columns)):
        return None

    df = (
        df
        .with_columns(pl.col("DateTime").cast(pl.Datetime("us")))
        .sort("DateTime")
        # RTH filter
        .filter(
            (pl.col("DateTime").dt.strftime("%H:%M:%S") >= RTH_START) &
            (pl.col("DateTime").dt.strftime("%H:%M:%S") <  RTH_END)
        )
    )
    if df.is_empty():
        return None

    df = _classify_ticks_polars(df)

    # Compute buy/sell volumes
    df = df.with_columns([
        (pl.col("Volume") * pl.when(pl.col("side") == 1).then(1).otherwise(0)).alias("buy_vol"),
        (pl.col("Volume") * pl.when(pl.col("side") == -1).then(1).otherwise(0)).alias("sell_vol"),
    ])

    # Truncate to 5M bars — S60 close labels: bin ticks by [open, close) then
    # label with the bin CLOSE (truncate gives the open; +5m = close)
    df = df.with_columns(
        (pl.col("DateTime").dt.truncate("5m") + pl.duration(minutes=5)).alias("bar_dt")
    )

    # Per-bar aggregation
    bar_df = (
        df
        .group_by("bar_dt")
        .agg([
            pl.col("buy_vol").sum().alias("buy_vol"),
            pl.col("sell_vol").sum().alias("sell_vol"),
            pl.col("Volume").sum().alias("total_vol"),
            # Delta: buy - sell
            (pl.col("buy_vol").sum() - pl.col("sell_vol").sum()).alias("delta"),
            pl.col("Price").count().alias("tick_count"),
        ])
        .sort("bar_dt")
    )

    # Cumulative delta within RTH session (resets each day)
    bar_df = bar_df.with_columns(
        pl.col("delta").cum_sum().alias("cum_delta")
    )

    return bar_df.rename({"bar_dt": "DateTime"})


# ── Public API ────────────────────────────────────────────────────────────────

def build_bar_flow(
    date_range: tuple[date, date] | None = None,
    tick_dir: Path | str = TICK_DIR,
) -> pl.DataFrame:
    """
    Build per-5M-bar order flow features for a date range.

    Parameters
    ----------
    date_range : (start_date, end_date) inclusive. If None, processes all
                 available tick parquets in tick_dir.
    tick_dir   : path to per-day tick parquet directory.

    Returns
    -------
    polars DataFrame with columns:
        DateTime, buy_vol, sell_vol, total_vol, delta, cum_delta, tick_count

    Notes
    -----
    - cum_delta resets to zero at each RTH open (spec §11.3).
    - Missing days are silently skipped.
    - Use bar_flow_to_pandas() to convert for joining with bars_5m.
    """
    tick_dir = Path(tick_dir)

    if date_range is None:
        files = sorted(tick_dir.glob("*.parquet"))
        dates = []
        for f in files:
            try:
                dates.append(date.fromisoformat(f.stem))
            except ValueError:
                pass
        if not dates:
            return pl.DataFrame(schema={
                "DateTime": pl.Datetime("us"),
                "buy_vol": pl.Int64, "sell_vol": pl.Int64,
                "total_vol": pl.Int64, "delta": pl.Int64,
                "cum_delta": pl.Int64, "tick_count": pl.UInt32,
            })
        start, end = min(dates), max(dates)
    else:
        start, end = date_range

    frames = []
    for d in _iter_dates(start, end):
        day_df = _process_day(d)
        if day_df is not None:
            frames.append(day_df)

    if not frames:
        return pl.DataFrame(schema={
            "DateTime": pl.Datetime("us"),
            "buy_vol": pl.Int64, "sell_vol": pl.Int64,
            "total_vol": pl.Int64, "delta": pl.Int64,
            "cum_delta": pl.Int64, "tick_count": pl.UInt32,
        })

    return pl.concat(frames).sort("DateTime")


def bar_flow_to_pandas(pl_df: pl.DataFrame) -> pd.DataFrame:
    """Convert polars bar-flow DataFrame to pandas, keeping DateTime as index-compatible."""
    df = pl_df.to_pandas()
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    return df


def join_flow_to_bars(bars_5m: pd.DataFrame, bar_flow_pd: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join order-flow features onto bars_5m by DateTime.

    Missing bars (no tick data that day) get NaN flow columns.
    """
    bars_r = bars_5m.copy()
    bars_r["DateTime"] = pd.to_datetime(bars_r["DateTime"])
    flow_r = bar_flow_pd.copy()
    flow_r["DateTime"] = pd.to_datetime(flow_r["DateTime"])

    merged = bars_r.merge(
        flow_r[["DateTime", "buy_vol", "sell_vol", "total_vol", "delta", "cum_delta", "tick_count"]],
        on="DateTime",
        how="left",
    )
    return merged


# ── Leg-level aggregation ─────────────────────────────────────────────────────

def aggregate_flow_per_leg(
    bars_with_flow: pd.DataFrame,
    bar_labels: pd.DataFrame,
) -> pd.DataFrame:
    """
    Aggregate per-bar flow features to per-leg summaries.

    Parameters
    ----------
    bars_with_flow : output of join_flow_to_bars()
    bar_labels     : output of leg_decomp.bar_labels()

    Returns
    -------
    DataFrame indexed by leg_id with columns:
        leg_delta          — cumulative delta over the leg
        leg_buy_vol        — total buy volume
        leg_sell_vol       — total sell volume
        leg_total_vol      — total volume
        delta_slope        — linear slope of per-bar delta across the leg (sign = trend)
        delta_divergence   — 1 if delta slope opposes leg direction (exhaustion signal)
        effort_vs_result   — total_vol / (leg length in ticks + 1), normalised effort
        tick_count         — number of ticks in the leg
    """
    merged = bar_labels[["leg_id", "direction"]].copy()
    merged["delta"]     = bars_with_flow["delta"].values
    merged["buy_vol"]   = bars_with_flow["buy_vol"].values
    merged["sell_vol"]  = bars_with_flow["sell_vol"].values
    merged["total_vol"] = bars_with_flow["total_vol"].values
    merged["tick_count"] = bars_with_flow["tick_count"].values

    rows = []
    for lid, grp in merged.groupby("leg_id"):
        direction = int(grp["direction"].iloc[0])
        deltas = grp["delta"].dropna().to_numpy(dtype=float)

        leg_delta   = float(np.nansum(grp["delta"]))
        buy_vol     = float(np.nansum(grp["buy_vol"]))
        sell_vol    = float(np.nansum(grp["sell_vol"]))
        total_vol   = float(np.nansum(grp["total_vol"]))
        ticks_total = int(np.nansum(grp["tick_count"]))

        # Delta slope (linear regression over bar indices within the leg)
        delta_slope = np.nan
        if len(deltas) >= 2:
            x = np.arange(len(deltas), dtype=float)
            if np.std(x) > 0:
                delta_slope = float(np.polyfit(x, deltas, 1)[0])

        # Divergence: slope opposes leg direction → exhaustion
        diverges = 0
        if not np.isnan(delta_slope):
            if direction == 1 and delta_slope < 0:
                diverges = 1
            elif direction == -1 and delta_slope > 0:
                diverges = 1

        # Effort vs result: high volume + little price progress = absorption
        # (actual leg_ticks added later in leg_features.py join)
        effort = total_vol / max(len(grp), 1)

        rows.append({
            "leg_id":           lid,
            "leg_delta":        leg_delta,
            "leg_buy_vol":      buy_vol,
            "leg_sell_vol":     sell_vol,
            "leg_total_vol":    total_vol,
            "delta_slope":      delta_slope,
            "delta_divergence": diverges,
            "effort_vs_result": effort,
            "tick_count":       ticks_total,
        })

    return pd.DataFrame(rows).set_index("leg_id")
