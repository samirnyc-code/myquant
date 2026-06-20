"""indicators.py — regime indicators for signal bucketing.

Indicators are computed ONCE over the full continuous 5M series, then joined onto
signals by an as-of (look-ahead-safe) lookup. One definition, shared by Bar
Analysis research, WFA validation, and the future NT robot.

Families (all derived purely from bars — no external API except VIX):

  • session VWAP σ-bands — developing (causal) session VWAP and its volume-weighted
    standard deviation; `VWAP_dev` = signed σ-distance of Close from VWAP.
  • volume-profile value areas — per RTH session POC / VAH / VAL via a volume-at-price
    histogram (70% rule).
  • daily regime — ATR/ADX percentiles, Kaufman ER, range/ATR ratio.
  • session levels — Open of Day, prior-day High/Low, 60-min Opening Range.
  • intrabar context — developing 20-bar EMA at each 5M bar.

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
                 er_n: int = 10, pct_window: int = 252) -> pd.DataFrame:
    """Per-day volatility/trend regime (causal). Indexed by normalized day.

      ATR        — Wilder ATR(atr_n) in points
      ATR_pct    — percentile rank within trailing `pct_window` days (0–1)
      ADX        — Wilder ADX(adx_n), 0–100 trend-strength index
      ADX_pct    — percentile rank within trailing window (0–1)
      ER         — Kaufman Efficiency Ratio over `er_n` days (0–1)
      ER_pct     — percentile rank within trailing window (0–1)
      RangeATR   — prior-day range / ATR (compressed <0.6, extended >1.2)
    """
    d   = _daily_ohlc(bars)
    atr = _wilder_atr(d, atr_n)
    adx = _wilder_adx(d, adx_n)
    er  = _kaufman_er(d, er_n)
    _pctile = lambda s: s.rolling(pct_window, min_periods=20).apply(
        lambda x: (x <= x[-1]).mean(), raw=True)
    day_range = d["High"] - d["Low"]
    range_atr = (day_range / atr.replace(0, np.nan))
    return pd.DataFrame({"ATR": atr, "ATR_pct": _pctile(atr),
                         "ADX": adx, "ADX_pct": _pctile(adx),
                         "ER": er, "ER_pct": _pctile(er),
                         "RangeATR": range_atr})


def _kaufman_er(daily: pd.DataFrame, n: int = 10) -> pd.Series:
    """Kaufman Efficiency Ratio: |net move| / sum(|per-bar moves|) over n days.
    1.0 = perfectly efficient trend, 0.0 = pure chop."""
    c = daily["Close"]
    direction = (c - c.shift(n)).abs()
    volatility = c.diff().abs().rolling(n).sum().replace(0, np.nan)
    return direction / volatility


def bar_kaufman_er(bars: pd.DataFrame, spans=(6, 12, 24)) -> pd.DataFrame:
    """Developing intraday Kaufman ER on the 5M Close (causal — uses only bars
    up to T). One column per span: ER_intra_{n} = |net move over n bars| /
    sum(|per-bar moves| over n bars). 0 = chop, 1 = clean trend.

    Computed on the continuous series (does NOT reset per session), matching how
    `bar_ema` is handled — `merge_asof(direction="backward")` keeps it look-ahead
    safe at the signal bar. Default spans are 30m / 60m / 120m on a 5M chart;
    the trio exists so a slice's edge can be checked for *insensitivity* to the
    lookback (robustness) rather than tuned to a single 'best' value."""
    df = bars.sort_values("DateTime").reset_index(drop=True)
    c = df["Close"]
    step = c.diff().abs()
    out = {"DateTime": df["DateTime"]}
    for n in spans:
        direction = (c - c.shift(n)).abs()
        volatility = step.rolling(n).sum().replace(0, np.nan)
        out[f"ER_intra_{n}"] = (direction / volatility).values
    return pd.DataFrame(out)


def session_levels(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-bar session context levels (causal, look-ahead-safe).

    Returns a frame aligned to `bars` with:
      OOD        — Open of Day (first bar's Open for this session)
      HOY        — High of Yesterday (prior completed session High)
      LOY        — Low of Yesterday (prior completed session Low)
      OR60_High  — 60-min Opening Range High (max of first 12 bars)
      OR60_Low   — 60-min Opening Range Low (min of first 12 bars)

    OR is developing for bars 1–12 (causal: only uses bars seen so far)
    and fixed after bar 12.
    """
    df  = bars.sort_values("DateTime").reset_index(drop=True)
    day = df["DateTime"].dt.normalize()

    # Open of Day
    ood = df.groupby(day)["Open"].transform("first")

    # HOY / LOY — prior session's High / Low
    daily = _daily_ohlc(bars)
    hoy_map = daily["High"].shift(1)
    loy_map = daily["Low"].shift(1)
    hoy = day.map(hoy_map)
    loy = day.map(loy_map)

    # 60-min Opening Range (first 12 five-minute bars = 60 min)
    bar_num = df.groupby(day).cumcount()  # 0-indexed
    or_high = df.groupby(day)["High"].cummax()
    or_low  = df.groupby(day)["Low"].cummin()
    # After bar 11 (60 min), freeze at the bar-11 level
    or_high_frozen = df.groupby(day)["High"].transform(
        lambda x: x.iloc[:12].max() if len(x) >= 12 else x.cummax().iloc[-1])
    or_low_frozen = df.groupby(day)["Low"].transform(
        lambda x: x.iloc[:12].min() if len(x) >= 12 else x.cummin().iloc[-1])
    # Developing for first 12 bars, frozen after
    or_h = np.where(bar_num < 12, or_high, or_high_frozen)
    or_l = np.where(bar_num < 12, or_low, or_low_frozen)

    return pd.DataFrame({
        "DateTime":  df["DateTime"],
        "OOD":       ood.values,
        "HOY":       hoy.values,
        "LOY":       loy.values,
        "OR60_High": or_h,
        "OR60_Low":  or_l,
    })


