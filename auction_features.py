"""auction_features.py — per-session auction/market-profile feature library.

One row per RTH session. Every feature is derived purely from the RTH 5M bars
(plus optional ETH overnight levels) so it is reproducible and look-ahead-safe
when consumed correctly:

  • Within-session descriptive features (IB, range, value area, day-type) describe
    the COMPLETED session — use them as *yesterday's* context (the table exposes
    prior_* columns already shifted by one session).
  • Cross-session features (gap, open-location, VA migration) compare today's OPEN
    to the PRIOR completed session — these ARE known at today's open, so they are
    safe as same-day inputs.

This is the foundation other tools query: the day-type classifier, the gap study,
and a future pattern scanner. It deliberately does NOT bolt anything into the sim
— it builds the feature matrix once; mining happens on top.

v1 scope: IB + extension, range/ADR (DR%), open/close location, value area
(POC/VAH/VAL/width + skew), gap classification + same-session fill, open location
vs prior range/VA, Dalton day-type label, VA migration vs prior.

Deferred (phase 2, documented): HVN/LVN shelves, double-distribution (B) detection,
single/zero prints, full TPO profiles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as ind
from data_loader import TICK_SIZE

# First 60 minutes = Initial Balance. 08:30 CT open, 5M bars → first 12 bars.
IB_BARS = 12
ADR_WINDOW = 14
TREND_MULT = 1.6          # range > TREND_MULT × ADR is "trend-sized"


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_div(a, b):
    return a / b if b else np.nan


def _loc_in_range(x, lo, hi):
    """Where x sits in [lo, hi] as 0..1 (0=at low, 1=at high). NaN if no range."""
    rng = hi - lo
    return (x - lo) / rng if rng > 0 else np.nan


def _session_bimodal(g: pd.DataFrame, bucket_ticks: int = 4) -> bool:
    """True if the session's volume-at-price profile is double-humped.

    Dalton's Double-Distribution day builds a SECOND distribution separated from
    the first by a low-volume gap (single prints). Detect ≥2 prominent peaks
    (each > 50% of the max bucket) separated by a valley < 35% of the smaller
    peak — the structural fingerprint of two distributions.
    """
    bucket = TICK_SIZE * bucket_ticks
    tp = (g["High"] + g["Low"] + g["Close"]) / 3.0
    keys = (tp / bucket).round() * bucket
    prof = g["Volume"].groupby(keys).sum().sort_index()
    if len(prof) < 5:
        return False
    v = prof.to_numpy(dtype=float)
    mx = v.max()
    # Two SUBSTANTIAL humps (each ≥ 60% of max), well separated (≥ 4 buckets),
    # with a deep valley between them (< 25% of the smaller hump) = single prints.
    peaks = [i for i in range(1, len(v) - 1)
             if v[i] >= 0.60 * mx and v[i] >= v[i - 1] and v[i] >= v[i + 1]]
    if len(peaks) < 2:
        return False
    p1, p2 = peaks[0], peaks[-1]
    if p2 - p1 < 4:
        return False
    valley = v[p1:p2 + 1].min()
    return valley < 0.25 * min(v[p1], v[p2])


# ── per-session feature build ─────────────────────────────────────────────────

def build_session_features(bars: pd.DataFrame,
                           eth_levels: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compute one feature row per RTH session.

    `bars`       : continuous RTH 5M OHLCV with DateTime (one session/date).
    `eth_levels` : optional per-Date frame (ETH_High/Low/Open/Close, PC_High/Low).

    Returns a DataFrame indexed 0..N-1, one row per session, sorted by Date.
    """
    b = bars.sort_values("DateTime").reset_index(drop=True)
    b["Date"] = b["DateTime"].dt.normalize()

    # Per-session value areas (POC/VAH/VAL) — reuse the existing engine.
    va = ind.session_value_areas(b)  # columns: Date, POC, VAL, VAH, SessionVol
    va_map = {pd.Timestamp(r.Date).normalize(): r for r in va.itertuples()}

    rows: list[dict] = []
    for date, g in b.groupby("Date"):
        g = g.reset_index(drop=True)
        if len(g) < 2:
            continue
        o = float(g["Open"].iloc[0])
        h = float(g["High"].max())
        l = float(g["Low"].min())
        c = float(g["Close"].iloc[-1])
        rng = h - l

        # Initial Balance (first 60 min)
        ib = g.iloc[:min(IB_BARS, len(g))]
        ib_hi = float(ib["High"].max())
        ib_lo = float(ib["Low"].min())
        ib_width = ib_hi - ib_lo

        # Range extension beyond IB (each side)
        ext_up = max(0.0, h - ib_hi)
        ext_dn = max(0.0, ib_lo - l)

        # Which side of the IB broke first (after the IB period)
        post = g.iloc[min(IB_BARS, len(g)):]
        first_break = "none"
        if not post.empty:
            up_hit = post.index[post["High"] > ib_hi]
            dn_hit = post.index[post["Low"] < ib_lo]
            first_up = up_hit.min() if len(up_hit) else np.inf
            first_dn = dn_hit.min() if len(dn_hit) else np.inf
            if first_up < first_dn:
                first_break = "up"
            elif first_dn < first_up:
                first_break = "down"

        vrow = va_map.get(pd.Timestamp(date).normalize())
        poc = float(vrow.POC) if vrow is not None else np.nan
        vah = float(vrow.VAH) if vrow is not None else np.nan
        val = float(vrow.VAL) if vrow is not None else np.nan
        va_width = (vah - val) if (vrow is not None and not np.isnan(vah)) else np.nan

        rows.append({
            "Date": pd.Timestamp(date).normalize(),
            "Open": o, "High": h, "Low": l, "Close": c, "Range": rng,
            "IB_High": ib_hi, "IB_Low": ib_lo, "IB_width": ib_width,
            "ext_up": ext_up, "ext_dn": ext_dn, "first_break": first_break,
            "CLV": _loc_in_range(c, l, h),       # close location 0..1
            "OLV": _loc_in_range(o, l, h),       # open  location 0..1
            "POC": poc, "VAH": vah, "VAL": val, "VA_width": va_width,
            "POC_loc": _loc_in_range(poc, l, h),
            "VA_skew": _safe_div(poc - (l + h) / 2.0, rng),  # +up-skew (P), -down (b)
            "bimodal": _session_bimodal(g),
            "Volume": float(g["Volume"].sum()) if "Volume" in g else np.nan,
        })

    f = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    if f.empty:
        return f

    # ── ADR + DR% (trailing mean of PRIOR daily ranges) ──────────────────────
    f["ADR"] = f["Range"].shift(1).rolling(ADR_WINDOW, min_periods=5).mean()
    f["DR_pct"] = f["Range"] / f["ADR"] * 100.0          # range as % of ADR

    # ── Prior-session context (shifted — known at today's open) ──────────────
    for col in ["High", "Low", "Close", "POC", "VAH", "VAL", "Range", "VA_width"]:
        f[f"prior_{col}"] = f[col].shift(1)

    # ── Gap (today open vs prior close) ──────────────────────────────────────
    f["gap"] = f["Open"] - f["prior_Close"]
    f["gap_adr"] = f["gap"] / f["ADR"]
    f["gap_abs_adr"] = f["gap_adr"].abs()
    f["gap_dir"] = np.sign(f["gap"]).map({1: "up", -1: "down", 0: "flat"})
    f["gap_bucket"] = pd.cut(
        f["gap_abs_adr"],
        bins=[-0.001, 0.1, 0.25, 0.5, np.inf],
        labels=["flat", "small", "medium", "large"])

    # Open location vs PRIOR range / value area
    f["open_vs_prior_range"] = np.select(
        [f["Open"] > f["prior_High"], f["Open"] < f["prior_Low"]],
        ["above", "below"], default="inside")
    f["open_vs_prior_va"] = np.select(
        [f["Open"] > f["prior_VAH"], f["Open"] < f["prior_VAL"]],
        ["above_VA", "below_VA"], default="inside_VA")

    # ── Same-session gap fill (did price return to prior close?) ──────────────
    fill = np.where(
        f["gap"] > 0, f["Low"] <= f["prior_Close"],
        np.where(f["gap"] < 0, f["High"] >= f["prior_Close"], True))
    f["gap_filled"] = fill.astype(bool)

    # ── Value-area migration vs prior ────────────────────────────────────────
    f["va_migration"] = np.select(
        [(f["VAL"] > f["prior_VAH"]),                       # fully higher
         (f["VAH"] < f["prior_VAL"]),                       # fully lower
         (f["POC"] > f["prior_POC"]),                       # overlap-higher
         (f["POC"] < f["prior_POC"])],                      # overlap-lower
        ["higher", "lower", "overlap_higher", "overlap_lower"],
        default="unchanged")

    # ── Day-type classification (Dalton, Mind Over Markets Ch.2) ─────────────
    f["day_type"] = _classify_day_type(f)
    f["neutral_subtype"] = np.where(
        f["day_type"] == "Neutral",
        np.where((f["CLV"] > 0.65) | (f["CLV"] < 0.35), "extreme", "center"),
        "")

    # Prior day-type (for transition studies — known at today's open)
    f["prior_day_type"] = f["day_type"].shift(1)
    f["prior_DR_pct"] = f["DR_pct"].shift(1)

    return f


