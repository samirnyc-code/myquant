"""stack_filter.py — the S53 "Stack v2" one-click MC filter (frozen spec).

One shared definition consumed by the Bar Analyzer filter panel (and, through
``ba_results``, the Prop tab) so the app reproduces the S53 Fable-agent research
numbers exactly. Spec source: docs/living/fable5_mc_findings.md (Rounds 1-4).

THE FROZEN RULES (all causal — computable at the signal bar's close):

  Skip filters (drop the signal if ANY fires):
    F1  counter-IB-break — IB = first 12 RTH bars (08:30-09:30 CT). A break
        exists from the CLOSE of the first post-IB bar whose High > IB_High
        (up) / Low < IB_Low (down). Skip Longs while the day's break state is
        down-only; skip Shorts while it is up-only. ('both' and 'none' pass.)
    F2  prior trend day — prior session range > 1.6×ADR(14)
        (= tag_signals ``prior_adr_ext``, the S25 hard-skip).
    F3  late session — signal bar closes at/after 14:00 CT.

  Tier features (size 2 units when ANY is true, else 1):
    bal   balance_state (tag_signals: opened inside prior range, still rotating)
    bwva  Long below the prior WEEK's Value Area Low (vaW_pos < 0)
    mss   mss_event (market-structure shift at the signal bar)
    pull  pullback from the developing session extreme >= 0.86 × ABR20, where
          ABR20 = 20-session rolling mean (shifted 1 day) of the per-session
          mean bar range, and pullback = dev_High - SignalPrice for Longs /
          SignalPrice - dev_Low for Shorts.

Exits are NOT applied here (they are simulation settings): the researched book
uses target 3R + ratchet-to-BE at +1R + EOD flat, which the Bar Analyzer's
existing target/ratchet controls express directly. The 6c bail rule (exit at
the close of the bar after the entry bar if >50% of stop against) is not yet
in the engine — numbers with the filter alone match the no-bail book.

Bars are OPEN-labeled (bar DateTime = bar open); signal DateTime = signal bar
CLOSE = the next bar's open label. All time comparisons below follow the same
convention the research used (break confirmed at breaking-bar label + 5 min).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import indicators

IB_BARS = 12          # first 60 minutes of RTH on 5M bars
LATE_CUTOFF_MIN = 840  # 14:00 CT, minutes past midnight (signal-close stamped)
PULL_ABR_MIN = 0.86    # pullback-from-extreme tier threshold (× ABR20)

TIER_FEATURES = ("bal", "bwva", "mss", "pull")


# ── feature computation ───────────────────────────────────────────────────────

def _ib_break_state(signals: pd.DataFrame, bars: pd.DataFrame) -> pd.Series:
    """Per-signal IB break state at the signal's DateTime: none/up/down/both.

    Break time = close label of the first post-IB bar whose High/Low exceeds
    the IB extreme (S60: labels are closes — when the break is knowable). A
    signal is 'after' a break when its close-stamped DateTime >= that break close.
    """
    b = bars.sort_values("DateTime").reset_index(drop=True)
    day = b["DateTime"].dt.normalize()
    b = b.assign(_d=day, _i=b.groupby(day).cumcount())

    ib = b[b["_i"] < IB_BARS]
    ib_hi = ib.groupby("_d")["High"].max()
    ib_lo = ib.groupby("_d")["Low"].min()

    post = b[b["_i"] >= IB_BARS].copy()
    post["_ibH"] = post["_d"].map(ib_hi)
    post["_ibL"] = post["_d"].map(ib_lo)
    # S60 close labels: the break bar's label already IS its close (when the
    # break is knowable) — no +5m shift needed.
    up_t = post.loc[post["High"] > post["_ibH"]].groupby("_d")["DateTime"].min()
    dn_t = post.loc[post["Low"] < post["_ibL"]].groupby("_d")["DateTime"].min()

    s_day = signals["DateTime"].dt.normalize()
    s_up = s_day.map(up_t)
    s_dn = s_day.map(dn_t)
    up_done = s_up.notna() & (s_up <= signals["DateTime"])
    dn_done = s_dn.notna() & (s_dn <= signals["DateTime"])
    return pd.Series(
        np.select([up_done & dn_done, up_done, dn_done],
                  ["both", "up", "down"], default="none"),
        index=signals.index)


def _abr20(bars: pd.DataFrame) -> pd.Series:
    """ABR20 per session date: 20-session rolling mean (shifted 1 — prior
    sessions only) of the session's mean bar range."""
    day = bars["DateTime"].dt.normalize()
    per_day = (bars["High"] - bars["Low"]).groupby(day).mean()
    return per_day.rolling(20, min_periods=10).mean().shift(1)