def bar_ema(bars: pd.DataFrame, span: int = 20) -> pd.DataFrame:
    """Developing EMA on the 5M bar Close (causal — uses only bars up to T).

    Returns a frame with DateTime and EMA_{span} columns. The EMA is computed
    across the full continuous series (does NOT reset per session) — this matches
    how a 20 EMA would appear on a continuous intraday chart.
    """
    df = bars.sort_values("DateTime").reset_index(drop=True)
    ema = df["Close"].ewm(span=span, adjust=False).mean()
    return pd.DataFrame({
        "DateTime": df["DateTime"],
        f"EMA_{span}": ema,
    })


# ── Market Structure Shift (MSS) engine ──────────────────────────────────────

def _tod_avg_volume(bars: pd.DataFrame, lookback_days: int = 20) -> pd.Series:
    """Rolling average volume for each 5-minute time-of-day slot.

    Groups by HH:MM across a trailing `lookback_days` window so that volume
    at 08:35 is compared to other 08:35 bars, not midday bars. Returns a
    Series aligned to `bars` with the TOD-normalized average volume.
    """
    df = bars.sort_values("DateTime").reset_index(drop=True)
    tod = df["DateTime"].dt.time
    vol = df["Volume"].astype(float)

    result = np.full(len(df), np.nan)
    slots = df["DateTime"].dt.strftime("%H:%M")
    for slot, idxs in df.groupby(slots).groups.items():
        idxs_sorted = sorted(idxs)
        slot_vols = vol.iloc[idxs_sorted].values
        # rolling mean over `lookback_days` occurrences of this time slot
        avg = pd.Series(slot_vols).rolling(lookback_days, min_periods=5).mean().values
        for j, idx in enumerate(idxs_sorted):
            result[idx] = avg[j]
    return pd.Series(result, index=df.index)


