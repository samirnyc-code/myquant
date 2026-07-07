"""
leg_htf.py — 30M HTF context builder (causal, no lookahead).

At each 5M bar close, reconstructs the state of the forming 30M bar
exactly as it would have appeared in real-time — using only the 5M bars
that have closed at or before that timestamp (spec §4.3, §5.3).

Primary entry point
-------------------
build_htf_context(bars_5m, threshold, atr_period) -> DataFrame
    One row per 5M bar. All HTF columns are causal (past data only).

Lookahead safety guarantee
--------------------------
For each 5M bar at time T, the partial 30M bar is built from all 5M bars
in the same 30M window whose close time <= T. The finalized 30M bar is
NEVER used for the current (forming) window. Only prior *closed* 30M bars
feed the HTF leg decomposition (spec §10.3 note).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from leg_decomp import bar_labels as _bar_labels, DEFAULT_THRESHOLD, DEFAULT_ATR_PERIOD

RTH_START_MIN = 8 * 60 + 30   # 510 minutes from midnight (08:30 CT)
HTF_PERIOD_MIN = 30            # 30-minute HTF bars


def _minutes_from_midnight(dt_series: pd.Series) -> pd.Series:
    return dt_series.dt.hour * 60 + dt_series.dt.minute


def _htf_window_start(dt_series: pd.Series) -> pd.Series:
    """Return the start timestamp of the 30M window each 5M bar belongs to.
    S60: 5M bars are CLOSE-labelled, so the bar's open = label − 5 min; window
    membership is decided by the open (a bar closing 09:00 belongs to the
    08:30–09:00 window)."""
    mins = _minutes_from_midnight(dt_series) - 5
    offset_from_rth = mins - RTH_START_MIN
    window_offset = (offset_from_rth // HTF_PERIOD_MIN) * HTF_PERIOD_MIN
    base_date = dt_series.dt.normalize()
    return base_date + pd.to_timedelta(RTH_START_MIN + window_offset, unit="m")


def build_htf_context(
    bars_5m: pd.DataFrame,
    threshold: float = DEFAULT_THRESHOLD,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> pd.DataFrame:
    """
    Build causal 30M HTF context features for every 5M bar.

    Parameters
    ----------
    bars_5m : DataFrame
        5M bars: DateTime, Open, High, Low, Close, Volume.
    threshold : float
        ATR-swing threshold for HTF leg decomposition.
    atr_period : int
        Wilder ATR period for HTF decomposition.

    Returns
    -------
    DataFrame (same length as bars_5m) with columns:
        htf_window_start  datetime  — start of the 30M window this bar is in
        htf_k             int       — bar position within 30M window (1=first, 6=last)
        htf_partial_open  float     — open of first 5M bar in this 30M window
        htf_partial_high  float     — max high of 5M bars up to and including this bar
        htf_partial_low   float     — min low of 5M bars up to and including this bar
        htf_partial_close float     — close of this 5M bar (= 30M close so far)
        htf_bar_range     float     — htf_partial_high - htf_partial_low
        htf_broke_struct  int       — 1 if partial 30M bar broke prior HTF swing extreme
        htf_has_pb        int       — 1 if price pulled back >0 ticks within forming bar
        htf_direction     int       — +1/−1 direction of the current 30M HTF leg (causal)
        htf_leg_id        int       — HTF leg_id from closed 30M bars
        htf_leg_bars      int       — bars elapsed in current HTF leg (at prior HTF close)
        htf_prior_extreme float     — prior HTF swing extreme (high or low)
        htf_retrace_pct   float     — how far into the prior HTF leg price has retraced (0–1)
    """
    bars_r = bars_5m.reset_index(drop=True).copy()
    bars_r["DateTime"] = pd.to_datetime(bars_r["DateTime"])

    win_start = _htf_window_start(bars_r["DateTime"])
    bars_r["_win"]  = win_start
    bars_r["_date"] = bars_r["DateTime"].dt.date

    # ── Build closed 30M bars (causal: use only finalized windows) ────────────
    # Group by (date, win_start) to produce OHLCV for each complete 30M window.
    closed_htf = (
        bars_r.groupby(["_date", "_win"], sort=True)
        .agg(
            Open   = ("Open",   "first"),
            High   = ("High",   "max"),
            Low    = ("Low",    "min"),
            Close  = ("Close",  "last"),
            Volume = ("Volume", "sum"),
        )
        .reset_index()
        .rename(columns={"_win": "DateTime"})
        .drop(columns=["_date"])
        .sort_values("DateTime")
        .reset_index(drop=True)
    )

    # ── Run HTF leg decomposition on closed 30M bars ───────────────────────────
    if len(closed_htf) >= 2:
        htf_lbl = _bar_labels(closed_htf, threshold=threshold, atr_period=atr_period)
    else:
        htf_lbl = pd.DataFrame(columns=[
            "DateTime", "leg_id", "direction", "phase",
            "pivot_price", "run_extreme", "bars_in_leg", "atr",
        ])

    # Build a lookup: for any closed 30M bar, what is the HTF leg state?
    # We need the state BEFORE each window starts (i.e. from closed_htf[-1])
    # so at 5M bar time T inside window W, HTF leg state = state at end of window W-1.

    htf_lbl_indexed = htf_lbl.set_index("DateTime") if not htf_lbl.empty else None

    # ── Per-5M-bar HTF features ───────────────────────────────────────────────
    n = len(bars_r)
    htf_win_start_out   = np.empty(n, dtype="datetime64[ns]")
    htf_k_out           = np.zeros(n, dtype=np.int32)
    htf_p_open_out      = np.full(n, np.nan)
    htf_p_high_out      = np.full(n, np.nan)
    htf_p_low_out       = np.full(n, np.nan)
    htf_p_close_out     = np.full(n, np.nan)
    htf_broke_struct_out = np.zeros(n, dtype=np.int8)
    htf_has_pb_out      = np.zeros(n, dtype=np.int8)
    htf_direction_out   = np.zeros(n, dtype=np.int8)
    htf_leg_id_out      = np.zeros(n, dtype=np.int32)
    htf_leg_bars_out    = np.zeros(n, dtype=np.int32)
    htf_prior_extreme_out = np.full(n, np.nan)
    htf_retrace_pct_out = np.full(n, np.nan)

    # Process window-by-window
    for win_dt, grp in bars_r.groupby("_win", sort=True):
        idxs = grp.index.tolist()
        k_vals = list(range(1, len(idxs) + 1))

        p_open  = float(grp["Open"].iloc[0])
        p_highs = grp["High"].to_numpy(dtype=np.float64)
        p_lows  = grp["Low"].to_numpy(dtype=np.float64)
        p_closes = grp["Close"].to_numpy(dtype=np.float64)

        # Retrieve HTF state from the last closed bar BEFORE this window
        win_ts = pd.Timestamp(win_dt)
        htf_dir      = 0
        htf_lid      = 0
        htf_lbars    = 0
        htf_prior_ext = np.nan

        if htf_lbl_indexed is not None:
            prior = htf_lbl_indexed[htf_lbl_indexed.index < win_ts]
            if not prior.empty:
                last_htf = prior.iloc[-1]
                htf_dir   = int(last_htf["direction"])
                htf_lid   = int(last_htf["leg_id"])
                htf_lbars = int(last_htf["bars_in_leg"])
                htf_prior_ext = float(last_htf["run_extreme"])

        for j, idx in enumerate(idxs):
            cum_high = float(np.max(p_highs[: j + 1]))
            cum_low  = float(np.min(p_lows[: j + 1]))
            cur_close = float(p_closes[j])

            # Broke structure: did the partial 30M bar exceed the prior HTF extreme?
            broke = 0
            if not np.isnan(htf_prior_ext) and htf_dir != 0:
                if htf_dir == 1 and cum_high > htf_prior_ext:
                    broke = 1
                elif htf_dir == -1 and cum_low < htf_prior_ext:
                    broke = 1

            # Has-PB: did price pull back within the forming 30M bar?
            has_pb = 0
            if j > 0:
                if htf_dir == 1 and cum_low < float(p_lows[0]):
                    has_pb = 1
                elif htf_dir == -1 and cum_high > float(p_highs[0]):
                    has_pb = 1

            # Retrace pct: how far has price retraced into the prior HTF leg?
            retrace = np.nan
            if not np.isnan(htf_prior_ext) and htf_dir != 0:
                leg_size = abs(cur_close - htf_prior_ext)
                prior_leg_size = abs(htf_prior_ext - p_open)  # approx
                if prior_leg_size > 0:
                    retrace = leg_size / prior_leg_size

            htf_win_start_out[idx]    = np.datetime64(win_ts)
            htf_k_out[idx]            = k_vals[j]
            htf_p_open_out[idx]       = p_open
            htf_p_high_out[idx]       = cum_high
            htf_p_low_out[idx]        = cum_low
            htf_p_close_out[idx]      = cur_close
            htf_broke_struct_out[idx] = broke
            htf_has_pb_out[idx]       = has_pb
            htf_direction_out[idx]    = htf_dir
            htf_leg_id_out[idx]       = htf_lid
            htf_leg_bars_out[idx]     = htf_lbars
            htf_prior_extreme_out[idx] = htf_prior_ext
            htf_retrace_pct_out[idx]  = retrace

    out = bars_r[["DateTime"]].copy()
    out["htf_window_start"]  = htf_win_start_out
    out["htf_k"]             = htf_k_out.astype(int)
    out["htf_partial_open"]  = htf_p_open_out
    out["htf_partial_high"]  = htf_p_high_out
    out["htf_partial_low"]   = htf_p_low_out
    out["htf_partial_close"] = htf_p_close_out
    out["htf_bar_range"]     = htf_p_high_out - htf_p_low_out
    out["htf_broke_struct"]  = htf_broke_struct_out.astype(int)
    out["htf_has_pb"]        = htf_has_pb_out.astype(int)
    out["htf_direction"]     = htf_direction_out.astype(int)
    out["htf_leg_id"]        = htf_leg_id_out.astype(int)
    out["htf_leg_bars"]      = htf_leg_bars_out.astype(int)
    out["htf_prior_extreme"] = htf_prior_extreme_out
    out["htf_retrace_pct"]   = htf_retrace_pct_out
    return out
