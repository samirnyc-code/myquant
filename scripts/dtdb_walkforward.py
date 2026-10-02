"""dtdb_walkforward.py — full-history walk-forward optimization of DtDbScanner.

Addresses three gaps in the prior 90-day single-split analysis (dtdb_optimize.py):
  1. Full RTH trove (2021-06-18 -> most recent day), not 90 days.
  2. Expanding-window, calendar-year walk-forward folds (train on all prior years,
     test on the next full year) instead of one in-sample/out-of-sample split.
  3. A stop/target sweep layered on top of the structure-detection grid: stop is a
     multiple of the structure's own risk distance (entry -> InvalidateBeyond),
     target is an R-multiple of THAT stop. Replaces the single fixed "measured move"
     rule used previously.
  4. A minimum trades/day gate applied during selection (on the train side only, to
     avoid selecting on OOS) — configs that don't clear it are not eligible, however
     good their P&L, because they trade too rarely to be usable.

ES only (no MES, no commission assumption) — ticks and $ES (12.50/tick) throughout.

Folds (RTH trove 2021-06-18 -> 2026-10-01):
  F1: train 2021-2022 (388d) -> test 2023 (250d)
  F2: train 2021-2023 (638d) -> test 2024 (252d)
  F3: train 2021-2024 (890d) -> test 2025 (252d)
  F4: train 2021-2025 (1142d) -> test 2026 YTD (189d, partial year)

Structure grid (same 6,480 combos as dtdb_optimize.py, same meaning):
  SwingStrength{3,4,5,6,8} x PeakToleranceTicks{4,6,8,12} x MinValleyDepthTicks{6,10,16,24}
  x MinBarsBetween{4,6,10} x MaxBarsBetween{80,120,200} x NecklineBufferTicks{1,2,4}
  x ConfirmWithinBars{80,150,250}

Stop/target sweep (15 combos, evaluated only for combos clearing the frequency gate):
  stop_mult {0.5, 0.75, 1.0} x base_risk (entry -> InvalidateBeyond)
  target_R  {1, 1.5, 2, 3, 4} x the resulting stop distance

Selection per (bar_type, fold): among structure-combos with train trades/day >= 3,
pick the (structure-combo, stop_mult, target_R) maximizing train net ticks. Verify
that single config on the fold's test days with the exact tick-level engine.

Usage: python scripts/dtdb_walkforward.py
Output: data/dtdb_backtest/wf_folds_<date>.csv   (per bar-type x fold, chosen config + OOS stats)
        data/dtdb_backtest/wf_trades_<date>.csv  (every OOS trade, all folds, all bar types)
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tickdata  # noqa: E402
from dtdb_backtest import TICK_SIZE, ES_PER_TICK  # noqa: E402
from dtdb_optimize import (  # noqa: E402
    GRID, TICK_INTERVALS, TIME_INTERVALS_MIN,
    build_tick_bars, build_time_bars, build_bars_for,
    detect_pivots, phase_b_events, resolve_side, self_check,
)

MIN_TRADES_PER_DAY = 3.0
STOP_MULTS = [0.5, 0.75, 1.0]
TARGET_RS = [1.0, 1.5, 2.0, 3.0, 4.0]

PHASE_B_COMBOS = list(itertools.product(
    GRID["swing"], GRID["peak_tol"], GRID["min_depth"], GRID["min_bars"], GRID["max_bars"]))
PHASE_C_COMBOS = list(itertools.product(GRID["neck_buf"], GRID["confirm_within"]))

BAR_TYPES = [("tick", n) for n in TICK_INTERVALS] + [("time", m) for m in TIME_INTERVALS_MIN]


def _first_true(mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def exit_bar_level_rr(confirm_bar, neckline, invalidate, is_top, H, L, C, nbars, stop_mult, target_r):
    direction_short = is_top
    raw_entry = C[confirm_bar]
    base_risk = abs(raw_entry - invalidate)
    risk = base_risk * stop_mult
    stop = (raw_entry + risk) if direction_short else (raw_entry - risk)
    target = (raw_entry - risk * target_r) if direction_short else (raw_entry + risk * target_r)
    entry_price = raw_entry - TICK_SIZE if direction_short else raw_entry + TICK_SIZE

    start = confirm_bar + 1
    if start >= nbars:
        exit_price = raw_entry
    else:
        seg_h, seg_l, seg_c = H[start:], L[start:], C[start:]
        if direction_short:
            si, ti = _first_true(seg_h >= stop), _first_true(seg_l <= target)
        else:
            si, ti = _first_true(seg_l <= stop), _first_true(seg_h >= target)
        if si is not None and (ti is None or si <= ti):
            exit_price = (stop + TICK_SIZE) if direction_short else (stop - TICK_SIZE)
        elif ti is not None:
            exit_price = target
        else:
            exit_price = (seg_c[-1] + TICK_SIZE) if direction_short else (seg_c[-1] - TICK_SIZE)

    pnl_ticks = ((entry_price - exit_price) if direction_short else (exit_price - entry_price)) / TICK_SIZE
    risk_ticks = risk / TICK_SIZE
    return pnl_ticks, risk_ticks


def build_all_bars_for_day(prices, times):
    out = {}
    for n in TICK_INTERVALS:
        built = build_tick_bars(prices, n)
        if built is not None:
            O, H, L, C, _ = built
            out[("tick", n)] = (O, H, L, C)
    for m in TIME_INTERVALS_MIN:
        built = build_time_bars(times, prices, m)
        if built is not None:
            O, H, L, C, _ = built
            out[("time", m)] = (O, H, L, C)
    return out


def make_folds(days):
    by_year = {}
    for d in days:
        by_year.setdefault(d[:4], []).append(d)
    years = sorted(by_year)
    folds = []
    for i in range(1, len(years)):
        test_year = years[i]
        train_days = [d for y in years[:i] for d in by_year[y]]
        test_days = by_year[test_year]
        folds.append((years[i - 1], test_year, train_days, test_days))
    return folds


def phase_ab_events_for_combo(bar_type, interval, combo, days, bars_by_spec, pivots_cache):
    swing, peak_tol, min_depth, min_bars, max_bars = combo
    events_by_day = {}
    for d in days:
        O, H, L, C = bars_by_spec[(bar_type, interval)][d]
        high_c, low_c = pivots_cache[swing][d]
        events_by_day[d] = phase_b_events(high_c, low_c, H, L, swing, peak_tol, min_depth, min_bars, max_bars)
    return events_by_day


def confirmed_for_combo(bar_type, interval, combo, neck_buf, confirm_within, days, bars_by_spec, events_by_day):
    out = {}
    for d in days:
        O, H, L, C = bars_by_spec[(bar_type, interval)][d]
        nbars = len(O)
        top_ev, bot_ev = events_by_day[d]
        ct = resolve_side(top_ev, H, L, C, nbars, True, neck_buf, confirm_within)
        cb = resolve_side(bot_ev, H, L, C, nbars, False, neck_buf, confirm_within)
        out[d] = (ct, cb)
    return out


def run_bar_type(bar_type, interval, all_days, folds, bars_by_spec):
    label = f"{interval}t" if bar_type == "tick" else f"{interval}min"
    valid_days = bars_by_spec[(bar_type, interval)].keys()

    pivots_cache = {}
    for s in GRID["swing"]:
        pivots_cache[s] = {}
        for d in valid_days:
            O, H, L, C = bars_by_spec[(bar_type, interval)][d]
            pivots_cache[s][d] = detect_pivots(H, L, s)

    fold_results = []
    for train_label, test_label, train_days_all, test_days_all in folds:
        train_days = [d for d in train_days_all if d in valid_days]
        test_days = [d for d in test_days_all if d in valid_days]
        dropped_train = len(train_days_all) - len(train_days)
        dropped_test = len(test_days_all) - len(test_days)
        if dropped_train or dropped_test:
            print(f"  {label} fold train<={train_label}: dropped {dropped_train} thin train day(s), "
                  f"{dropped_test} thin test day(s) (too few ticks for a full {label} bar)")
        candidates = []  # (combo7, train_net_ticks, train_trades, trades_per_day)
        for combo in PHASE_B_COMBOS:
            events_by_day = phase_ab_events_for_combo(bar_type, interval, combo, train_days, bars_by_spec, pivots_cache)
            for neck_buf, confirm_within in PHASE_C_COMBOS:
                confirmed = confirmed_for_combo(bar_type, interval, combo, neck_buf, confirm_within,
                                                 train_days, bars_by_spec, events_by_day)
                n_trades = sum(len(ct) + len(cb) for ct, cb in confirmed.values())
                tpd = n_trades / len(train_days) if train_days else 0.0
                if tpd < MIN_TRADES_PER_DAY:
                    continue
                full_combo = combo + (neck_buf, confirm_within)
                for stop_mult, target_r in itertools.product(STOP_MULTS, TARGET_RS):
                    pnl = []
                    for d, (ct, cb) in confirmed.items():
                        O, H, L, C = bars_by_spec[(bar_type, interval)][d]
                        nbars = len(O)
                        for cbar, neck, inv in ct:
                            p, _ = exit_bar_level_rr(cbar, neck, inv, True, H, L, C, nbars, stop_mult, target_r)
                            pnl.append(p)
                        for cbar, neck, inv in cb:
                            p, _ = exit_bar_level_rr(cbar, neck, inv, False, H, L, C, nbars, stop_mult, target_r)
                            pnl.append(p)
                    net_ticks = sum(pnl)
                    candidates.append((full_combo, stop_mult, target_r, net_ticks, n_trades, tpd))

        if not candidates:
            fold_results.append(dict(bar_type=bar_type, interval=interval, train=train_label, test=test_label,
                                      status=f"no combo clears {MIN_TRADES_PER_DAY}/day on train"))
            continue

        best = max(candidates, key=lambda c: c[3])
        full_combo, stop_mult, target_r, train_net_ticks, train_trades, train_tpd = best
        swing, peak_tol, min_depth, min_bars, max_bars, neck_buf, confirm_within = full_combo

        oos_trades = exact_verify_rr(bar_type, interval, test_days, swing, peak_tol, min_depth,
                                      min_bars, max_bars, neck_buf, confirm_within, stop_mult, target_r)
        oos_stats = stats_for(oos_trades, test_days)
        fold_results.append(dict(
            bar_type=bar_type, interval=interval, train=train_label, test=test_label, status="ok",
            swing=swing, peak_tol=peak_tol, min_depth=min_depth, min_bars=min_bars, max_bars=max_bars,
            neck_buf=neck_buf, confirm_within=confirm_within, stop_mult=stop_mult, target_r=target_r,
            train_trades=train_trades, train_trades_per_day=round(train_tpd, 2),
            train_net_ticks=round(train_net_ticks, 1),
            **oos_stats,
        ))
        if oos_trades is not None and not oos_trades.empty:
            oos_trades = oos_trades.assign(bar_type=bar_type, interval=interval,
                                            train=train_label, test=test_label)
        fold_results[-1]["_trades_df"] = oos_trades
        print(f"  {label} fold train<={train_label} test={test_label}: "
              f"swing={swing} peak_tol={peak_tol} min_depth={min_depth} min_bars={min_bars} "
              f"max_bars={max_bars} neck_buf={neck_buf} confirm_within={confirm_within} "
              f"stop_mult={stop_mult} target_r={target_r} | train {train_trades}tr "
              f"({train_tpd:.2f}/day) -> OOS {oos_stats['trades']}tr ${oos_stats['total_usd_ES']:.0f}")

    return fold_results


def exact_verify_rr(bar_type, interval, days, swing, peak_tol, min_depth, min_bars, max_bars,
                     neck_buf, confirm_within, stop_mult, target_r):
    trades = []
    for d in days:
        df = tickdata.load_rth(d)
        prices = df["Price"].to_numpy(dtype=np.float64)
        times = df["DateTime"].to_numpy()
        built = build_bars_for(bar_type, interval, prices, times)
        if built is None:
            continue
        O, H, L, C, end_idx = built
        nbars = len(O)
        if nbars < 2 * swing + 2:
            continue

        highs, lows = [], []
        pending_top = pending_bottom = None
        tol = peak_tol * TICK_SIZE
        mindep = min_depth * TICK_SIZE
        buf = neck_buf * TICK_SIZE

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
            if current_bar < 2 * swing + 2:
                continue
            cand = current_bar - swing
            cand_high, cand_low = H[cand], L[cand]
            is_high = is_low = True
            for k in range(1, swing + 1):
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
                            if (peak_diff <= tol and valley_depth >= mindep
                                    and min_bars <= bars_between <= max_bars):
                                pending_top = dict(neckline=valley[0], invalidate=max(p1[0], p2[0]), form_bar=current_bar)
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
                            if (trough_diff <= tol and peak_height >= mindep
                                    and min_bars <= bars_between <= max_bars):
                                pending_bottom = dict(neckline=peak[0], invalidate=min(t1[0], t2[0]), form_bar=current_bar)

            if pending_top is not None:
                if H[i] > pending_top["invalidate"]:
                    pending_top = None
                elif current_bar - pending_top["form_bar"] > confirm_within:
                    pending_top = None
                elif C[i] < pending_top["neckline"] - buf:
                    trades.append(make_trade_rr("DT", True, pending_top, i, end_idx, prices, times,
                                                 stop_mult, target_r, d))
                    pending_top = None
            if pending_bottom is not None:
                if L[i] < pending_bottom["invalidate"]:
                    pending_bottom = None
                elif current_bar - pending_bottom["form_bar"] > confirm_within:
                    pending_bottom = None
                elif C[i] > pending_bottom["neckline"] + buf:
                    trades.append(make_trade_rr("DB", False, pending_bottom, i, end_idx, prices, times,
                                                 stop_mult, target_r, d))
                    pending_bottom = None

    return pd.DataFrame(trades)


def make_trade_rr(kind, is_top, pending, confirm_bar_i, end_idx, prices, times, stop_mult, target_r, day):
    neckline, invalidate = pending["neckline"], pending["invalidate"]
    direction_short = is_top
    entry_tick_idx = end_idx[confirm_bar_i]
    raw_entry = prices[entry_tick_idx]
    base_risk = abs(raw_entry - invalidate)
    risk = base_risk * stop_mult
    stop_level = (raw_entry + risk) if direction_short else (raw_entry - risk)
    target_level = (raw_entry - risk * target_r) if direction_short else (raw_entry + risk * target_r)
    entry_price = raw_entry - TICK_SIZE if direction_short else raw_entry + TICK_SIZE
    risk_ticks = risk / TICK_SIZE

    path = prices[entry_tick_idx + 1:]
    path_times = times[entry_tick_idx + 1:]

    if len(path) == 0:
        exit_price, exit_reason, exit_time = raw_entry, "EOD flat (no ticks left)", times[entry_tick_idx]
    else:
        if direction_short:
            stop_hit = np.flatnonzero(path >= stop_level)
            tgt_hit = np.flatnonzero(path <= target_level)
        else:
            stop_hit = np.flatnonzero(path <= stop_level)
            tgt_hit = np.flatnonzero(path >= target_level)
        si = stop_hit[0] if len(stop_hit) else None
        ti = tgt_hit[0] if len(tgt_hit) else None
        if si is not None and (ti is None or si <= ti):
            exit_price = (stop_level + TICK_SIZE) if direction_short else (stop_level - TICK_SIZE)
            exit_reason, exit_time = "stop", path_times[si]
        elif ti is not None:
            exit_price, exit_reason, exit_time = target_level, "target", path_times[ti]
        else:
            exit_price = (path[-1] + TICK_SIZE) if direction_short else (path[-1] - TICK_SIZE)
            exit_reason, exit_time = "EOD flat", path_times[-1]

    pnl_ticks = ((entry_price - exit_price) if direction_short else (exit_price - entry_price)) / TICK_SIZE
    return dict(kind=kind, direction="short" if direction_short else "long", day=day,
                entry_time=times[entry_tick_idx], entry_price=entry_price,
                stop_level=stop_level, target_level=target_level, risk_ticks=round(risk_ticks, 2),
                exit_time=exit_time, exit_price=exit_price, exit_reason=exit_reason,
                pnl_ticks=round(pnl_ticks, 2),
                r_multiple=round(pnl_ticks / risk_ticks, 3) if risk_ticks > 0 else np.nan)


def stats_for(df, days):
    n_days = len(days) if days else 0
    if df is None or df.empty:
        return dict(trades=0, trades_per_day=0.0, win_rate=np.nan, avg_r=np.nan, profit_factor=np.nan,
                    total_ticks=0.0, total_usd_ES=0.0, max_dd_ticks=0.0)
    wins = df[df["pnl_ticks"] > 0]
    losses = df[df["pnl_ticks"] <= 0]
    gw, gl = wins["pnl_ticks"].sum(), -losses["pnl_ticks"].sum()
    pf = gw / gl if gl > 0 else np.inf
    cum = df.sort_values("entry_time")["pnl_ticks"].cumsum()
    maxdd = (cum - cum.cummax()).min() if len(cum) else 0.0
    return dict(
        trades=len(df), trades_per_day=round(len(df) / n_days, 2) if n_days else 0.0,
        win_rate=round(100 * len(wins) / len(df), 1), avg_r=round(df["r_multiple"].mean(), 3),
        profit_factor=round(pf, 2) if np.isfinite(pf) else float("inf"),
        total_ticks=round(df["pnl_ticks"].sum(), 1), total_usd_ES=round(df["pnl_ticks"].sum() * ES_PER_TICK, 0),
        max_dd_ticks=round(maxdd, 1),
    )


if __name__ == "__main__":
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    out_dir = Path(__file__).resolve().parent.parent / "data" / "dtdb_backtest"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_days = tickdata.available("rth")
    print(f"Full RTH trove: {all_days[0]} -> {all_days[-1]}  ({len(all_days)} days)")

    folds = make_folds(all_days)
    for trl, tel, trd, ted in folds:
        print(f"  fold: train<={trl} ({len(trd)}d)  ->  test={tel} ({len(ted)}d)")

    print("Self-check (fast engine vs committed exact-engine, default params) ...")
    _check_days = all_days[-90:]
    _check_cache = {}
    for d in _check_days:
        _df = tickdata.load_rth(d)
        _check_cache[d] = (_df["Price"].to_numpy(dtype=np.float64), _df["DateTime"].to_numpy())
    self_check(_check_days, _check_cache)

    print("Building bars for all days x all bar types (single pass over raw ticks) ...")
    bars_by_spec = {spec: {} for spec in BAR_TYPES}
    for i, d in enumerate(all_days):
        df = tickdata.load_rth(d)
        prices = df["Price"].to_numpy(dtype=np.float64)
        times = df["DateTime"].to_numpy()
        day_bars = build_all_bars_for_day(prices, times)
        for spec, built in day_bars.items():
            bars_by_spec[spec][d] = built
        if (i + 1) % 200 == 0:
            print(f"  bars built: {i+1}/{len(all_days)} days")
    print("bars built for all days.")

    all_fold_rows = []
    all_trade_frames = []
    for bar_type, interval in BAR_TYPES:
        label = f"{interval}t" if bar_type == "tick" else f"{interval}min"
        print(f"walk-forward {label} ...")
        results = run_bar_type(bar_type, interval, all_days, folds, bars_by_spec)
        for r in results:
            tdf = r.pop("_trades_df", None)
            all_fold_rows.append(r)
            if tdf is not None and not tdf.empty:
                all_trade_frames.append(tdf)

    folds_df = pd.DataFrame(all_fold_rows)
    folds_path = out_dir / f"wf_folds_{today}.csv"
    folds_df.to_csv(folds_path, index=False)
    print(f"folds -> {folds_path}")

    if all_trade_frames:
        trades_df = pd.concat(all_trade_frames, ignore_index=True)
        trades_path = out_dir / f"wf_trades_{today}.csv"
        trades_df.to_csv(trades_path, index=False)
        print(f"trades -> {trades_path} ({len(trades_df)} rows)")

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 40)
    print(folds_df.to_string(index=False))
