"""
leg_decomp.py — ATR-swing leg decomposition for ES 5M and 30M bars.

Segments a bar series into directed micro-channel legs using an ATR-gated
swing reversal rule (Brooks price-action framework, spec §6.1).

Primary entry points
--------------------
bar_labels(bars, threshold, atr_period) -> DataFrame
    Per-bar leg assignment. One row per input bar.

leg_table(bar_labels_df, bars) -> DataFrame
    One row per confirmed leg with geometry fields.

swing_threshold
    Primary tuning knob — ATR multiples required to confirm a reversal.
    Lock on structural grounds BEFORE any model training (spec §6.1 note).
    Default 1.5 is a reasonable ES 5M starting point; tune by visual
    inspection of leg count and structure, not by fitting to labels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TICK_SIZE        = 0.25
DEFAULT_THRESHOLD  = 1.5   # ATR multiples to confirm reversal
DEFAULT_ATR_PERIOD = 14


# ── ATR ───────────────────────────────────────────────────────────────────────

def _wilder_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Wilder smoothed ATR. First value uses simple mean of first `period` TRs."""
    n = len(high)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i]  - close[i - 1]),
        )
    atr = np.full(n, np.nan, dtype=np.float64)
    if n >= period:
        atr[period - 1] = float(np.mean(tr[:period]))
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


# ── Core decomposition ────────────────────────────────────────────────────────

