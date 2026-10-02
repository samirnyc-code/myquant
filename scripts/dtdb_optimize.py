"""dtdb_optimize.py — grid-search DtDbScanner's detection parameters per bar type,
select by in-sample performance, report out-of-sample.

Bar types: tick [1500,2000,2500,5000,7500,10000] and time [3,5,10,15] minutes.
Grid (structure/confirmation params, same meaning as the NinjaScript properties):
  SwingStrength       {3,4,5,6,8}
  PeakToleranceTicks  {4,6,8,12}
  MinValleyDepthTicks {6,10,16,24}
  MinBarsBetween      {4,6,10}
  MaxBarsBetween      {80,120,200}
  NecklineBufferTicks {1,2,4}
  ConfirmWithinBars   {80,150,250}
  = 19,440 combos/bar type x 10 bar types = 194,400 combos.

Entry/exit rule is unchanged from dtdb_backtest.py (technical stop = InvalidateBeyond,
target = measured move, 1 tick adverse slippage) and score is NOT computed here — the
live indicator's confirm alert is unconditional on score, so it has no effect on which
trades are taken and is dropped entirely from this search.

Two-stage design for tractability:
  1. FAST engine (this file): vectorized pivot detection (cached per SwingStrength) +
     per-pending-episode vectorized confirm/invalidate resolution (not a per-bar Python
     loop) + bar-level (not tick-level) forward scan for stop/target. Used for the full
     grid, ranked on the first 60 of 90 days (in-sample).
  2. EXACT engine: the tick-by-tick walk from dtdb_backtest.py, run only on the top
     in-sample config per bar type, over the full 90 days, split IS/OOS for reporting.

Self-check: the fast engine's trade COUNT/direction-split (Phase A-C, independent of the
exit model) is asserted against dtdb_backtest.py's already-committed default-param numbers
before the grid runs.

Usage: python scripts/dtdb_optimize.py
Output: data/dtdb_backtest/grid_<date>.csv (full grid, all bar types)
        data/dtdb_backtest/optimized_<date>.csv (top-IS config per bar type, exact OOS/IS)
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tickdata  # noqa: E402
from dtdb_backtest import (  # noqa: E402
    TICK_SIZE, ES_PER_TICK, MES_PER_TICK, MES_RT_COMMISSION,
    SWING_STRENGTH as DEFAULT_SWING, PEAK_TOL_TICKS as DEFAULT_PEAK_TOL,
    MIN_VALLEY_DEPTH_TICKS as DEFAULT_MIN_DEPTH, MIN_BARS_BETWEEN as DEFAULT_MIN_BARS,
    MAX_BARS_BETWEEN as DEFAULT_MAX_BARS, NECKLINE_BUFFER_TICKS as DEFAULT_NECK_BUF,
    CONFIRM_WITHIN_BARS as DEFAULT_CONFIRM_WITHIN,
    build_bars as build_tick_bars, make_trade, simulate_day as simulate_day_exact_default,
)

LOOKBACK_DAYS = 90
IS_DAYS = 60  # first 60 of 90 = in-sample selection; last 30 = out-of-sample report

TICK_INTERVALS = [1500, 2000, 2500, 5000, 7500, 10000]
TIME_INTERVALS_MIN = [3, 5, 10, 15]

GRID = dict(
    swing=[3, 4, 5, 6, 8],
    peak_tol=[4, 6, 8, 12],
    min_depth=[6, 10, 16, 24],
    min_bars=[4, 6, 10],
    max_bars=[80, 120, 200],
    neck_buf=[1, 2, 4],
    confirm_within=[80, 150, 250],
)

MIN_IS_TRADES = 10  # filter out configs too thin to trust on the 60-day IS window


# ============================================================================
# Bar construction (independent of search params; built once per day/bar-type)
# ============================================================================

def build_time_bars(times: np.ndarray, prices: np.ndarray, minutes: int):
    if len(times) == 0:
        return None
    day0 = times[0].astype("datetime64[D]")
    anchor = day0 + np.timedelta64(8 * 60 + 30, "m")
    step = np.timedelta64(minutes, "m")
    bin_idx = ((times - anchor) // step).astype(np.int64)
    bin_idx = np.maximum(bin_idx, 0)
    change = np.flatnonzero(np.diff(bin_idx)) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [len(prices)]))
    nbars = len(starts)
    O = np.empty(nbars); H = np.empty(nbars); L = np.empty(nbars); C = np.empty(nbars)
    end_idx = np.empty(nbars, dtype=np.int64)
    for i, (s, e) in enumerate(zip(starts, ends)):
        seg = prices[s:e]
        O[i] = seg[0]; H[i] = seg.max(); L[i] = seg.min(); C[i] = seg[-1]
        end_idx[i] = e - 1
    return O, H, L, C, end_idx


def build_bars_for(bar_type: str, n, prices, times):
    if bar_type == "tick":
        return build_tick_bars(prices, n)
    return build_time_bars(times, prices, n)


# ============================================================================
# Phase A — vectorized pivot detection (per day, per SwingStrength)
# ============================================================================

def detect_pivots(H: np.ndarray, L: np.ndarray, s: int):
    n = len(H)
    lo = s + 2
    hi = n - 1 - s
    if hi < lo:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)

    sH = pd.Series(H)
    left_max = sH.shift(1).rolling(window=s, min_periods=s).max().to_numpy()
    right_max = sH[::-1].shift(1).rolling(window=s, min_periods=s).max().to_numpy()[::-1]
    sL = pd.Series(L)
    left_min = sL.shift(1).rolling(window=s, min_periods=s).min().to_numpy()
    right_min = sL[::-1].shift(1).rolling(window=s, min_periods=s).min().to_numpy()[::-1]

    is_high = (H > left_max) & (H > right_max)
    is_low = (L < left_min) & (L < right_min)
    mask = np.zeros(n, dtype=bool)
    mask[lo:hi + 1] = True
    is_high &= mask
    is_low &= mask
    return np.flatnonzero(is_high), np.flatnonzero(is_low)


# ============================================================================
# Phase B — structure formation from pivot events (merged chronological order)
# ============================================================================

def phase_b_events(high_c, low_c, H, L, s, peak_tol_ticks, min_depth_ticks, min_bars, max_bars):
    tol = peak_tol_ticks * TICK_SIZE
    min_depth = min_depth_ticks * TICK_SIZE

    events = []  # (current_bar, 'H'|'L', c)
    events += [(c + s, "H", c) for c in high_c]
    events += [(c + s, "L", c) for c in low_c]
    events.sort(key=lambda e: (e[0], 0 if e[1] == "H" else 1))

    highs: list[tuple[float, int]] = []
    lows: list[tuple[float, int]] = []
    top_events = []     # (form_bar, neckline, invalidate)
    bottom_events = []

    def lowest_low_between(a, b):
        best = None
        for p, bb in lows:
            if a < bb < b and (best is None or p < best[0]):
                best = (p, bb)
        return best

    def highest_high_between(a, b):
        best = None
        for p, bb in highs:
            if a < bb < b and (best is None or p > best[0]):
                best = (p, bb)
        return best

    for current_bar, kind, c in events:
        if kind == "H":
            price = H[c]
            highs.append((price, c))
            if len(highs) >= 2:
                p1, p2 = highs[-2], highs[-1]
                valley = lowest_low_between(p1[1], p2[1])
                if valley is not None:
                    peak_diff = abs(p1[0] - p2[0])
                    valley_depth = min(p1[0], p2[0]) - valley[0]
                    bars_between = p2[1] - p1[1]
                    if (peak_diff <= tol and valley_depth >= min_depth
                            and min_bars <= bars_between <= max_bars):
                        top_events.append((current_bar, valley[0], max(p1[0], p2[0])))
        else:
            price = L[c]
            lows.append((price, c))
            if len(lows) >= 2:
                t1, t2 = lows[-2], lows[-1]
                peak = highest_high_between(t1[1], t2[1])
                if peak is not None:
                    trough_diff = abs(t1[0] - t2[0])
                    peak_height = peak[0] - max(t1[0], t2[0])
                    bars_between = t2[1] - t1[1]
                    if (trough_diff <= tol and peak_height >= min_depth
                            and min_bars <= bars_between <= max_bars):
                        bottom_events.append((current_bar, peak[0], min(t1[0], t2[0])))

    return top_events, bottom_events


# ============================================================================
# Phase C+D — vectorized confirm/invalidate resolution + bar-level exit scan
# ============================================================================

def _first_true(mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def resolve_side(events, H, L, C, nbars, is_top, neck_buf_ticks, confirm_within):
    buf = neck_buf_ticks * TICK_SIZE
    out = []
    for i, (form_bar, neckline, invalidate) in enumerate(events):
        upper = events[i + 1][0] - 1 if i + 1 < len(events) else nbars - 1
        bound = min(upper - form_bar, confirm_within)
        if bound < 0:
            continue
        end = form_bar + bound + 1
        if is_top:
            seg_h = H[form_bar:end]
            seg_c = C[form_bar:end]
            inv_idx = _first_true(seg_h > invalidate)
            conf_idx = _first_true(seg_c < neckline - buf)
        else:
            seg_l = L[form_bar:end]
            seg_c = C[form_bar:end]
            inv_idx = _first_true(seg_l < invalidate)
            conf_idx = _first_true(seg_c > neckline + buf)

        if inv_idx is not None and (conf_idx is None or inv_idx <= conf_idx):
            continue
        if conf_idx is None:
            continue
        confirm_bar = form_bar + conf_idx
        out.append((confirm_bar, neckline, invalidate))
    return out


def exit_bar_level(confirm_bar, neckline, invalidate, is_top, H, L, C, nbars):
    direction_short = is_top
    height = (invalidate - neckline) if direction_short else (neckline - invalidate)
    target = (neckline - height) if direction_short else (neckline + height)
    stop = invalidate

    raw_entry = C[confirm_bar]
    entry_price = raw_entry - TICK_SIZE if direction_short else raw_entry + TICK_SIZE

    start = confirm_bar + 1
    if start >= nbars:
        exit_price = raw_entry
    else:
        seg_h, seg_l, seg_c = H[start:], L[start:], C[start:]
        if direction_short:
            si = _first_true(seg_h >= stop)
            ti = _first_true(seg_l <= target)
        else:
            si = _first_true(seg_l <= stop)
            ti = _first_true(seg_h >= target)

        if si is not None and (ti is None or si <= ti):
            exit_price = (stop + TICK_SIZE) if direction_short else (stop - TICK_SIZE)
        elif ti is not None:
            exit_price = target
        else:
            exit_price = (seg_c[-1] + TICK_SIZE) if direction_short else (seg_c[-1] - TICK_SIZE)

    pnl_ticks = ((entry_price - exit_price) if direction_short else (exit_price - entry_price)) / TICK_SIZE
    return pnl_ticks


# ============================================================================
# Driver
# ============================================================================

def load_day_bars(days, day_cache, bar_type, interval):
    """Per-day (O,H,L,C,end_idx), cached per (bar_type, interval)."""
    out = {}
    for d in days:
        prices, times = day_cache[d]
        built = build_bars_for(bar_type, interval, prices, times)
        out[d] = built
    return out


def run_grid_for_bar_type(bar_type, interval, days, is_days_set, day_cache, bars_cache):
    rows = []
    # Phase A cached per SwingStrength
    pivots_cache = {}
    for s in GRID["swing"]:
        per_day = {}
        for d in days:
            built = bars_cache[d]
            if built is None:
                per_day[d] = (np.array([], dtype=np.int64), np.array([], dtype=np.int64))
                continue
            O, H, L, C, end_idx = built
            per_day[d] = detect_pivots(H, L, s)
        pivots_cache[s] = per_day

    for s, peak_tol, min_depth, min_bars, max_bars in itertools.product(
        GRID["swing"], GRID["peak_tol"], GRID["min_depth"], GRID["min_bars"], GRID["max_bars"]
    ):
        # Phase B per day (reused across neck_buf x confirm_within)
        events_by_day = {}
        for d in days:
            built = bars_cache[d]
            if built is None:
                events_by_day[d] = ([], [])
                continue
            O, H, L, C, end_idx = built
            high_c, low_c = pivots_cache[s][d]
            events_by_day[d] = phase_b_events(high_c, low_c, H, L, s, peak_tol, min_depth, min_bars, max_bars)

        for neck_buf, confirm_within in itertools.product(GRID["neck_buf"], GRID["confirm_within"]):
            is_pnl, is_n = [], 0
            oos_pnl, oos_n = [], 0
            for d in days:
                built = bars_cache[d]
                if built is None:
                    continue
                O, H, L, C, end_idx = built
                nbars = len(O)
                top_events, bottom_events = events_by_day[d]

                confirmed_top = resolve_side(top_events, H, L, C, nbars, True, neck_buf, confirm_within)
                confirmed_bot = resolve_side(bottom_events, H, L, C, nbars, False, neck_buf, confirm_within)

                day_pnl = []
                for cb, neck, inv in confirmed_top:
                    day_pnl.append(exit_bar_level(cb, neck, inv, True, H, L, C, nbars))
                for cb, neck, inv in confirmed_bot:
                    day_pnl.append(exit_bar_level(cb, neck, inv, False, H, L, C, nbars))

                if d in is_days_set:
                    is_pnl.extend(day_pnl); is_n += len(day_pnl)
                else:
                    oos_pnl.extend(day_pnl); oos_n += len(day_pnl)

            is_arr = np.array(is_pnl) if is_pnl else np.array([])
            oos_arr = np.array(oos_pnl) if oos_pnl else np.array([])
            is_mes = is_arr.sum() * MES_PER_TICK - len(is_arr) * MES_RT_COMMISSION if len(is_arr) else 0.0
            oos_mes = oos_arr.sum() * MES_PER_TICK - len(oos_arr) * MES_RT_COMMISSION if len(oos_arr) else 0.0

            rows.append(dict(
                bar_type=bar_type, interval=interval,
                swing=s, peak_tol=peak_tol, min_depth=min_depth, min_bars=min_bars,
                max_bars=max_bars, neck_buf=neck_buf, confirm_within=confirm_within,
                is_trades=is_n, is_ticks=round(is_arr.sum(), 1) if len(is_arr) else 0.0,
                is_mes_net=round(is_mes, 0),
                oos_trades=oos_n, oos_ticks=round(oos_arr.sum(), 1) if len(oos_arr) else 0.0,
                oos_mes_net=round(oos_mes, 0),
            ))
    return rows


def self_check(days, day_cache):
    """Fast engine's confirmed trade COUNT (Phase A-C) must match dtdb_backtest.py's
    already-committed default-param run exactly — confirmation doesn't depend on the
    exit model, so this isolates correctness of the pivot/structure/confirm logic."""
    expected = {1500: 358, 2000: 233, 2500: 163, 5000: 65}  # ALL (DT+DB), default params, 90d
    for n, exp_total in expected.items():
        total = 0
        for d in days:
            prices, times = day_cache[d]
            built = build_tick_bars(prices, n)
            if built is None:
                continue
            O, H, L, C, end_idx = built
            nbars = len(O)
            high_c, low_c = detect_pivots(H, L, DEFAULT_SWING)
            top_ev, bot_ev = phase_b_events(high_c, low_c, H, L, DEFAULT_SWING,
                                             DEFAULT_PEAK_TOL, DEFAULT_MIN_DEPTH,
                                             DEFAULT_MIN_BARS, DEFAULT_MAX_BARS)
            ct = resolve_side(top_ev, H, L, C, nbars, True, DEFAULT_NECK_BUF, DEFAULT_CONFIRM_WITHIN)
            cb = resolve_side(bot_ev, H, L, C, nbars, False, DEFAULT_NECK_BUF, DEFAULT_CONFIRM_WITHIN)
            total += len(ct) + len(cb)
        status = "OK" if total == exp_total else "MISMATCH"
        print(f"self-check {n}t: fast engine={total} vs exact engine={exp_total}  [{status}]")
        if total != exp_total:
            raise RuntimeError(f"fast engine diverges from validated exact engine at {n}t: "
                                f"{total} != {exp_total}")


def exact_verify(bar_type, interval, days, day_cache, params):
    """Re-run the top config through the EXACT tick-level engine (dtdb_backtest.py's
    per-bar loop + tick-walk fills), generalized to accept arbitrary params and time bars."""
    import dtdb_backtest as db

    trades = []
    for d in days:
        prices, times = day_cache[d]
        built = build_bars_for(bar_type, interval, prices, times)
        if built is None:
            continue
        O, H, L, C, end_idx = built
        nbars = len(O)
        if nbars < 2 * params["swing"] + 2:
            continue

        TR = np.empty(nbars); TR[0] = H[0] - L[0]
        for i in range(1, nbars):
            TR[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
        atr_sma = pd.Series(TR).rolling(14).mean().to_numpy()

        highs, lows = [], []
        pending_top = pending_bottom = None
        tol = params["peak_tol"] * TICK_SIZE
        min_depth = params["min_depth"] * TICK_SIZE
        buf = params["neck_buf"] * TICK_SIZE
        s = params["swing"]

        def lowest_low_between(a, b):
            best = None
            for p, bb in lows:
                if a < bb < b and (best is None or p < best[0]):
                    best = (p, bb)
            return best

        def highest_high_between(a, b):
            best = None
            for p, bb in highs:
                if a < bb < b and (best is None or p > best[0]):
                    best = (p, bb)
            return best

        for i in range(nbars):
            current_bar = i
            if current_bar < 2 * s + 2:
                continue
            atr = atr_sma[i] if current_bar > 14 and not np.isnan(atr_sma[i]) else TICK_SIZE * 20
            if atr <= 0:
                atr = TICK_SIZE * 20

            cand = current_bar - s
            cand_high, cand_low = H[cand], L[cand]
            is_high = is_low = True
            for k in range(1, s + 1):
                jf, jb = cand + k, cand - k
                if H[jf] >= cand_high or H[jb] >= cand_high:
                    is_high = False
                if L[jf] <= cand_low or L[jb] <= cand_low:
                    is_low = False
            abs_bar = cand

            if is_high:
                if not highs or highs[-1][1] != abs_bar:
                    highs.append((cand_high, abs_bar))
                    if len(highs) >= 2:
                        p1, p2 = highs[-2], highs[-1]
                        valley = lowest_low_between(p1[1], p2[1])
                        if valley is not None:
                            peak_diff = abs(p1[0] - p2[0])
                            valley_depth = min(p1[0], p2[0]) - valley[0]
                            bars_between = p2[1] - p1[1]
                            if (peak_diff <= tol and valley_depth >= min_depth
                                    and params["min_bars"] <= bars_between <= params["max_bars"]):
                                pending_top = dict(neckline=valley[0], invalidate=max(p1[0], p2[0]),
                                                    form_bar=current_bar, score=0.0)
            if is_low:
                if not lows or lows[-1][1] != abs_bar:
                    lows.append((cand_low, abs_bar))
                    if len(lows) >= 2:
                        t1, t2 = lows[-2], lows[-1]
                        peak = highest_high_between(t1[1], t2[1])
                        if peak is not None:
                            trough_diff = abs(t1[0] - t2[0])
                            peak_height = peak[0] - max(t1[0], t2[0])
                            bars_between = t2[1] - t1[1]
                            if (trough_diff <= tol and peak_height >= min_depth
                                    and params["min_bars"] <= bars_between <= params["max_bars"]):
                                pending_bottom = dict(neckline=peak[0], invalidate=min(t1[0], t2[0]),
                                                       form_bar=current_bar, score=0.0)

            if pending_top is not None:
                if H[i] > pending_top["invalidate"]:
                    pending_top = None
                elif current_bar - pending_top["form_bar"] > params["confirm_within"]:
                    pending_top = None
                elif C[i] < pending_top["neckline"] - buf:
                    tr = make_trade("DT", "short", pending_top, i, end_idx, prices, times)
                    tr["bar_type"] = bar_type; tr["interval"] = interval; tr["day"] = d
                    trades.append(tr)
                    pending_top = None
            if pending_bottom is not None:
                if L[i] < pending_bottom["invalidate"]:
                    pending_bottom = None
                elif current_bar - pending_bottom["form_bar"] > params["confirm_within"]:
                    pending_bottom = None
                elif C[i] > pending_bottom["neckline"] + buf:
                    tr = make_trade("DB", "long", pending_bottom, i, end_idx, prices, times)
                    tr["bar_type"] = bar_type; tr["interval"] = interval; tr["day"] = d
                    trades.append(tr)
                    pending_bottom = None

    return pd.DataFrame(trades)


def stats_for(df: pd.DataFrame):
    if df.empty:
        return dict(trades=0, win_rate=np.nan, avg_r=np.nan, profit_factor=np.nan,
                    total_ticks=0.0, total_usd_ES=0.0, total_usd_MES_net=0.0, max_dd_ticks=0.0)
    wins = df[df["pnl_ticks"] > 0]
    losses = df[df["pnl_ticks"] <= 0]
    gw, gl = wins["pnl_ticks"].sum(), -losses["pnl_ticks"].sum()
    pf = gw / gl if gl > 0 else np.inf
    cum = df.sort_values("entry_time")["pnl_ticks"].cumsum()
    maxdd = (cum - cum.cummax()).min() if len(cum) else 0.0
    net_mes = df["pnl_ticks"].sum() * MES_PER_TICK - len(df) * MES_RT_COMMISSION
    return dict(
        trades=len(df), win_rate=round(100 * len(wins) / len(df), 1),
        avg_r=round(df["r_multiple"].mean(), 3), profit_factor=round(pf, 2) if np.isfinite(pf) else "inf",
        total_ticks=round(df["pnl_ticks"].sum(), 1), total_usd_ES=round(df["pnl_ticks"].sum() * ES_PER_TICK, 0),
        total_usd_MES_net=round(net_mes, 0), max_dd_ticks=round(maxdd, 1),
    )


if __name__ == "__main__":
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    out_dir = Path(__file__).resolve().parent.parent / "data" / "dtdb_backtest"
    out_dir.mkdir(parents=True, exist_ok=True)

    days = tickdata.available("rth")[-LOOKBACK_DAYS:]
    is_days_set = set(days[:IS_DAYS])
    oos_days_set = set(days[IS_DAYS:])
    print(f"Period: {days[0]} -> {days[-1]} ({len(days)}d). "
          f"IS={days[0]}->{days[IS_DAYS-1]} ({IS_DAYS}d), OOS={days[IS_DAYS]}->{days[-1]} ({len(days)-IS_DAYS}d)")

    day_cache = {}
    for d in days:
        df = tickdata.load_rth(d)
        day_cache[d] = (df["Price"].to_numpy(dtype=np.float64), df["DateTime"].to_numpy())

    print("Running self-check vs committed exact-engine results ...")
    self_check(days, day_cache)

    bar_types = [("tick", n) for n in TICK_INTERVALS] + [("time", m) for m in TIME_INTERVALS_MIN]

    all_rows = []
    for bar_type, interval in bar_types:
        label = f"{interval}t" if bar_type == "tick" else f"{interval}min"
        print(f"grid search {label} ...")
        bars_cache = load_day_bars(days, day_cache, bar_type, interval)
        rows = run_grid_for_bar_type(bar_type, interval, days, is_days_set, day_cache, bars_cache)
        all_rows.extend(rows)
        print(f"  {label}: {len(rows)} combos")

    grid_df = pd.DataFrame(all_rows)
    grid_path = out_dir / f"grid_{today}.csv"
    grid_df.to_csv(grid_path, index=False)
    print(f"grid -> {grid_path} ({len(grid_df)} rows)")

    # select top-3 by IS net MES $ per bar type, subject to a minimum IS trade count
    opt_rows = []
    exact_trade_frames = []
    for bar_type, interval in bar_types:
        sub = grid_df[(grid_df["bar_type"] == bar_type) & (grid_df["interval"] == interval)]
        sub = sub[sub["is_trades"] >= MIN_IS_TRADES]
        if sub.empty:
            print(f"{bar_type} {interval}: no config clears {MIN_IS_TRADES}+ IS trades, skipping exact verify")
            continue
        top3 = sub.sort_values("is_mes_net", ascending=False).head(3)
        for rank, (_, row) in enumerate(top3.iterrows(), start=1):
            params = dict(swing=int(row["swing"]), peak_tol=int(row["peak_tol"]),
                          min_depth=int(row["min_depth"]), min_bars=int(row["min_bars"]),
                          max_bars=int(row["max_bars"]), neck_buf=int(row["neck_buf"]),
                          confirm_within=int(row["confirm_within"]))
            exact_df = exact_verify(bar_type, interval, days, day_cache, params)
            is_exact = exact_df[exact_df["day"].isin(is_days_set)] if not exact_df.empty else exact_df
            oos_exact = exact_df[exact_df["day"].isin(oos_days_set)] if not exact_df.empty else exact_df
            is_stats = stats_for(is_exact)
            oos_stats = stats_for(oos_exact)
            opt_rows.append(dict(
                bar_type=bar_type, interval=interval, is_rank=rank, **params,
                is_trades=is_stats["trades"], is_win_rate=is_stats["win_rate"], is_avg_r=is_stats["avg_r"],
                is_pf=is_stats["profit_factor"], is_ticks=is_stats["total_ticks"],
                is_usd_MES_net=is_stats["total_usd_MES_net"],
                oos_trades=oos_stats["trades"], oos_win_rate=oos_stats["win_rate"], oos_avg_r=oos_stats["avg_r"],
                oos_pf=oos_stats["profit_factor"], oos_ticks=oos_stats["total_ticks"],
                oos_usd_ES=oos_stats["total_usd_ES"], oos_usd_MES_net=oos_stats["total_usd_MES_net"],
                oos_max_dd_ticks=oos_stats["max_dd_ticks"],
            ))
            if not exact_df.empty:
                exact_trade_frames.append(exact_df.assign(is_rank=rank))

    opt_df = pd.DataFrame(opt_rows)
    opt_path = out_dir / f"optimized_{today}.csv"
    opt_df.to_csv(opt_path, index=False)
    print(f"optimized -> {opt_path}")

    if exact_trade_frames:
        trades_all = pd.concat(exact_trade_frames, ignore_index=True)
        trades_path = out_dir / f"optimized_trades_{today}.csv"
        trades_all.to_csv(trades_path, index=False)
        print(f"optimized trades -> {trades_path}")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(opt_df.to_string(index=False))
