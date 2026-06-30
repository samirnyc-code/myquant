"""
ama_setups.py — Python port of Ali Moin-Afshari's AMABreakoutsPB6 NinjaScript indicator.

Faithfully replicates Ver 6 core signal logic AND the "AI Flip" (TD additions).
Bar-by-bar loop required: FT carry-forward and AI Flip state break full vectorisation.

⚠️  LOOK-AHEAD PREVENTION
    DateTime column in bars is the bar's OPEN time (NT8 export convention).
    A 5M bar opening at 08:30 is KNOWN only at 08:35 (its close).
    `to_signal_rows()` adds 5 minutes to every signal's DateTime so the
    simulation engine fills at the NEXT bar's open — never inside the signal bar.
    Do NOT use bar i's data (H/L/C/O) when computing signals for bars < i.

Signal codes
    ±1  : Bull/Bear Breakout (BO)
    ±2  : Bull/Bear Climax (CX)
    ±3  : Bull/Bear Outside Bar (OB)
     4  : Doji Outside Bar
    ±5  : Big Bull/Bear BO
     0  : No signal / inside bar / filtered

AI Flip outputs
    Flip_Long  : price level of bullish regime-change dot (0 = no flip)
    Flip_Short : price level of bearish regime-change dot (0 = no flip)
    FlipType_L / FlipType_S : 'ema' | '3cc' | 'bigbo' | 'b12' | None
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

TICK_SIZE = 0.25  # ES

FLIP_EMA   = "ema"
FLIP_3CC   = "3cc"
FLIP_BIGBO = "bigbo"
FLIP_B12   = "b12"


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class AMAConfig:
    # 01 — BO / OB / CX
    show_blbo: int = 1           # show bull breakouts
    show_brbo: int = 1           # show bear breakouts
    show_bigbo: int = 0          # show big-bar BO override
    big_bo_range_factor: float = 1.05   # min Z-score (or range multiple) for BigBO
    show_outside_bars: int = 1   # show OB signals
    strict_ob: int = 1           # require H > H[1] AND L < L[1] for OB
    show_cx: int = 0             # show CX signals
    cx_factor: float = 1.8       # CX ratio threshold
    # 02 — Z-score (drives BigBO when enabled)
    big_bo_by_zscore: int = 1    # use range Z-score for BigBO detection
    compare_range2range: int = 1 # compare bar range vs avg range (Z-score mode)
    compare_body2body: int = 0   # compare body size vs avg body (Z-score mode)
    z_length: int = 20           # lookback for Z-score + ZScore plot
    # 03 — Range Filter
    range_filter: float = 0.0    # minimum range multiplier (0 = off)
    range_lookback: int = 8      # SMA period for avg range used in filter
    do_not_range_limit_ob: int = 0  # exempt OB signals from range filter
    # 04 — IBS Filters (-1 = off)
    bl_signal_ibs: int = 69      # bull BO: minimum IBS (non-FT)
    br_signal_ibs: int = 31      # bear BO: maximum IBS (non-FT)
    bl_ft_bar_ibs: int = 40      # bull FT: minimum IBS
    br_ft_bar_ibs: int = 60      # bear FT: maximum IBS
    do_not_ibs_filter_ob: int = 1  # exempt OB signals from IBS filter
    # 05 — Signal / Output Control
    paint_ft_bar: int = 1        # paint follow-through bars
    ft_bar_must_bo: int = 1      # FT bar must break out
    ft_bar_must_close_beyond: int = 1  # FT bar must close beyond prior extreme
    ft_bar_not_range_limited: int = 1  # FT bar exempt from range filter
    ft_after_ob: int = 0         # allow FT after OB signal
    ft_color_same_as_bo: int = 0 # use BO colour for FT bar (cosmetic, ignored here)
    ignore_open_gap: int = 1     # ignore gap opens for FT (no-op in detector)
    # AI Flip
    show_ai_flip: bool = True    # compute Flip_Long / Flip_Short


# ── Indicator helpers ──────────────────────────────────────────────────────────

def _sma(a: np.ndarray, p: int) -> np.ndarray:
    return pd.Series(a).rolling(p, min_periods=p).mean().values

def _std(a: np.ndarray, p: int) -> np.ndarray:
    return pd.Series(a).rolling(p, min_periods=p).std(ddof=1).values

def _ema(a: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(a).ewm(span=span, adjust=False).mean().values

def _wilder_atr(H: np.ndarray, L: np.ndarray, C: np.ndarray, period: int) -> np.ndarray:
    n = len(H)
    prev_c = np.roll(C, 1); prev_c[0] = C[0]
    tr = np.maximum(H - L, np.maximum(np.abs(H - prev_c), np.abs(L - prev_c)))
    tr[0] = H[0] - L[0]
    atr = np.full(n, np.nan)
    if n < period:
        return atr
    atr[period - 1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr

def _rolling_max(a: np.ndarray, p: int) -> np.ndarray:
    return pd.Series(a).rolling(p, min_periods=1).max().values

def _rolling_min(a: np.ndarray, p: int) -> np.ndarray:
    return pd.Series(a).rolling(p, min_periods=1).min().values


def _bars_since_session_open(dt_col: np.ndarray) -> np.ndarray:
    """Return 0-based bar index within each trading day."""
    dates = pd.to_datetime(dt_col).date
    result = np.zeros(len(dates), dtype=int)
    prev = None; count = 0
    for i, d in enumerate(dates):
        if d != prev:
            count = 0; prev = d
        result[i] = count
        count += 1
    return result


# ── CountIf equivalent ─────────────────────────────────────────────────────────

def _cif(bool_arr: np.ndarray, i: int, N: int, k: int = 0) -> int:
    """
    NT CountIf(delegate {return cond[k];}, N) at bar i.
    = sum of bool_arr at positions [i-k-(N-1) .. i-k]  (inclusive both ends).
    k=0 means current bar; k=1 means shifted back 1, etc.
    """
    end   = min(len(bool_arr), i - k + 1)
    start = max(0, i - k - N + 1)
    if end <= start:
        return 0
    return int(np.sum(bool_arr[start:end]))


# ── Main detector ──────────────────────────────────────────────────────────────

def detect(bars: pd.DataFrame, config: AMAConfig | None = None) -> pd.DataFrame:
    """
    Detect AMA Breakouts PB6 signals for every bar in `bars`.

    Parameters
    ----------
    bars : DataFrame with columns Open, High, Low, Close, DateTime.
           DateTime is the bar's OPEN time (NT8 export convention).
           Must be RTH-only 5M bars; one row per closed bar.
    config : AMAConfig — uses NT Ver 6 defaults if omitted.

    Returns
    -------
    DataFrame (same length as bars) with raw detection columns:
        Signal, FTflag, ZScore, OB, IB, IBS, BarDir, BODir,
        AvgRange, Flip_Long, Flip_Short, FlipType_L, FlipType_S, DateTime
    Rows with Signal==0 carry no tradeable signal; keep them for context.
    """
    cfg = config or AMAConfig()
    n = len(bars)

    H = bars["High"].to_numpy(float)
    L = bars["Low"].to_numpy(float)
    C = bars["Close"].to_numpy(float)
    O = bars["Open"].to_numpy(float)
    DT = bars["DateTime"].to_numpy()

    rng  = H - L
    body = np.abs(C - O)
    med  = (H + L) / 2.0

    # ── Pre-compute indicator arrays (no look-ahead: rolling ends at bar i) ──
    ema20      = _ema(C, 20)
    atr50      = _wilder_atr(H, L, C, 50)
    sma_rng8   = _sma(rng, 8)                   # SMA(Range, 8) — avg range for offset/filter
    sma_rng_z  = _sma(rng, cfg.z_length)         # SMA for Z-score numerator
    std_rng_z  = _std(rng, cfg.z_length)         # StdDev for Z-score denominator
    sma_body_z = _sma(body, cfg.z_length)
    std_body_z = _std(body, cfg.z_length)
    sma_rng_lb = _sma(rng, cfg.range_lookback)   # range filter baseline
    # MAX(High,81)[1] / MIN(Low,81)[1] — shifted so [1] matches NT convention
    max_h81    = np.roll(_rolling_max(H, 81), 1); max_h81[0] = np.nan
    min_l81    = np.roll(_rolling_min(L, 81), 1); min_l81[0] = np.nan

    # Pre-compute boolean arrays for CountIf (no state dependency)
    ema_above_c  = ema20 > C          # EMA above close (bear context)
    ema_below_c  = ema20 < C          # EMA below close (bull context)
    bull_bar     = C > O
    bear_bar     = C < O
    med_at_hi    = med <= C           # close in upper half (bull strength)
    med_at_lo    = med >= C           # close in lower half (bear strength)
    small_body   = (rng / 10.0) > body  # near-doji: range >> body
    doji_bull    = (O == C) & (med > C)
    doji_bear    = (O == C) & (med < C)
    # prior_H < close[i] (close breaks above prior high)
    h1_lt_c = np.zeros(n, dtype=bool)
    h1_lt_c[1:] = H[:-1] < C[1:]
    # prior_L > close[i] (close breaks below prior low)
    l1_gt_c = np.zeros(n, dtype=bool)
    l1_gt_c[1:] = L[:-1] > C[1:]
    # H - rng/2.5 < close (close in top 40% of bar: strong close)
    h_qtr_lt_c = (H - rng / 2.5) < C
    # close[i] > close[i-1]
    close_rising = np.zeros(n, dtype=bool)
    close_rising[1:] = C[1:] > C[:-1]

    bars_since = _bars_since_session_open(DT)

    # Pre-compute Z-score array (used in loop + AI Flip)
    with np.errstate(invalid="ignore", divide="ignore"):
        z_rng_arr  = np.where(std_rng_z  != 0, (rng  - sma_rng_z)  / std_rng_z,  0.0)
        z_body_arr = np.where(std_body_z != 0, (body - sma_body_z) / std_body_z, 0.0)
    z_rng_arr  = np.nan_to_num(z_rng_arr,  nan=0.0)
    z_body_arr = np.nan_to_num(z_body_arr, nan=0.0)

    # ── Output arrays ─────────────────────────────────────────────────────────
    Signal    = np.zeros(n, dtype=int)
    FTflag    = np.zeros(n, dtype=int)
    ZScore    = z_rng_arr.copy()
    OB_a      = np.zeros(n, dtype=int)
    IB_a      = np.zeros(n, dtype=int)
    IBS_a     = np.zeros(n, dtype=float)
    BarDir_a  = np.zeros(n, dtype=int)
    BODir_a   = np.zeros(n, dtype=int)
    AvgRange  = np.nan_to_num(sma_rng_lb, nan=0.0)

    Flip_L    = np.zeros(n, dtype=float)
    Flip_S    = np.zeros(n, dtype=float)
    FType_L   = np.empty(n, dtype=object)   # None / 'ema' / '3cc' / 'bigbo' / 'b12'
    FType_S   = np.empty(n, dtype=object)

    # ── Bar-by-bar loop ───────────────────────────────────────────────────────
    for i in range(1, n):
        h  = H[i];  l  = L[i];  c  = C[i];  o  = O[i]
        h1 = H[i-1];l1 = L[i-1];c1 = C[i-1];o1 = O[i-1]
        bar_rng = rng[i]

        # ── OB / IB ──────────────────────────────────────────────────────────
        ob = int(h > h1 and l < l1)
        if not ob and cfg.strict_ob <= 0:
            if (h > h1 and l == l1) or (h == h1 and l < l1):
                ob = 1
        OB_a[i] = ob

        ib = int((h < h1 and l > l1) or (h < h1 and l == l1) or (h == h1 and l > l1))
        IB_a[i] = ib

        # ── IBS ──────────────────────────────────────────────────────────────
        ibs = (c - l) / bar_rng * 100.0 if bar_rng != 0.0 else 50.0
        IBS_a[i] = ibs

        # ── Bar Direction ─────────────────────────────────────────────────────
        if   ibs > 50:                     bd = 1
        elif ibs < 50:                     bd = -1
        elif c > o:                        bd = 1
        elif c < o:                        bd = -1
        else:                              bd = BarDir_a[i - 1]
        BarDir_a[i] = bd

        # ── BODir ─────────────────────────────────────────────────────────────
        if ob:
            bo_dir = 0
        elif h > h1:
            bo_dir = 1
        elif l < l1:
            bo_dir = -1
        else:
            bo_dir = 0
        BODir_a[i] = bo_dir

        # ── Initial BO signal ─────────────────────────────────────────────────
        sig = 0
        if cfg.show_blbo > 0 and not ob and h > h1 and l >= l1:
            sig = 1
        elif cfg.show_brbo > 0 and not ob and h <= h1 and l < l1:
            sig = -1

        # ── Climax ───────────────────────────────────────────────────────────
        if cfg.show_cx > 0 and not ob:
            if sig == 1:
                bo_up = h - h1; bo_dn = l - l1   # bo_dn is 0 or negative here
                if bo_up > abs(bo_dn) * cfg.cx_factor and c > h1:
                    sig = 2
            elif sig == -1:
                bo_dn = l1 - l; bo_up = h - h1
                if bo_dn > bo_up * cfg.cx_factor and c < l1:
                    sig = -2
            # CX filters
            if sig == 2 and (IB_a[i-1] or ob or BarDir_a[i] != BarDir_a[i-1] or c <= h1):
                sig = bo_dir
            if sig == -2 and (IB_a[i-1] or ob or BarDir_a[i] != BarDir_a[i-1] or c >= l1):
                sig = bo_dir

        # ── OB signal ────────────────────────────────────────────────────────
        if cfg.show_outside_bars > 0 and ob:
            hh_dist = h - h1; ll_dist = l1 - l
            if hh_dist > ll_dist:
                sig = 3
            elif ll_dist > hh_dist:
                sig = -3
            elif c == o and ibs == 50:
                sig = 4
            elif bd == 1:
                sig = 3
            else:
                sig = -3

        # ── Follow-Through ────────────────────────────────────────────────────
        ft = 0
        sig_prev = Signal[i - 1]
        bd_prev  = BarDir_a[i - 1]

        if cfg.paint_ft_bar > 0 and sig_prev != 0:
            # Mode A: must BO (break prior extreme)
            if cfg.ft_bar_must_bo > 0 and cfg.ft_bar_must_close_beyond <= 0:
                if sig_prev > 0 and bo_dir == 1:
                    sig = 1; ft = 1
                elif sig_prev < 0 and bo_dir == -1:
                    sig = -1; ft = -1
                elif bd == bd_prev and not (ob and cfg.show_outside_bars):
                    sig = 0

            # Mode B: must close beyond prior extreme
            if cfg.ft_bar_must_close_beyond > 0:
                if sig_prev > 0 and c > h1:
                    sig = 1; ft = 1
                elif sig_prev < 0 and c < l1:
                    sig = -1; ft = -1
                elif bd == bd_prev and not (ob and cfg.show_outside_bars):
                    sig = 0
                elif sig_prev > 0 and bo_dir == 1 and c <= h1:
                    sig = 0; ft = 0
                elif sig_prev < 0 and bo_dir == -1 and c >= l1:
                    sig = 0; ft = 0

        # ── Range Filter ──────────────────────────────────────────────────────
        avg_rng = sma_rng_lb[i] if not np.isnan(sma_rng_lb[i]) else 0.0
        if cfg.range_filter > 0 and sig != 0:
            exempt = ob and cfg.do_not_range_limit_ob > 0
            ft_exempt = ft != 0 and cfg.ft_bar_not_range_limited > 0
            if not exempt and not ft_exempt:
                if bar_rng < avg_rng * cfg.range_filter:
                    sig = 0; ft = 0

        # ── Big BO ────────────────────────────────────────────────────────────
        # NT8: entire block is inside if (_ShowBigBO > 0). When off, the bar
        # stays as its original ±1 BO signal (it is NOT consumed/suppressed).
        if cfg.show_bigbo > 0 and sig != 0 and not ob:
            z_big = 0.0
            if cfg.big_bo_by_zscore > 0:
                if cfg.compare_range2range > 0 and cfg.compare_body2body <= 0:
                    z_big = z_rng_arr[i]
                elif cfg.compare_body2body > 0 and cfg.compare_range2range <= 0:
                    z_big = z_body_arr[i]
                if z_big >= cfg.big_bo_range_factor:
                    if bd == 1  and cfg.show_blbo > 0: sig = 5
                    elif bd == -1 and cfg.show_brbo > 0: sig = -5
            else:
                if avg_rng > 0 and bar_rng >= avg_rng * cfg.big_bo_range_factor:
                    if bd == 1  and cfg.show_blbo > 0: sig = 5
                    elif bd == -1 and cfg.show_brbo > 0: sig = -5

        # ── IBS Filter ────────────────────────────────────────────────────────
        apply_ibs = cfg.do_not_ibs_filter_ob <= 0 or abs(sig) not in (3, 4)
        if apply_ibs:
            if cfg.bl_signal_ibs > -1 and sig > 0 and ft == 0 and ibs < cfg.bl_signal_ibs:
                sig = 0
            if cfg.br_signal_ibs > -1 and sig < 0 and ft == 0 and ibs > cfg.br_signal_ibs:
                sig = 0
            if cfg.bl_ft_bar_ibs > -1 and sig > 0 and ft == 1 and ibs < cfg.bl_ft_bar_ibs:
                sig = 0; ft = 0
            if cfg.br_ft_bar_ibs > -1 and sig < 0 and ft == -1 and ibs > cfg.br_ft_bar_ibs:
                sig = 0; ft = 0

        Signal[i]  = sig
        FTflag[i]  = ft

        # ── AI Flip ───────────────────────────────────────────────────────────
        if not cfg.show_ai_flip or i < 4:
            continue

        # Locals that match NT's `double EMAN = EMA(20)[N]` captured vars.
        # These are CONSTANTS within each bar's flip evaluation (not re-evaluated
        # per CountIf iteration). Use ema1/ema2/ema3 names to match the NT source.
        ema0 = ema20[i]
        ema1 = ema20[i - 1]
        ema2 = ema20[i - 2]
        ema3 = ema20[i - 3]
        ibs1 = IBS_a[i - 1]
        my_ar0 = sma_rng8[i]   if not np.isnan(sma_rng8[i])   else 0.0
        my_ar1 = sma_rng8[i-1] if not np.isnan(sma_rng8[i-1]) else 0.0
        body0  = body[i]
        z0     = z_rng_arr[i]
        z1     = z_rng_arr[i - 1]
        rng0   = rng[i]
        rng1   = rng[i - 1]
        # ATR-based dot offset (same formula as NT)
        atr_prev = atr50[i - 1] if not np.isnan(atr50[i - 1]) else 0.0
        offset   = max(5.0 * TICK_SIZE, atr_prev / 4.0)

        fl  = Flip_L   # aliases for brevity in dense conditions
        fs  = Flip_S
        ftl = FType_L
        fts = FType_S

        # ── SECTION 1: BO+FT through EMA (type='ema') ─────────────────────────
        # Long BO+FT flip
        #
        # NT conditions translated literally.  `EMA3` inside CountIf delegates
        # is the CAPTURED constant ema3 = ema20[i-3], not a series.
        switch_from_short_bo = (
            _cif(ema_above_c, i, 10, k=2) > 3 or
            # CountIf(Flip_Short[0]>0 && EMA3>Close[0], 4) — EMA3 is captured const
            any(i - j >= 0 and fs[i - j] > 0 and ema3 > C[i - j] for j in range(4)) or
            bars_since[i] < 8
        )
        no_prior_long_bo = (
            # CountIf(Flip_Long[1]>0 && PlotBrushes[2][1]!=Blue, 3)<1
            # Blue = bigbo; "not Blue" = ema or 3cc
            sum(1 for j in range(3)
                if i - 1 - j >= 0
                and fl[i - 1 - j] > 0
                and ftl[i - 1 - j] != FLIP_BIGBO) < 1
        )
        flip_long_bo = (
            (o1 <= ema1 or bars_since[i] < 5) and
            ema1 <= c1 and
            (sig_prev == 1 or sig_prev == 3 or (sig_prev == -3 and h1 < c)) and
            not ((sig_prev in (3, -3)) and o1 > c1) and
            (ft == 1 or med[i] <= c) and
            bull_bar[i] and close_rising[i] and sig == 1 and l1 <= l and
            switch_from_short_bo and
            not (ema1 + my_ar1 * 0.5 > h) and
            no_prior_long_bo
        )
        if flip_long_bo:
            fl[i] = l - offset
            ftl[i] = FLIP_EMA

        # Short BO+FT flip
        switch_from_long_bo = (
            _cif(ema_below_c, i, 10, k=2) > 3 or
            any(i - j >= 0 and fl[i - j] > 0 and ema3 < C[i - j] for j in range(4)) or
            bars_since[i] < 8
        )
        no_prior_short_bo = (
            sum(1 for j in range(3)
                if i - 1 - j >= 0
                and fs[i - 1 - j] > 0
                and fts[i - 1 - j] != FLIP_BIGBO) < 1
        )
        flip_short_bo = (
            fl[i] == 0 and          # don't overwrite a long flip set above
            (o1 >= ema1 or bars_since[i] < 5) and
            ema1 >= c1 and
            (sig_prev == -1 or sig_prev == -3 or (sig_prev == 3 and l1 > c)) and
            not ((sig_prev in (3, -3)) and o1 < c1) and
            (ft == -1 or med[i] >= c) and
            bear_bar[i] and C[i] < C[i - 1] and sig == -1 and h1 >= h and
            switch_from_long_bo and
            not (ema1 - my_ar1 * 0.5 < l) and
            no_prior_short_bo
        )
        if flip_short_bo:
            fs[i] = h + offset
            fts[i] = FLIP_EMA

        # ── SECTION 2: 3 Consecutive Closes beyond EMA (type='3cc') ──────────
        if i >= 3:
            # Long 3CC
            # "switch from short": recent bars were above EMA, or recent short flip
            sw_short_3cc = (
                _cif(ema_above_c, i, 10, k=3) > 2 or
                any(i - j >= 0 and fs[i - j] > 0
                    and ema3 > C[i - j] for j in range(4))
            )
            # "no prior long" — three independent recency guards
            no_pl_1 = sum(1 for j in range(6)
                          if i - j - 3 >= 0
                          and fs[i - j - 3] > 0
                          and ema3 > C[i - j - 3]) < 1
            no_pl_2 = sum(1 for j in range(10)
                          if i - 1 - j >= 0
                          and fl[i - 1 - j] > 0
                          and ema3 < C[i - 1 - j]
                          and ftl[i - 1 - j] == FLIP_3CC) < 1
            no_pl_3 = sum(1 for j in range(5)
                          if i - j >= 0
                          and fl[i - j] > 0) < 1
            # "weak switch" exclusions
            low_hlows = sum(1 for j in range(2)    # CountIf(Low[1]<=Low[0],2)
                            if i - j >= 1 and L[i - j - 1] <= L[i - j])
            hi_hhighs = sum(1 for j in range(3)    # CountIf(High[1]<High[0],3)
                            if i - j >= 1 and H[i - j - 1] < H[i - j])
            not_weak_3cc_l = not (
                (_cif(med_at_lo, i, 3) > 1 and low_hlows < 2) or
                (ema2 + my_ar0 > h and _cif(IB_a.astype(bool), i, 3) > 0) or
                (ema2 + my_ar0 > h and hi_hhighs < 3) or
                (i >= 2 and ema2 > med[i - 2] and BarDir_a[i - 1] == -1
                 and (BarDir_a[i] == -1 or ib))
            )
            # 3-bar rising close count
            rising3 = sum(1 for j in range(3) if i - j >= 1 and C[i - j - 1] < C[i - j])
            # open <= close for 3 bars
            bull3   = all(O[i - j] <= C[i - j] for j in range(3))
            # strong close conditions
            strong3 = (
                (_cif(med_at_hi, i, 3) > 2 and ibs > 60) or
                _cif(bull_bar, i, 4) > 3 or
                _cif(h1_lt_c, i, 3) > 1
            )

            three_cc_long = (
                fl[i] == 0 and
                (
                    ema2 < C[i - 2] or
                    (H[i - 3] < C[i - 2]
                     and _cif(h_qtr_lt_c, i, 3) > 2
                     and ema1 + TICK_SIZE < c1) or
                    (1.8 < z0 and rng0 / 2 <= body0)
                ) and
                ema1 < c1 and ema0 < c and
                bull3 and rising3 > 2 and
                _cif(doji_bull, i, 3) < 2 and
                _cif(small_body, i, 3) < 2 and
                strong3 and
                sw_short_3cc and
                no_pl_1 and no_pl_2 and no_pl_3 and
                not_weak_3cc_l
            )
            if three_cc_long:
                fl[i] = l - offset
                ftl[i] = FLIP_3CC

            # Short 3CC
            sw_long_3cc = (
                _cif(ema_below_c, i, 10, k=3) > 2 or
                any(i - j >= 0 and fl[i - j] > 0
                    and ema3 < C[i - j] for j in range(4))
            )
            no_ps_1 = sum(1 for j in range(6)
                          if i - j - 3 >= 0
                          and fl[i - j - 3] > 0
                          and ema3 < C[i - j - 3]) < 1
            no_ps_2 = sum(1 for j in range(10)
                          if i - 1 - j >= 0
                          and fs[i - 1 - j] > 0
                          and ema3 > C[i - 1 - j]
                          and fts[i - 1 - j] == FLIP_3CC) < 1
            no_ps_3 = sum(1 for j in range(5)
                          if i - j >= 0
                          and fs[i - j] > 0) < 1
            hi_llows = sum(1 for j in range(2)     # CountIf(High[1]>=High[0],2)
                           if i - j >= 1 and H[i - j - 1] >= H[i - j])
            lo_llows = sum(1 for j in range(3)     # CountIf(Low[1]>Low[0],3)
                           if i - j >= 1 and L[i - j - 1] > L[i - j])
            not_weak_3cc_s = not (
                (_cif(med_at_hi, i, 3) > 1 and hi_llows < 2) or
                (ema2 - my_ar0 < l and _cif(IB_a.astype(bool), i, 3) > 0) or
                (ema2 - my_ar0 < l and lo_llows < 3) or
                (i >= 2 and ema2 < med[i - 2] and BarDir_a[i - 1] == 1
                 and (BarDir_a[i] == 1 or ib))
            )
            falling3 = sum(1 for j in range(3) if i - j >= 1 and C[i - j - 1] > C[i - j])
            bear3    = all(O[i - j] >= C[i - j] for j in range(3))
            strong3s = (
                (_cif(med_at_lo, i, 3) > 2 and ibs < 40) or
                _cif(bear_bar, i, 4) > 3 or
                _cif(l1_gt_c, i, 3) > 1
            )
            # low side analogue of h_qtr_lt_c: L + rng/2.5 > C (close in bottom)
            l_qtr_gt_c = (L + rng / 2.5) > C

            three_cc_short = (
                fs[i] == 0 and
                (
                    ema2 > C[i - 2] or
                    (L[i - 3] > C[i - 2]
                     and sum(1 for j in range(3)
                             if i - j >= 0 and L[i - j] + rng[i - j] / 2.5 > C[i - j]) > 2
                     and ema1 - TICK_SIZE > c1) or
                    (1.8 < z0 and rng0 / 2 <= body0)
                ) and
                ema1 > c1 and ema0 > c and
                bear3 and falling3 > 2 and
                _cif(doji_bear, i, 3) < 2 and
                _cif(small_body, i, 3) < 2 and
                strong3s and
                sw_long_3cc and
                no_ps_1 and no_ps_2 and no_ps_3 and
                not_weak_3cc_s
            )
            if three_cc_short:
                fs[i] = h + offset
                fts[i] = FLIP_3CC

        # ── SECTION 3: Big BO — one large bar (RangeZ > 2.1) ─────────────────
        if z0 > 2.1:
            ema1_cap = ema1   # captured constant for CountIf delegates below

            # Long bigbo
            prev_cross = (
                _cif(ema_above_c, i, 10, k=2) > 2 or
                (sig_prev in (-1, -3) and ema1 > c1) or
                sum(1 for j in range(8)
                    if i - 1 - j >= 0
                    and fl[i - 1 - j] > 0
                    and ema1_cap < C[i - 1 - j]) < 1
            )
            long_bigbo = (
                fl[i] == 0 and
                (sig in (1, 3)) and bull_bar[i] and
                rng0 / 4 <= body0 and
                (h1 <= med[i] or sig == 3 or
                 (sig_prev == -3 and o1 < c) or
                 (z1 > 1.5 and O[i-1] > C[i-1] and h1 < c and not ob)) and
                not (OB_a[i - 1] and ob) and
                o < ema0 < c and
                prev_cross
            )
            if long_bigbo:
                fl[i] = l - offset
                ftl[i] = FLIP_BIGBO

            # Short bigbo
            prev_cross_s = (
                _cif(ema_below_c, i, 10, k=2) > 2 or
                (sig_prev in (1, 3) and ema1 < c1) or
                sum(1 for j in range(8)
                    if i - 1 - j >= 0
                    and fs[i - 1 - j] > 0
                    and ema1_cap > C[i - 1 - j]) < 1
            )
            short_bigbo = (
                fs[i] == 0 and
                (sig in (-1, -3)) and bear_bar[i] and
                rng0 / 4 <= body0 and
                (l1 >= med[i] or sig == -3 or
                 (sig_prev == 3 and o1 > c) or
                 (z1 > 1.5 and O[i-1] < C[i-1] and l1 > c and not ob)) and
                not (OB_a[i - 1] and ob) and
                o > ema0 > c and
                prev_cross_s
            )
            if short_bigbo:
                fs[i] = h + offset
                fts[i] = FLIP_BIGBO

        # ── SECTION 4: Big BO — two smaller bars (Z[1]>1.5 && Z[0]>1.2) ──────
        if z1 > 1.5 and z0 > 1.2 and rng1 / 2.1 < body[i - 1]:
            # Long two-bar bigbo
            two_long = (
                fl[i] == 0 and fl[i - 1] == 0 and
                sig_prev in (1, 3, -3) and sig == 1 and
                O[i-1] < C[i-1] and o < c and
                O[i-1] < ema1 and ema0 < c and
                _cif(ema_above_c, i, 10, k=2) > 4
            )
            if two_long:
                fl[i] = l - offset
                ftl[i] = FLIP_BIGBO

            # Short two-bar bigbo
            two_short = (
                fs[i] == 0 and fs[i - 1] == 0 and
                sig_prev in (-1, -3, 3) and sig == -1 and
                O[i-1] > C[i-1] and o > c and
                O[i-1] > ema1 and ema0 > c and
                _cif(ema_below_c, i, 10, k=2) > 4
            )
            if two_short:
                fs[i] = h + offset
                fts[i] = FLIP_BIGBO

        # ── SECTION 5: Bars 1 & 2 (second bar of session with big Z-scores) ───
        if bars_since[i] == 1 and (z1 > 2 or z0 > 2) and BarDir_a[i - 1] == bd:
            solid_bar1 = (
                rng1 / 4 < body[i - 1] or
                (rng1 / 5 < body[i - 1] and (ibs1 >= 89 or ibs1 <= 11))
            )
            solid_bar0 = rng0 / 4 < body0
            if solid_bar1 and solid_bar0:
                if h1 < c and O[i-1] < C[i-1] and o < c and ema0 - rng0 > h:
                    fl[i] = l - 1.5 * offset
                    ftl[i] = FLIP_B12
                elif l1 > c and O[i-1] > C[i-1] and o > c and ema0 + rng0 < l:
                    fs[i] = h + 1.5 * offset
                    fts[i] = FLIP_B12

    # ── Build output DataFrame ─────────────────────────────────────────────────
    return pd.DataFrame({
        "DateTime":   DT,
        "Signal":     Signal,
        "FTflag":     FTflag,
        "ZScore":     ZScore,
        "OB":         OB_a,
        "IB":         IB_a,
        "IBS":        IBS_a,
        "BarDir":     BarDir_a,
        "BODir":      BODir_a,
        "AvgRange":   AvgRange,
        "Flip_Long":  Flip_L,
        "Flip_Short": Flip_S,
        "FlipType_L": FType_L,
        "FlipType_S": FType_S,
    })


# ── Trade parameters ───────────────────────────────────────────────────────────

@dataclass
class AMATradeParams:
    """Per-setup trade geometry attached to AMA signals.

    Stop modes
    ----------
    "BarExtreme"
        Stop placed at the far extreme of the signal bar (bull → Low, bear → High).
        For BO+FT signals the combined extreme of both bars is used (more conservative).
        `stop_offset_ticks` additional ticks of buffer beyond the extreme.

    Target modes
    ------------
    "BarRange"
        Target distance = (H - L) of the signal bar(s) × `target_mult`.
        For BO+FT the combined two-bar range is used.
    "BodyRange"
        Target distance = sum of |C - O| of the signal bar(s) × `target_mult`.
        For BO+FT both bars' bodies are summed.

    The target distance is stored as `TargetPoints` in the signal rows.
    The simulation engine applies it from the actual fill price:
        target_price = fill + direction × TargetPoints
    (sim support for TargetPoints TBD — stop is wired today).

    Stop ratchet
    ------------
    TBD — placeholder `ratchet_mode` reserved for future options.
    """
    stop_mode: str         = "BarExtreme"   # only mode currently implemented
    stop_offset_ticks: int = 1              # ticks of buffer beyond extreme
    target_mode: str       = "BarRange"     # "BarRange" | "BodyRange"
    target_mult: float     = 1.0            # range × this = target distance
    ratchet_mode: str      = "none"         # TBD


# ── Signal-row converter ───────────────────────────────────────────────────────

def to_signal_rows(
    detected: pd.DataFrame,
    bars: pd.DataFrame,
    trade_params: AMATradeParams | None = None,
    signal_types: tuple[int, ...] = (1, -1, 5, -5, 3, -3, 4),
    include_ft: bool = True,
    ob_requires_ft: bool = True,
    include_flip: bool = True,
) -> pd.DataFrame:
    """
    Convert `detect()` output to the project-standard simulation schema plus
    AMA-specific geometry columns.

    Column layout
    -------------
    SignalNum, SignalType, Direction,
    SignalBarNum    — 1-indexed position of the signal bar in `bars`
    SignalDateTime  — bar OPEN time (when the bar begins; for reference only)
    DateTime        — bar CLOSE time = SignalDateTime + 5m  ← sim fills NEXT bar's open
    EntryBarNum     — SignalBarNum + 1 (the bar where the fill lands)
    SignalPrice     — close of signal bar (= fill reference for stop geometry)
    StopMode        — name of stop rule applied
    StopOffset      — ticks of buffer used
    StopPrice       — computed stop level
    TargetMode      — name of target rule applied
    TargetMult      — multiplier applied to range measure
    TargetPoints    — target distance in points (apply from fill price, not signal close)
    Date, FilterStatus

    ⚠️  Look-ahead: DateTime is bar OPEN + 5 minutes.  The sim fills at the open of
        the NEXT bar (EntryBarNum).  Never use bars[i+1] data when building signals.
    """
    tp = trade_params or AMATradeParams()

    H  = bars["High"].to_numpy(float)
    L  = bars["Low"].to_numpy(float)
    C  = bars["Close"].to_numpy(float)
    O  = bars["Open"].to_numpy(float)
    DT = pd.to_datetime(detected["DateTime"])
    n  = len(detected)

    sig_arr  = detected["Signal"].to_numpy(int)
    ft_arr   = detected["FTflag"].to_numpy(int)
    fl_arr   = detected["Flip_Long"].to_numpy(float)
    fs_arr   = detected["Flip_Short"].to_numpy(float)
    ftl_arr  = detected["FlipType_L"].to_numpy(object)
    fts_arr  = detected["FlipType_S"].to_numpy(object)

    offset_pts = tp.stop_offset_ticks * TICK_SIZE
    rows = []

    for i in range(n):
        sig = sig_arr[i]
        ft  = ft_arr[i]
        open_dt  = DT.iloc[i]
        close_dt = open_dt + pd.Timedelta(minutes=5)
        date     = open_dt.date()
        is_ft    = ft != 0
        direction = 1 if sig > 0 else -1

        if sig != 0 and sig in signal_types:
            prior_sig = sig_arr[i - 1] if i > 0 else 0
            prior_ft  = ft_arr[i - 1]  if i > 0 else 0
            is_first_ft     = is_ft and prior_ft == 0
            is_ft_after_ob  = is_first_ft and abs(prior_sig) in (3, 4)
            is_ft_after_bo  = is_first_ft and abs(prior_sig) == 1

            # ── Decide whether to emit ────────────────────────────────────────
            # BO+FT: BO bar initiates (skipped), first FT bar is the trade.
            #        Chained FT bars are part of the running trade — skipped.
            # OB+FT: OB bar initiates (skipped when ob_requires_ft=True),
            #        first FT bar after OB is the trade.
            # BigBO / CX: single-bar setups, always emit.
            emit = False
            if abs(sig) == 1:
                if is_ft_after_bo and include_ft:
                    emit = True
                elif is_ft_after_ob and ob_requires_ft and (3 in signal_types or -3 in signal_types or 4 in signal_types):
                    emit = True
                # else: pure BO bar, chained FT, or filtered → skip
            elif abs(sig) in (3, 4):
                if not ob_requires_ft:
                    emit = True   # standalone OB — no FT required
                # else: OB bar is setup-only; wait for FT bar
            else:
                emit = True       # BigBO (±5), CX (±2) — standalone

            if emit:
                # ── Stop geometry ─────────────────────────────────────────────
                # For two-bar setups (FT bar) use combined extreme of both bars.
                two_bar = is_ft and i > 0
                if tp.stop_mode == "BarExtreme":
                    if direction == 1:
                        bar_low  = min(L[i], L[i-1]) if two_bar else L[i]
                        stop_px  = bar_low - offset_pts
                    else:
                        bar_high = max(H[i], H[i-1]) if two_bar else H[i]
                        stop_px  = bar_high + offset_pts
                else:
                    stop_px = 0.0

                # ── Target geometry ───────────────────────────────────────────
                if tp.target_mode == "BarRange":
                    tgt_pts = ((max(H[i], H[i-1]) - min(L[i], L[i-1])) if two_bar
                               else (H[i] - L[i])) * tp.target_mult
                elif tp.target_mode == "BodyRange":
                    body_i  = abs(C[i] - O[i])
                    body_i1 = abs(C[i-1] - O[i-1]) if two_bar else 0.0
                    tgt_pts = (body_i + body_i1) * tp.target_mult
                else:
                    tgt_pts = 0.0

                rows.append({
                    "SignalType":    _signal_type(sig, is_ft, prior_sig),
                    "Direction":     "Long" if direction == 1 else "Short",
                    "SignalBarNum":  i + 1,
                    "SignalDateTime": open_dt,
                    "DateTime":      close_dt,
                    "EntryBarNum":   i + 2,
                    "SignalPrice":   float(C[i]),
                    "StopMode":      tp.stop_mode,
                    "StopOffset":    tp.stop_offset_ticks,
                    "StopPrice":     float(stop_px),
                    "TargetMode":    tp.target_mode,
                    "TargetMult":    tp.target_mult,
                    "TargetPoints":  float(tgt_pts),
                    "Date":          date,
                    "FilterStatus":  "ok",
                })

        if include_flip:
            fl   = fl_arr[i]
            fs_v = fs_arr[i]
            if fl != 0:
                rows.append({
                    "SignalType":    f"Flip_L_{ftl_arr[i]}",
                    "Direction":     "Long",
                    "SignalBarNum":  i + 1,
                    "SignalDateTime": open_dt,
                    "DateTime":      close_dt,
                    "EntryBarNum":   i + 2,
                    "SignalPrice":   float(C[i]),
                    "StopMode":      "FlipDot",
                    "StopOffset":    0,
                    "StopPrice":     float(fl),
                    "TargetMode":    tp.target_mode,
                    "TargetMult":    tp.target_mult,
                    "TargetPoints":  float((H[i] - L[i]) * tp.target_mult),
                    "Date":          date,
                    "FilterStatus":  "ok",
                })
            if fs_v != 0:
                rows.append({
                    "SignalType":    f"Flip_S_{fts_arr[i]}",
                    "Direction":     "Short",
                    "SignalBarNum":  i + 1,
                    "SignalDateTime": open_dt,
                    "DateTime":      close_dt,
                    "EntryBarNum":   i + 2,
                    "SignalPrice":   float(C[i]),
                    "StopMode":      "FlipDot",
                    "StopOffset":    0,
                    "StopPrice":     float(fs_v),
                    "TargetMode":    tp.target_mode,
                    "TargetMult":    tp.target_mult,
                    "TargetPoints":  float((H[i] - L[i]) * tp.target_mult),
                    "Date":          date,
                    "FilterStatus":  "ok",
                })

    if not rows:
        return _empty_signal_schema()

    df = pd.DataFrame(rows).reset_index(drop=True)
    df.insert(0, "SignalNum", range(1, len(df) + 1))
    return df


def _signal_type(sig: int, is_ft: bool, prior_sig: int = 0) -> str:
    if abs(sig) == 5:  return "BigBO"
    if abs(sig) == 3:  return "OB"
    if abs(sig) == 4:  return "OB_Doji"
    if abs(sig) == 2:  return "CX"
    if is_ft and abs(prior_sig) in (3, 4): return "OB+FT"
    return "BO+FT" if is_ft else "BO"


def _empty_signal_schema() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "SignalNum", "SignalType", "Direction",
        "SignalBarNum", "SignalDateTime", "DateTime", "EntryBarNum",
        "SignalPrice", "StopMode", "StopOffset", "StopPrice",
        "TargetMode", "TargetMult", "TargetPoints",
        "Date", "FilterStatus",
    ])