def _classify_day_type(f: pd.DataFrame) -> pd.Series:
    """Day-type label per Dalton, *Mind Over Markets* Ch.2.

    Canonical types (conviction gradient, lowest → highest):
      Nontrend            — narrow IB, NO range extension; the other timeframe
                            never surfaces (the quiet rotational day).
      Normal              — WIDE IB ("base") not upset all day; both-side tails,
                            little/no extension; price rotates inside the base.
      Normal Variation    — moderate IB "tipped over" on ONE side by range
                            extension; two-timeframe, value shifts.
      Neutral             — range extension on BOTH sides of the IB (both other
                            timeframe participants active). Center vs Extreme by close.
      Double Distribution — SMALL IB, quiet open, then a LATE one-sided extension
                            to a SECOND distribution (bimodal profile).
      Trend               — open forms the extreme, one-timeframe directional all
                            day, thin elongated profile, closes at the extreme.

    Criteria are computed from RTH OHLC + IB + the session volume profile (no TPO).
    Tunable thresholds; faithful to the book's structural descriptions.
    """
    adr = f["ADR"].fillna(f["Range"].median())
    rng = f["Range"]
    ibw = f["IB_width"]
    clv = f["CLV"]
    olv = f["OLV"]
    eu, ed = f["ext_up"], f["ext_dn"]
    bimodal = f["bimodal"].fillna(False)

    # A range extension "tips over the base" only if it is a meaningful fraction
    # of the IB / ADR — a 1-2 tick poke past the IB is not Normal-Variation activity.
    ext_thr   = np.maximum(0.20 * adr, 0.40 * ibw)
    up_ext    = eu > ext_thr
    dn_ext    = ed > ext_thr
    both_ext  = up_ext & dn_ext
    one_ext   = up_ext ^ dn_ext
    no_ext    = ~up_ext & ~dn_ext

    trend_sz   = rng > TREND_MULT * adr
    at_extreme = (clv > 0.75) | (clv < 0.25)
    wide_ib    = ibw >= 0.55 * rng       # base contains most of the day
    quiet      = rng < 0.60 * adr        # genuinely inactive session

    out = np.full(len(f), "Normal Variation", dtype=object)   # most common default
    # No meaningful extension → Normal (wide base held) or Nontrend (quiet/narrow)
    out = np.where(no_ext &  wide_ib, "Normal",   out)
    out = np.where(no_ext & ~wide_ib & quiet, "Nontrend", out)
    # One-sided, trend-sized, closes at an extreme → Trend (one distribution) or
    # Double Distribution (two distributions separated by single prints = bimodal).
    trendy = one_ext & trend_sz & at_extreme
    out = np.where(trendy & ~bimodal, "Trend", out)
    out = np.where(trendy &  bimodal, "Double Distribution", out)
    # Both sides extended → Neutral (two-sided auction; overrides).
    out = np.where(both_ext, "Neutral", out)
    return pd.Series(out, index=f.index)


