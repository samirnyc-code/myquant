"""indicators.py — session VWAP σ-bands + volume-profile value areas.

Indicators are computed ONCE over the full continuous 5M series, then joined onto
signals by an as-of (look-ahead-safe) lookup. One definition, shared by Bar
Analysis research, WFA validation, and the future NT robot.

Two families (both volume-aware, both derived purely from bars — no external API):

  • session VWAP σ-bands — developing (causal) session VWAP and its volume-weighted
    standard deviation; `VWAP_dev` = signed σ-distance of Close from VWAP.
  • volume-profile value areas — per RTH session POC / VAH / VAL via a volume-at-price
    histogram (70% rule). Used to contextualize the FOLLOWING session (prior-day value),
    which is naturally look-ahead-safe.

Look-ahead rule: a signal at bar T is tagged with (a) the developing VWAP using bars
≤ T only, and (b) the PRIOR completed session's value area. Never the session's final
value, never today's value area.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import TICK_SIZE


def _typical(bars: pd.DataFrame) -> pd.Series:
    return (bars["High"] + bars["Low"] + bars["Close"]) / 3.0


def session_vwap_bands(bars: pd.DataFrame, warmup_bars: int = 3) -> pd.DataFrame:
    """Per-bar developing session VWAP + volume-weighted σ (resets each RTH day).

    Returns a frame aligned to `bars` (by DateTime) with:
      VWAP        — developing session VWAP up to and including this bar
      VWAP_sigma  — volume-weighted std-dev of typical price from VWAP so far
      VWAP_dev    — signed σ-distance of Close from VWAP (the 'deviation')

    `warmup_bars` — VWAP_dev is meaningless in the first bars of a session (σ not
    yet established → division by ~0 explodes). For the first `warmup_bars` bars of
    each session VWAP_dev is set NaN, so downstream filters treat it as 'no reading'
    rather than a spurious extreme. VWAP/σ themselves are kept.
    """
    df  = bars.sort_values("DateTime").reset_index(drop=True)
    day = df["DateTime"].dt.normalize()
    tp  = _typical(df)
    vol = df["Volume"].astype(float).clip(lower=0)

    tmp = pd.DataFrame({
        "_vol": vol,
        "_pv":  tp * vol,
        "_pv2": tp * tp * vol,
    })
    g       = tmp.groupby(day)
    cum_vol = g["_vol"].cumsum().replace(0, np.nan)
    cum_pv  = g["_pv"].cumsum()
    cum_pv2 = g["_pv2"].cumsum()

    vwap  = cum_pv / cum_vol
    var   = (cum_pv2 / cum_vol) - vwap ** 2
    sigma = np.sqrt(var.clip(lower=0))
    dev   = (df["Close"] - vwap) / sigma.replace(0, np.nan)

    # warmup guard — null out unstable early-session deviations
    bar_in_session = g.cumcount()  # 0-indexed within each session
    dev = dev.where(bar_in_session >= warmup_bars)

    return pd.DataFrame({
        "DateTime":   df["DateTime"],
        "VWAP":       vwap,
        "VWAP_sigma": sigma,
        "VWAP_dev":   dev,
    })


# Period aliases → pandas period frequency. "session"/"daily" use calendar day,
# which == one RTH session for this RTH-only series.
_PERIOD_FREQ = {
    "session":   "D", "daily": "D",
    "weekly":    "W", "monthly": "M",
    "quarterly": "Q", "yearly":  "Y",
}
# Short prefix per period for tagged columns.
_PERIOD_PREFIX = {
    "session": "vaD", "daily": "vaD",
    "weekly":  "vaW", "monthly": "vaM",
    "quarterly": "vaQ", "yearly": "vaY",
}


def _profile_value_area(prices: np.ndarray, vols: np.ndarray,
                        va_pct: float) -> tuple[float, float, float]:
    """POC / VAL / VAH from a price→volume profile (greedy 70%-rule expansion)."""
    total  = vols.sum()
    target = va_pct * total
    poc = int(np.argmax(vols))
    lo = hi = poc
    acc = vols[poc]
    while acc < target and (lo > 0 or hi < len(vols) - 1):
        left  = vols[lo - 1] if lo > 0 else -1.0
        right = vols[hi + 1] if hi < len(vols) - 1 else -1.0
        if right >= left:
            hi += 1
            acc += vols[hi]
        else:
            lo -= 1
            acc += vols[lo]
    return float(prices[poc]), float(prices[lo]), float(prices[hi])


def value_areas(bars: pd.DataFrame,
                period: str = "session",
                va_pct: float = 0.70,
                bucket_ticks: int = 4) -> pd.DataFrame:
    """Value area (POC/VAH/VAL) per period from a volume-at-price profile.

    `period` ∈ {session, weekly, monthly, quarterly, yearly}. Each bar's volume is
    assigned to its typical-price bucket (`bucket_ticks` ticks/bucket — default
    1 ES point). POC = heaviest bucket; expand outward (greedy, heavier side) until
    `va_pct` of period volume is captured → VAL / VAH.

    Returns one row per period: PeriodKey (pandas Period), POC, VAH, VAL, Vol.
    """
    freq   = _PERIOD_FREQ[period]
    bucket = TICK_SIZE * bucket_ticks
    pk     = bars["DateTime"].dt.to_period(freq)
    out: list[dict] = []

    for key, g in bars.groupby(pk):
        tp   = _typical(g)
        keys = (tp / bucket).round() * bucket
        prof = g["Volume"].groupby(keys).sum().sort_index()
        if prof.empty or prof.sum() <= 0:
            continue
        poc, val, vah = _profile_value_area(
            prof.index.to_numpy(dtype=float), prof.to_numpy(dtype=float), va_pct)
        out.append({"PeriodKey": key, "POC": poc, "VAL": val, "VAH": vah,
                    "Vol": float(prof.sum())})

    return pd.DataFrame(out)


def session_value_areas(bars: pd.DataFrame, **kw) -> pd.DataFrame:
    """Back-compat: per-session value areas with a `Date` column."""
    va = value_areas(bars, "session", **kw)
    va["Date"] = va["PeriodKey"].dt.to_timestamp().dt.date
    return va.rename(columns={"Vol": "SessionVol"})[
        ["Date", "POC", "VAL", "VAH", "SessionVol"]]


def _daily_ohlc(bars: pd.DataFrame) -> pd.DataFrame:
    g = bars.groupby(bars["DateTime"].dt.normalize())
    d = pd.DataFrame({"High": g["High"].max(), "Low": g["Low"].min(),
                      "Close": g["Close"].last(), "Open": g["Open"].first()})
    return d.sort_index()


def _wilder_atr(daily: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def _wilder_adx(daily: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    up, down = h.diff(), -l.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev = c.shift(1)
    tr  = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False).mean().replace(0, np.nan)
    plus_di  = 100 * pd.Series(plus_dm,  index=daily.index).ewm(alpha=1.0 / n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=daily.index).ewm(alpha=1.0 / n, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / n, adjust=False).mean()


def daily_regime(bars: pd.DataFrame, atr_n: int = 14, adx_n: int = 14,
                 pct_window: int = 252) -> pd.DataFrame:
    """Per-day volatility/trend regime (causal). Indexed by normalized day.

      ATR      — Wilder ATR(atr_n) in points
      ATR_pct  — percentile rank of today's ATR within the trailing `pct_window`
                 days (0–1); comparable across years, the form to bucket on
      ADX      — Wilder ADX(adx_n), 0–100 trend-strength index
      ADX_pct  — percentile rank of today's ADX within the trailing window (0–1)
    """
    d   = _daily_ohlc(bars)
    atr = _wilder_atr(d, atr_n)
    adx = _wilder_adx(d, adx_n)
    _pctile = lambda s: s.rolling(pct_window, min_periods=20).apply(
        lambda x: (x <= x[-1]).mean(), raw=True)
    return pd.DataFrame({"ATR": atr, "ATR_pct": _pctile(atr),
                         "ADX": adx, "ADX_pct": _pctile(adx)})


def prior_period_levels(bars: pd.DataFrame, target_dt: pd.Series,
                        period: str) -> pd.DataFrame:
    """For each timestamp in `target_dt`, the PRIOR period's POC/VAH/VAL.

    `shift(1)` over existing periods = previous *completed* period (robust to
    calendar gaps/holidays), so the value area is always already finished → no
    look-ahead. Returns a frame (POC/VAH/VAL) indexed like `target_dt`. Shared by
    both `tag_signals` (the entry filter) and the chart overlay — one definition.
    """
    freq = _PERIOD_FREQ[period]
    va   = value_areas(bars, period).sort_values("PeriodKey")
    m    = va.set_index("PeriodKey")
    pk   = pd.to_datetime(target_dt).dt.to_period(freq)
    return pd.DataFrame({
        "POC": pk.map(m["POC"].shift(1)).values,
        "VAH": pk.map(m["VAH"].shift(1)).values,
        "VAL": pk.map(m["VAL"].shift(1)).values,
    }, index=target_dt.index)


def tag_signals(signals: pd.DataFrame, bars: pd.DataFrame,
                periods: tuple = ("session", "weekly", "monthly",
                                  "quarterly", "yearly")) -> pd.DataFrame:
    """Attach look-ahead-safe indicator columns to each signal row.

    VWAP (causal, at the signal bar):
      VWAP, VWAP_sigma, VWAP_dev — developing session VWAP and signed σ-deviation.

    Value areas — for each period in `periods`, the PRIOR period's levels (so the
    value area is always already complete → no look-ahead). Columns per period use a
    prefix (vaD=session, vaW=weekly, vaM=monthly, vaQ=quarterly, vaY=yearly):
      {p}_POC/VAH/VAL — prior period's value-area levels
      {p}_loc         — 'above' / 'inside' / 'below' (signal price vs that value area)
      {p}_dist        — signed points outside value (>0 above VAH, <0 below VAL, 0 inside)
    """
    sig = signals.copy()

    # ── VWAP deviation at the signal bar (as-of merge on DateTime) ────────────
    vb = session_vwap_bands(bars)[["DateTime", "VWAP", "VWAP_sigma", "VWAP_dev"]]
    sig = sig.sort_values("DateTime")
    sig = pd.merge_asof(
        sig, vb.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # signal price — prefer an explicit price column, fall back to causal VWAP
    px_col = next((c for c in ("Price", "SignalPrice", "Close", "EntryPrice")
                   if c in sig.columns), None)
    px = sig[px_col].astype(float) if px_col else sig["VWAP"]

    # ── Prior-day regime (ATR / ATR percentile / ADX) — look-ahead-safe ───────
    reg   = daily_regime(bars).shift(1)          # prior trading day's completed values
    s_day = pd.to_datetime(sig["DateTime"]).dt.normalize()
    sig["prior_ATR"]     = s_day.map(reg["ATR"]).values
    sig["prior_ATR_pct"] = s_day.map(reg["ATR_pct"]).values
    sig["prior_ADX"]     = s_day.map(reg["ADX"]).values
    sig["prior_ADX_pct"] = s_day.map(reg["ADX_pct"]).values

    # ── Prior-period value areas (one block per timeframe) ────────────────────
    for period in periods:
        prefix = _PERIOD_PREFIX[period]
        lv  = prior_period_levels(bars, sig["DateTime"], period)
        poc, vah, val = lv["POC"], lv["VAH"], lv["VAL"]

        above = px > vah
        below = px < val
        sig[f"{prefix}_POC"] = poc.values
        sig[f"{prefix}_VAH"] = vah.values
        sig[f"{prefix}_VAL"] = val.values
        sig[f"{prefix}_loc"] = np.select([above.values, below.values],
                                         ["above", "below"], default="inside")
        sig[f"{prefix}_dist"] = np.where(above, (px - vah),
                                np.where(below, (px - val), 0.0))

    return sig