def compute_stack_columns(signals: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Return a frame aligned to ``signals`` (original index) with:

      stack_pass       bool — passes all three skip filters
      stack_skip       ''/'ib_counter'/'prior_trend'/'late' (first rule that fired)
      stack_tier       1 or 2 — researched sizing tier (2 if any tier feature)
      stack_bal/bwva/mss/pull — the individual tier features (bool)

    ``signals`` needs DateTime, Direction, SignalPrice. Tagging columns are
    taken from ``signals`` when already present (a tagged frame) or computed
    via indicators.tag_signals otherwise.
    """
    need = {"balance_state", "mss_event", "prior_adr_ext",
            "dev_High", "dev_Low", "vaW_VAH", "vaW_VAL"}
    if need.issubset(signals.columns):
        t = signals
    else:
        t = indicators.tag_signals(signals.assign(_sf_id=np.arange(len(signals))), bars)
        t = t.sort_values("_sf_id").set_index(signals.index).drop(columns="_sf_id")

    is_long = t["Direction"].astype(str).str.upper().str.startswith("L")
    px = t["SignalPrice"].astype(float)

    # F1 — counter-IB-break
    ib_state = _ib_break_state(t, bars)
    counter = ((is_long & (ib_state == "down")) |
               (~is_long & (ib_state == "up")))

    # F2 — prior trend day (S25 flag from tag_signals)
    prior_trend = t["prior_adr_ext"].fillna(False).astype(bool)

    # F3 — late session (signal close >= 14:00 CT)
    tod = t["DateTime"].dt.hour * 60 + t["DateTime"].dt.minute
    late = tod >= LATE_CUTOFF_MIN

    stack_pass = ~(counter | prior_trend | late)
    skip = np.select([counter, prior_trend, late],
                     ["ib_counter", "prior_trend", "late"], default="")

    # ── tier features ────────────────────────────────────────────────────────
    bal = t["balance_state"].fillna(False).astype(bool)
    mss = t["mss_event"].fillna(False).astype(bool)

    va_w = (t["vaW_VAH"] - t["vaW_VAL"]).replace(0, np.nan)
    vaw_pos = (px - t["vaW_VAL"]) / va_w
    bwva = (is_long & (vaw_pos < 0)).fillna(False)

    abr = t["DateTime"].dt.normalize().map(_abr20(bars))
    pull_pts = np.where(is_long, t["dev_High"] - px, px - t["dev_Low"])
    pull = pd.Series(pull_pts / abr.to_numpy(), index=t.index) >= PULL_ABR_MIN
    pull = pull.fillna(False)

    tier = np.where(bal | bwva | mss | pull, 2, 1)

    return pd.DataFrame({
        "stack_pass": stack_pass.to_numpy(),
        "stack_skip": skip,
        "stack_tier": tier,
        "stack_bal": bal.to_numpy(),
        "stack_bwva": bwva.to_numpy(),
        "stack_mss": mss.to_numpy(),
        "stack_pull": pull.to_numpy(),
    }, index=signals.index)


# ── Bar Analyzer integration ─────────────────────────────────────────────────

def apply_stack_filter(df: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Mark FilterStatus for signals failing Stack v2 and attach the tier
    columns. Follows the apply_*_filters convention: only rows currently 'ok'
    are re-marked; already-excluded rows keep their first exclusion reason.
    """
    if df.empty:
        return df
    cols = compute_stack_columns(df, bars)
    df = df.join(cols)
    ok = df["FilterStatus"] == "ok"
    df.loc[ok & ~df["stack_pass"],
           "FilterStatus"] = "stack_" + df.loc[ok & ~df["stack_pass"], "stack_skip"]
    return df


def describe() -> str:
    """One-line spec string for run notes / captions."""
    return ("Stack v2 (S53): skip counter-IB-break + prior-trend-day + ≥14:00 CT; "
            f"tier 2x on bal/bwva/mss/pull≥{PULL_ABR_MIN}×ABR20. "
            "Researched exits: 3R target, BE at +1R, EOD flat.")