# ── studies on top of the feature matrix ──────────────────────────────────────

def day_type_transition_matrix(f: pd.DataFrame) -> pd.DataFrame:
    """P(today's day_type | yesterday's day_type) as a row-normalized matrix (%)."""
    d = f.dropna(subset=["prior_day_type", "day_type"])
    if d.empty:
        return pd.DataFrame()
    ct = pd.crosstab(d["prior_day_type"], d["day_type"], normalize="index") * 100.0
    ct.index.name = "yesterday \\ today"
    return ct.round(1)


def gap_outcome_study(f: pd.DataFrame) -> pd.DataFrame:
    """Per gap bucket × direction: fill rate, day return, close-vs-open bias."""
    d = f.dropna(subset=["gap_bucket", "gap_dir"]).copy()
    d = d[d["gap_dir"].isin(["up", "down"])]
    if d.empty:
        return pd.DataFrame()
    d["day_ret"] = d["Close"] - d["Open"]
    d["go_with"] = np.where(d["gap_dir"] == "up", d["day_ret"] > 0, d["day_ret"] < 0)
    g = d.groupby(["gap_dir", "gap_bucket"], observed=True)
    out = g.agg(
        n=("Date", "size"),
        fill_rate=("gap_filled", lambda s: round(s.mean() * 100, 1)),
        go_with_rate=("go_with", lambda s: round(s.mean() * 100, 1)),
        avg_day_ret=("day_ret", lambda s: round(s.mean(), 2)),
        med_day_ret=("day_ret", lambda s: round(s.median(), 2)),
    ).reset_index()
    return out