def calculate_market_structure(bars: pd.DataFrame,
                               atr_multiplier: float = 2.0,
                               vol_multiplier: float = 1.5,
                               lookback_days: int = 20) -> pd.DataFrame:
    """ATR-adaptive zigzag → HH/HL/LH/LL state machine → MSS detection.

    Parameters are testable in Bar Analysis but NOT swept by WFA.

    Args:
        bars:           5M OHLCV DataFrame with DateTime column.
        atr_multiplier: Reversal threshold as multiple of 14-period 5M ATR.
                        Higher = fewer pivots, smoother structure.
        vol_multiplier: Volume spike threshold as multiple of TOD-avg volume.
        lookback_days:  Days for TOD volume averaging.

    Returns DataFrame aligned to bars with:
        structural_trend  — 1 (bullish) / -1 (bearish)
        active_floor      — price of the current HL (bullish) or LH (bearish)
        is_deep_pullback  — wick pierced floor but close held
        mss_event         — confirmed structural break on this bar
        last_swing_type   — most recent pivot type (HH/HL/LH/LL)
    """
    df = bars.sort_values("DateTime").reset_index(drop=True)
    n  = len(df)

    # 14-period ATR on 5M bars (Wilder smoothing)
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    alpha = 1.0 / 14
    atr = np.empty(n)
    atr[0] = tr[0]
    for i in range(1, n):
        atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha

    # TOD-normalized volume
    tod_vol = _tod_avg_volume(df, lookback_days).values
    vol = df["Volume"].astype(float).values

    # output arrays
    trend       = np.ones(n, dtype=np.int8)      # 1=bullish
    floor_price = np.full(n, np.nan)
    deep_pb     = np.zeros(n, dtype=bool)
    mss         = np.zeros(n, dtype=bool)
    swing_type  = np.empty(n, dtype=object)
    swing_type[:] = ""

    # zigzag state machine
    # direction: 1 = looking for next high (last anchor was a low)
    #           -1 = looking for next low  (last anchor was a high)
    zz_dir       = 1
    anchor_price = c[0]
    anchor_idx   = 0

    # structural pivots (the last 4 confirmed swing points)
    pivots = []   # list of (idx, price, 'H'|'L')

    # macro trend
    macro_trend   = 1
    active_hl     = np.nan   # last confirmed HL price (bullish floor)
    active_lh     = np.nan   # last confirmed LH price (bearish ceiling)

    def _classify_pivot(price, typ):
        """Classify a new pivot as HH/HL/LH/LL relative to the last same-type pivot."""
        same = [p for p in pivots if p[2] == typ]
        if not same:
            return "HH" if typ == "H" else "HL"
        prev_price = same[-1][1]
        if typ == "H":
            return "HH" if price > prev_price else "LH"
        else:
            return "HL" if price > prev_price else "LL"

    for i in range(n):
        threshold = atr_multiplier * atr[i]

        if zz_dir == 1:
            # tracking upward — looking for a new high
            if h[i] > anchor_price:
                anchor_price = h[i]
                anchor_idx   = i
            elif anchor_price - l[i] >= threshold:
                # reversal confirmed → anchor was a swing high
                cls = _classify_pivot(anchor_price, "H")
                pivots.append((anchor_idx, anchor_price, "H"))
                for j in range(anchor_idx, i + 1):
                    swing_type[j] = cls

                if cls == "LH":
                    active_lh = anchor_price

                # new direction: looking for low, anchor at current low
                zz_dir       = -1
                anchor_price  = l[i]
                anchor_idx    = i

        else:
            # tracking downward — looking for a new low
            if l[i] < anchor_price:
                anchor_price = l[i]
                anchor_idx   = i
            elif h[i] - anchor_price >= threshold:
                # reversal confirmed → anchor was a swing low (mirror of the
                # up-tracking gate: price's HIGH rose `threshold` above the trough)
                cls = _classify_pivot(anchor_price, "L")
                pivots.append((anchor_idx, anchor_price, "L"))
                for j in range(anchor_idx, i + 1):
                    swing_type[j] = cls

                if cls == "HL":
                    active_hl = anchor_price
                elif cls == "LL":
                    active_hl = anchor_price  # track even in bearish

                # new direction: looking for high
                zz_dir       = 1
                anchor_price  = h[i]
                anchor_idx    = i

        # ── MSS / deep pullback detection ────────────────────────────────
        if macro_trend == 1 and not np.isnan(active_hl):
            if l[i] < active_hl:
                vol_spike = (not np.isnan(tod_vol[i]) and tod_vol[i] > 0
                             and vol[i] >= vol_multiplier * tod_vol[i])
                if c[i] < active_hl and vol_spike:
                    mss[i]      = True
                    macro_trend = -1
                    active_lh   = h[i]
                else:
                    deep_pb[i] = True

        elif macro_trend == -1 and not np.isnan(active_lh):
            if h[i] > active_lh:
                vol_spike = (not np.isnan(tod_vol[i]) and tod_vol[i] > 0
                             and vol[i] >= vol_multiplier * tod_vol[i])
                if c[i] > active_lh and vol_spike:
                    mss[i]      = True
                    macro_trend = 1
                    active_hl   = l[i]
                else:
                    deep_pb[i] = True

        trend[i]       = macro_trend
        floor_price[i] = active_hl if macro_trend == 1 else active_lh

    return pd.DataFrame({
        "DateTime":         df["DateTime"],
        "structural_trend": trend,
        "active_floor":     floor_price,
        "is_deep_pullback": deep_pb,
        "mss_event":        mss,
        "last_swing_type":  swing_type,
    })


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

    EMA / session levels (causal, at the signal bar):
      EMA_20       — developing 20-bar EMA on 5M Close
      OOD          — Open of Day
      HOY / LOY    — prior session High / Low
      OR60_High/Low — 60-min Opening Range (developing first 12 bars, frozen after)

    Daily regime (prior-day, look-ahead-safe):
      prior_ATR/ATR_pct, prior_ADX/ADX_pct, prior_ER/ER_pct, prior_RangeATR

    Value areas — for each period in `periods`, the PRIOR period's levels:
      {p}_POC/VAH/VAL, {p}_loc, {p}_dist
    """
    sig = signals.copy()

    # ── VWAP deviation at the signal bar (as-of merge on DateTime) ────────────
    vb = session_vwap_bands(bars)[["DateTime", "VWAP", "VWAP_sigma", "VWAP_dev"]]
    sig = sig.sort_values("DateTime")
    sig = pd.merge_asof(
        sig, vb.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # ── 20-bar EMA (as-of merge) ─────────────────────────────────────────────
    ema_df = bar_ema(bars, span=20)
    sig = pd.merge_asof(
        sig, ema_df.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # ── Intraday Kaufman ER (30m/60m/120m, causal) ───────────────────────────
    eri = bar_kaufman_er(bars, spans=(6, 12, 24))
    sig = pd.merge_asof(
        sig, eri.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # ── Session levels (as-of merge) ─────────────────────────────────────────
    sl = session_levels(bars)
    sig = pd.merge_asof(
        sig, sl.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # ── Market structure (as-of merge) ──────────────────────────────────────
    ms = calculate_market_structure(bars)
    ms_cols = ["DateTime", "structural_trend", "active_floor",
               "is_deep_pullback", "mss_event"]
    sig = pd.merge_asof(
        sig, ms[ms_cols].sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # signal price — prefer an explicit price column, fall back to causal VWAP
    px_col = next((c for c in ("Price", "SignalPrice", "Close", "EntryPrice")
                   if c in sig.columns), None)
    px = sig[px_col].astype(float) if px_col else sig["VWAP"]

    # ── Prior-day regime (ATR / ADX / ER / RangeATR) — look-ahead-safe ───────
    reg   = daily_regime(bars).shift(1)          # prior trading day's completed values
    s_day = pd.to_datetime(sig["DateTime"]).dt.normalize()
    sig["prior_ATR"]      = s_day.map(reg["ATR"]).values
    sig["prior_ATR_pct"]  = s_day.map(reg["ATR_pct"]).values
    sig["prior_ADX"]      = s_day.map(reg["ADX"]).values
    sig["prior_ADX_pct"]  = s_day.map(reg["ADX_pct"]).values
    sig["prior_ER"]       = s_day.map(reg["ER"]).values
    sig["prior_ER_pct"]   = s_day.map(reg["ER_pct"]).values
    sig["prior_RangeATR"] = s_day.map(reg["RangeATR"]).values

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