def bar_labels(
    bars: pd.DataFrame,
    threshold: float = DEFAULT_THRESHOLD,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> pd.DataFrame:
    """
    Run ATR-swing decomposition and return a per-bar label DataFrame.

    Parameters
    ----------
    bars : DataFrame
        Must have columns: DateTime, Open, High, Low, Close (Volume optional).
    threshold : float
        Number of ATR multiples required to confirm a direction reversal.
    atr_period : int
        Lookback for Wilder ATR calculation.

    Returns
    -------
    DataFrame (same length as `bars`) with columns:
        leg_id       int   — monotone counter; increments on each confirmed flip
        direction    int   — +1 (up leg) or -1 (down leg)
        phase        str   — 'forming' for the current (last) leg, 'confirmed' for all prior
        pivot_price  float — price at which this leg started (prior pivot extreme)
        run_extreme  float — current running extreme (high for UP, low for DOWN)
        bars_in_leg  int   — bars elapsed since this leg started (0-based)
        atr          float — Wilder ATR at this bar (NaN during warmup)
    """
    hi  = bars["High"].to_numpy(dtype=np.float64)
    lo  = bars["Low"].to_numpy(dtype=np.float64)
    cl  = bars["Close"].to_numpy(dtype=np.float64)
    n   = len(bars)

    atr_arr = _wilder_atr(hi, lo, cl, atr_period)

    leg_id_arr     = np.zeros(n, dtype=np.int32)
    direction_arr  = np.zeros(n, dtype=np.int8)
    pivot_arr      = np.zeros(n, dtype=np.float64)
    run_ext_arr    = np.zeros(n, dtype=np.float64)
    bars_in_arr    = np.zeros(n, dtype=np.int32)

    # ── Initialise ────────────────────────────────────────────────────────────
    # Start bullish (arbitrary; the market will flip on evidence).
    cur_dir    = 1
    run_high   = hi[0]
    run_low    = lo[0]
    pivot_price = lo[0]    # up leg started "from" the open low
    leg_id     = 0
    leg_start  = 0

    for i in range(n):
        atr = atr_arr[i]
        if np.isnan(atr):
            # Warmup: use bar's own range as ATR proxy
            atr = max(hi[i] - lo[i], TICK_SIZE)

        if cur_dir == 1:
            run_high = max(run_high, hi[i])
            if cl[i] < run_high - threshold * atr:
                # Flip: confirm up-leg, start new down-leg
                leg_id    += 1
                pivot_price = run_high
                leg_start  = i
                cur_dir    = -1
                run_low    = lo[i]
                run_high   = hi[i]
        else:
            run_low = min(run_low, lo[i])
            if cl[i] > run_low + threshold * atr:
                # Flip: confirm down-leg, start new up-leg
                leg_id    += 1
                pivot_price = run_low
                leg_start  = i
                cur_dir    = 1
                run_high   = hi[i]
                run_low    = lo[i]

        leg_id_arr[i]    = leg_id
        direction_arr[i] = cur_dir
        pivot_arr[i]     = pivot_price
        run_ext_arr[i]   = run_high if cur_dir == 1 else run_low
        bars_in_arr[i]   = i - leg_start

    # Phase: all bars except the last leg are 'confirmed'
    max_leg = int(leg_id_arr[-1])
    phase = np.where(leg_id_arr < max_leg, "confirmed", "forming")

    out = bars[["DateTime"]].copy().reset_index(drop=True)
    out["leg_id"]      = leg_id_arr
    out["direction"]   = direction_arr.astype(int)
    out["phase"]       = phase
    out["pivot_price"] = pivot_arr
    out["run_extreme"] = run_ext_arr
    out["bars_in_leg"] = bars_in_arr
    out["atr"]         = atr_arr
    return out


# ── Leg summary table ─────────────────────────────────────────────────────────

def leg_table(labels: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """
    Build a one-row-per-leg summary from bar_labels() output.

    Parameters
    ----------
    labels : output of bar_labels()
    bars   : the same bar DataFrame passed to bar_labels()

    Returns
    -------
    DataFrame with columns:
        leg_id, direction, phase,
        start_dt, end_dt, start_idx, end_idx,
        start_price, end_price, pivot_price,
        length_bars, length_ticks, avg_atr,
        parent_leg_idx  (N-th leg of this direction within the session/full series)
    """
    bars_r = bars.reset_index(drop=True)
    lbl_r  = labels.reset_index(drop=True)

    hi_arr = bars_r["High"].to_numpy(dtype=np.float64)
    lo_arr = bars_r["Low"].to_numpy(dtype=np.float64)

    rows = []
    dir_counter = {1: 0, -1: 0}

    for lid, grp in lbl_r.groupby("leg_id", sort=True):
        first    = grp.iloc[0]
        last     = grp.iloc[-1]
        idx0     = int(grp.index[0])
        idx1     = int(grp.index[-1])
        direction = int(first["direction"])
        phase     = str(last["phase"])

        # Start price = pivot (where this leg kicked off)
        start_price = float(first["pivot_price"])
        # End price = the running extreme at the last bar of this leg
        end_price = float(last["run_extreme"])

        # For confirmed legs the run_extreme converges to the true pivot
        leg_high = float(np.max(hi_arr[idx0 : idx1 + 1]))
        leg_low  = float(np.min(lo_arr[idx0 : idx1 + 1]))
        excursion_price = leg_high if direction == 1 else leg_low

        length_ticks = round(abs(excursion_price - start_price) / TICK_SIZE)

        dir_counter[direction] += 1
        parent_leg_idx = dir_counter[direction]

        rows.append({
            "leg_id":          int(lid),
            "direction":       direction,
            "phase":           phase,
            "start_dt":        first["DateTime"],
            "end_dt":          last["DateTime"],
            "start_idx":       idx0,
            "end_idx":         idx1,
            "start_price":     start_price,
            "end_price":       excursion_price,
            "pivot_price":     start_price,
            "length_bars":     len(grp),
            "length_ticks":    length_ticks,
            "avg_atr":         float(grp["atr"].mean(skipna=True)),
            "parent_leg_idx":  parent_leg_idx,
        })

    return pd.DataFrame(rows)


# ── Convenience: decompose a full bars DataFrame in one call ──────────────────

def decompose(
    bars: pd.DataFrame,
    threshold: float = DEFAULT_THRESHOLD,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run full decomposition. Returns (bar_labels_df, leg_table_df).

    Example
    -------
    >>> labels, legs = decompose(bars_5m, threshold=1.5)
    """
    lbl = bar_labels(bars, threshold=threshold, atr_period=atr_period)
    tbl = leg_table(lbl, bars)
    return lbl, tbl
