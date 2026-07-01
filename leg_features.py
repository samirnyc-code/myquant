"""
leg_features.py — Full feature matrix for the ES leg classifier.

Builds a per-leg feature DataFrame combining:
  5.1 — 5M local leg geometry
  5.2 — Parent-relative (structural position, always-in, negation test)
  5.3 — HTF context (30M causal)
  5.4 — Order flow (tick-rule delta shape)

Primary entry point
-------------------
build_feature_matrix(bars_5m, labels, legs, htf_ctx, flow_per_leg) -> DataFrame
    One row per leg. All features are causal (no lookahead).

Columns returned
----------------
See FEATURE_COLS at the bottom of this module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TICK_SIZE    = 0.25
RTH_START_MIN = 8 * 60 + 30   # 08:30 CT in minutes from midnight
EMA_PERIOD   = 20


# ── EMA ───────────────────────────────────────────────────────────────────────

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(series), np.nan)
    k = 2 / (period + 1)
    # Seed with first finite value
    first = next((i for i, v in enumerate(series) if not np.isnan(v)), None)
    if first is None:
        return out
    out[first] = series[first]
    for i in range(first + 1, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1 - k)
    return out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_bucket(dt: pd.Timestamp) -> int:
    """
    0 = open rush   (08:30–09:30)
    1 = mid-morning (09:30–11:30)
    2 = lunch       (11:30–13:00)
    3 = afternoon   (13:00–15:15)
    """
    mins = dt.hour * 60 + dt.minute - RTH_START_MIN
    if mins < 60:  return 0
    if mins < 180: return 1
    if mins < 270: return 2
    return 3


def _minutes_into_session(dt: pd.Timestamp) -> int:
    return dt.hour * 60 + dt.minute - RTH_START_MIN


def _linear_slope(arr: np.ndarray) -> float:
    """Slope of linear fit. NaN if <2 points."""
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return np.nan
    x = np.arange(len(arr), dtype=float)
    return float(np.polyfit(x, arr, 1)[0])


# ── Section 5.1 — 5M local leg geometry ──────────────────────────────────────

def _local_features(
    leg: pd.Series,
    leg_bars: pd.DataFrame,
    ema_arr: np.ndarray,
    atr_at_start: float,
) -> dict:
    """
    Compute local geometry features for a single leg.

    leg       : one row of leg_table (leg_id, direction, start/end idx, ...)
    leg_bars  : subset of bars_5m for this leg
    ema_arr   : EMA(20) values aligned to full bars_5m index
    atr_at_start : ATR at the first bar of this leg
    """
    direction  = int(leg["direction"])
    n_bars     = len(leg_bars)
    hi = leg_bars["High"].to_numpy(dtype=float)
    lo = leg_bars["Low"].to_numpy(dtype=float)
    cl = leg_bars["Close"].to_numpy(dtype=float)
    op = leg_bars["Open"].to_numpy(dtype=float)

    # Slope: price change per bar
    price_range  = abs(cl[-1] - op[0]) if n_bars > 0 else 0.0
    slope_ticks  = (price_range / TICK_SIZE) / max(n_bars, 1) * direction

    # Bar overlap: fraction of bars whose range overlaps the prior bar
    overlapping = 0
    for i in range(1, n_bars):
        if lo[i] <= hi[i - 1] and hi[i] >= lo[i - 1]:
            overlapping += 1
    overlap_pct = overlapping / max(n_bars - 1, 1) if n_bars > 1 else 0.0

    # Opposite-direction bars within the leg
    opp_bars = 0
    for i in range(n_bars):
        bar_dir = 1 if cl[i] >= op[i] else -1
        if bar_dir != direction:
            opp_bars += 1
    opp_bar_frac = opp_bars / max(n_bars, 1)

    # Body/range ratio (avg across leg bars)
    body_range_ratios = []
    for i in range(n_bars):
        rng = hi[i] - lo[i]
        body = abs(cl[i] - op[i])
        body_range_ratios.append(body / rng if rng > 0 else 0.0)
    avg_body_range = float(np.mean(body_range_ratios)) if body_range_ratios else 0.0

    # Leg length (ATR-normalised)
    leg_length_ticks = int(leg["length_ticks"])
    leg_length_atr   = (leg_length_ticks * TICK_SIZE) / max(atr_at_start, TICK_SIZE)

    # Close position in bar range (last bar — trend bar one-sidedness)
    last_rng = hi[-1] - lo[-1]
    last_close_pos = (cl[-1] - lo[-1]) / last_rng if last_rng > 0 else 0.5

    # Time features (from start of leg)
    start_dt = pd.Timestamp(leg["start_dt"])
    time_bucket     = _time_bucket(start_dt)
    mins_into_sess  = _minutes_into_session(start_dt)

    # EMA distance at leg start (ATR-normalised)
    start_idx = int(leg["start_idx"])
    ema_val   = ema_arr[start_idx] if start_idx < len(ema_arr) else np.nan
    start_price = float(leg["start_price"])
    ema_dist_atr = (start_price - ema_val) / max(atr_at_start, TICK_SIZE) if not np.isnan(ema_val) else np.nan

    return {
        "slope_ticks_per_bar":  slope_ticks,
        "overlap_pct":          overlap_pct,
        "opp_bar_frac":         opp_bar_frac,
        "avg_body_range_ratio": avg_body_range,
        "length_bars":          n_bars,
        "length_ticks":         leg_length_ticks,
        "length_atr":           leg_length_atr,
        "last_close_pos":       last_close_pos,
        "time_bucket":          time_bucket,
        "mins_into_session":    mins_into_sess,
        "ema_dist_atr":         ema_dist_atr,
    }


# ── Section 5.2 — Parent-relative features ────────────────────────────────────

def _parent_features(
    leg: pd.Series,
    legs: pd.DataFrame,
    labels: pd.DataFrame,
    bars_5m: pd.DataFrame,
    atr_at_start: float,
) -> dict:
    """
    Compute parent-relative features: leg index, prior same-direction leg
    comparison, always-in state, negation test, momentum decay.
    """
    lid        = int(leg["leg_id"])
    direction  = int(leg["direction"])
    start_idx  = int(leg["start_idx"])
    start_price = float(leg["start_price"])
    end_price   = float(leg["end_price"])

    # All prior confirmed same-direction legs (to test against)
    prior_same = legs[
        (legs["direction"] == direction) &
        (legs["leg_id"]    < lid) &
        (legs["phase"]     == "confirmed")
    ]

    leg_index_n        = len(prior_same) + 1   # 1 = first leg, 2 = second, etc.
    has_prior_same_dir = int(len(prior_same) > 0)

    # Distance from this leg's extreme to prior same-direction extreme
    dist_to_prior_extreme_ticks = np.nan
    prior_extreme_delta         = np.nan
    if has_prior_same_dir:
        prior_leg = prior_same.iloc[-1]
        prior_ext = float(prior_leg["end_price"])
        dist_to_prior_extreme_ticks = (end_price - prior_ext) / TICK_SIZE * direction
        # Positive → this leg exceeded prior extreme (continuation / overshoot)
        # Negative → this leg fell short of prior extreme (stall / fail)
        prior_extreme_delta = dist_to_prior_extreme_ticks

    # Always-in state proxy: direction of the most recent confirmed leg
    # A stale flip (many bars ago) → PB context; fresh → impulse context
    prior_leg_any = legs[legs["leg_id"] < lid]
    always_in_dir = 0
    bars_since_flip = np.nan
    if not prior_leg_any.empty:
        last_prior = prior_leg_any.iloc[-1]
        always_in_dir   = int(last_prior["direction"])
        # Bars since the flip bar (= start_idx of current leg)
        prev_end_idx = int(last_prior["end_idx"])
        bars_since_flip = max(start_idx - prev_end_idx, 0)

    ai_with_leg      = int(always_in_dir == direction)   # 1 = impulse context
    ai_against_leg   = int(always_in_dir == -direction)  # 1 = PB context

    # Negation test: did this leg break beyond the origin of the move it counters?
    # "Origin of move it counters" = end_price of last OPPOSITE direction leg
    prior_opp = legs[
        (legs["direction"] == -direction) &
        (legs["leg_id"]    < lid) &
        (legs["phase"]     == "confirmed")
    ]
    broke_counter_origin = 0
    stalled_at_retrace   = 0
    retrace_depth_pct    = np.nan
    if not prior_opp.empty:
        last_opp = prior_opp.iloc[-1]
        opp_origin = float(last_opp["start_price"])
        opp_extent = float(last_opp["end_price"])
        opp_length = abs(opp_extent - opp_origin)

        # Broke beyond origin of counter move → impulse signal
        if direction == 1 and end_price > opp_origin:
            broke_counter_origin = 1
        elif direction == -1 and end_price < opp_origin:
            broke_counter_origin = 1

        # Retrace depth into prior opposite leg
        if opp_length > 0:
            if direction == 1:
                retrace = (end_price - opp_extent) / opp_length
            else:
                retrace = (opp_extent - end_price) / opp_length
            retrace_depth_pct = float(np.clip(retrace, -0.5, 2.0))
            # Stalled at classic retrace levels (38–62%)
            if 0.33 <= retrace_depth_pct <= 0.76:
                stalled_at_retrace = 1

    # Momentum decay (wedge / 3-push detection)
    slope_decay         = np.nan
    size_decay_ratio    = np.nan
    if has_prior_same_dir and len(prior_same) >= 2:
        cur_size   = float(leg["length_ticks"])
        prev_size  = float(prior_same.iloc[-1]["length_ticks"])
        size_decay_ratio = cur_size / max(prev_size, 1)   # <1 = shrinking = wedge

        cur_slope  = float(leg["length_ticks"]) / max(int(leg["length_bars"]), 1)
        prev_slope = float(prior_same.iloc[-1]["length_ticks"]) / max(int(prior_same.iloc[-1]["length_bars"]), 1)
        if prev_slope > 0:
            slope_decay = cur_slope / prev_slope   # <1 = decelerating

    # Reversal context before this leg (count of doji/extreme bars in prior 5 bars)
    reversal_bar_count = 0
    if start_idx >= 5:
        pre_bars = bars_5m.iloc[max(start_idx - 5, 0):start_idx]
        for _, b in pre_bars.iterrows():
            rng = float(b["High"]) - float(b["Low"])
            body = abs(float(b["Close"]) - float(b["Open"]))
            # Doji/inside bar proxy: small body relative to range
            if rng > 0 and (body / rng) < 0.25:
                reversal_bar_count += 1

    return {
        "leg_index_n":               leg_index_n,
        "has_prior_same_dir":        has_prior_same_dir,
        "prior_extreme_delta_ticks": prior_extreme_delta,
        "ai_with_leg":               ai_with_leg,
        "ai_against_leg":            ai_against_leg,
        "bars_since_flip":           bars_since_flip,
        "broke_counter_origin":      broke_counter_origin,
        "stalled_at_retrace":        stalled_at_retrace,
        "retrace_depth_pct":         retrace_depth_pct,
        "slope_decay_ratio":         slope_decay,
        "size_decay_ratio":          size_decay_ratio,
        "reversal_bar_count_pre":    reversal_bar_count,
    }


# ── Section 5.3 — HTF context features ───────────────────────────────────────

def _htf_features(leg: pd.Series, htf_ctx: pd.DataFrame) -> dict:
    """
    Extract HTF context at the first bar of the leg (causal: uses prior closed HTF bars).
    htf_ctx : output of leg_htf.build_htf_context(), aligned to bars_5m.
    """
    start_idx = int(leg["start_idx"])
    if start_idx >= len(htf_ctx):
        return {k: np.nan for k in [
            "htf_direction", "htf_leg_id", "htf_leg_bars",
            "htf_k", "htf_retrace_pct", "htf_broke_struct", "htf_has_pb",
            "htf_bar_range_rel", "htf_with_leg", "htf_against_leg",
        ]}

    row = htf_ctx.iloc[start_idx]
    direction = int(leg["direction"])
    htf_dir   = int(row.get("htf_direction", 0))

    return {
        "htf_direction":      htf_dir,
        "htf_leg_id":         int(row.get("htf_leg_id", 0)),
        "htf_leg_bars":       int(row.get("htf_leg_bars", 0)),
        "htf_k":              int(row.get("htf_k", 0)),
        "htf_retrace_pct":    float(row.get("htf_retrace_pct", np.nan)),
        "htf_broke_struct":   int(row.get("htf_broke_struct", 0)),
        "htf_has_pb":         int(row.get("htf_has_pb", 0)),
        "htf_bar_range_rel":  float(row.get("htf_bar_range", np.nan)),
        "htf_with_leg":       int(htf_dir == direction),
        "htf_against_leg":    int(htf_dir == -direction),
    }


# ── Section 5.4 — Order flow features ─────────────────────────────────────────

def _flow_features(leg: pd.Series, flow_per_leg: pd.DataFrame | None) -> dict:
    """Join pre-computed per-leg flow summary."""
    empty = {
        "leg_delta": np.nan, "leg_buy_vol": np.nan, "leg_sell_vol": np.nan,
        "leg_total_vol": np.nan, "delta_slope": np.nan,
        "delta_divergence": np.nan, "effort_vs_result": np.nan,
    }
    if flow_per_leg is None:
        return empty
    lid = int(leg["leg_id"])
    if lid not in flow_per_leg.index:
        return empty
    row = flow_per_leg.loc[lid]
    return {
        "leg_delta":          float(row.get("leg_delta", np.nan)),
        "leg_buy_vol":        float(row.get("leg_buy_vol", np.nan)),
        "leg_sell_vol":       float(row.get("leg_sell_vol", np.nan)),
        "leg_total_vol":      float(row.get("leg_total_vol", np.nan)),
        "delta_slope":        float(row.get("delta_slope", np.nan)),
        "delta_divergence":   float(row.get("delta_divergence", np.nan)),
        "effort_vs_result":   float(row.get("effort_vs_result", np.nan)),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def build_feature_matrix(
    bars_5m: pd.DataFrame,
    labels: pd.DataFrame,
    legs: pd.DataFrame,
    htf_ctx: pd.DataFrame | None = None,
    flow_per_leg: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build the full per-leg feature matrix (spec §5.1–5.4).

    Parameters
    ----------
    bars_5m     : 5M OHLCV bars (DateTime, Open, High, Low, Close, Volume)
    labels      : output of leg_decomp.bar_labels()
    legs        : output of leg_decomp.leg_table()
    htf_ctx     : output of leg_htf.build_htf_context() — optional, adds §5.3 features
    flow_per_leg: output of leg_flow.aggregate_flow_per_leg() — optional, adds §5.4

    Returns
    -------
    DataFrame with one row per leg. Index = leg_id.
    All features are causal (no lookahead into the leg's future).

    Notes
    -----
    - Confirmed legs only (phase == 'confirmed'). The last (forming) leg is excluded
      because its geometry is incomplete.
    - Flow features are NaN when flow_per_leg is None.
    - HTF features are NaN when htf_ctx is None.
    """
    bars_r  = bars_5m.reset_index(drop=True).copy()
    labels_r = labels.reset_index(drop=True).copy()

    close_arr = bars_r["Close"].to_numpy(dtype=float)
    ema_arr   = _ema(close_arr, EMA_PERIOD)

    confirmed_legs = legs[legs["phase"] == "confirmed"].copy()

    rows = []
    for _, leg in confirmed_legs.iterrows():
        start_idx = int(leg["start_idx"])
        end_idx   = int(leg["end_idx"])
        leg_bars  = bars_r.iloc[start_idx : end_idx + 1]

        atr_at_start = float(labels_r.iloc[start_idx]["atr"])
        if np.isnan(atr_at_start):
            hi = bars_r["High"].to_numpy(dtype=float)
            lo = bars_r["Low"].to_numpy(dtype=float)
            cl = bars_r["Close"].to_numpy(dtype=float)
            rng = hi[start_idx] - lo[start_idx]
            atr_at_start = max(rng, TICK_SIZE)

        feat: dict = {"leg_id": int(leg["leg_id"]), "direction": int(leg["direction"])}

        feat.update(_local_features(leg, leg_bars, ema_arr, atr_at_start))
        feat.update(_parent_features(leg, legs, labels_r, bars_r, atr_at_start))

        if htf_ctx is not None:
            htf_r = htf_ctx.reset_index(drop=True)
            feat.update(_htf_features(leg, htf_r))
        else:
            feat.update({k: np.nan for k in [
                "htf_direction", "htf_leg_id", "htf_leg_bars",
                "htf_k", "htf_retrace_pct", "htf_broke_struct", "htf_has_pb",
                "htf_bar_range_rel", "htf_with_leg", "htf_against_leg",
            ]})

        feat.update(_flow_features(leg, flow_per_leg))

        # Identity fields for later joining
        feat["start_dt"]    = leg["start_dt"]
        feat["end_dt"]      = leg["end_dt"]
        feat["start_price"] = float(leg["start_price"])
        feat["end_price"]   = float(leg["end_price"])
        feat["phase"]       = str(leg["phase"])

        rows.append(feat)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.set_index("leg_id")
    return df


# ── Feature column registry ───────────────────────────────────────────────────

FEATURE_COLS = [
    # §5.1 local geometry
    "slope_ticks_per_bar", "overlap_pct", "opp_bar_frac",
    "avg_body_range_ratio", "length_bars", "length_ticks", "length_atr",
    "last_close_pos", "time_bucket", "mins_into_session", "ema_dist_atr",
    # §5.2 parent-relative
    "leg_index_n", "has_prior_same_dir", "prior_extreme_delta_ticks",
    "ai_with_leg", "ai_against_leg", "bars_since_flip",
    "broke_counter_origin", "stalled_at_retrace", "retrace_depth_pct",
    "slope_decay_ratio", "size_decay_ratio", "reversal_bar_count_pre",
    # §5.3 HTF context
    "htf_direction", "htf_leg_id", "htf_leg_bars", "htf_k",
    "htf_retrace_pct", "htf_broke_struct", "htf_has_pb",
    "htf_bar_range_rel", "htf_with_leg", "htf_against_leg",
    # §5.4 order flow
    "leg_delta", "leg_buy_vol", "leg_sell_vol", "leg_total_vol",
    "delta_slope", "delta_divergence", "effort_vs_result",
]
