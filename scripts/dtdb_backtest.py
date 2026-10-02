"""dtdb_backtest.py — backtest of nt8/indicators/DtDbScanner.cs: trade every neckline break.

Ports the DT/DB detection + confirmation logic from DtDbScanner.cs 1:1 (same swing-pivot
algorithm, same scoring, same confirm/invalidate/expire rules) and simulates a trade on
every neckline CONFIRM (no score filter, matching the live code's confirm alert which is
unconditional). Entry/exit are NOT part of the indicator (execution is manual by design),
so this script adds the only entry/exit rule the indicator itself implies:

  Direction:  DT confirm -> short.  DB confirm -> long.
  Entry:      confirm bar's close, 1 tick adverse slippage.
  Stop:       the indicator's own InvalidateBeyond level (the setup's own invalidation price).
  Target:     classic measured move — neckline +/- (InvalidateBeyond - neckline).
  Exit mgmt:  walked tick-by-tick (not bar-by-bar) off the canonical RTH tick trove for an
              exact first-touch fill, stop priority on same-tick gap-through-both, flat at
              session close (15:15 CT) if neither level is hit. Target fills at the limit
              price (no slippage); stop/EOD-flat fills get 1 tick adverse slippage.

Data: tickdata.py RTH_TROVE only (hard rule — no other tick source). Each trading day is
simulated independently (bars/pivots/pending reset daily) — ES RTH tick bars from this
trove do not span the overnight gap, so this avoids any cross-session bar artifact. This
is a stated assumption, not a property of the live indicator (which would carry state
across days on a continuously-loaded NT8 chart).

Usage: python scripts/dtdb_backtest.py
Output: data/dtdb_backtest/trades_<date>.csv, data/dtdb_backtest/summary_<date>.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tickdata  # noqa: E402

TICK_SIZE = 0.25
ES_PER_TICK = 12.50
MES_PER_TICK = 1.25
MES_RT_COMMISSION = 5.00  # user's real prop account terms

TICK_INTERVALS = [1500, 2000, 2500, 5000]
LOOKBACK_DAYS = 90

# --- DtDbScanner.cs default parameters (unchanged) --------------------------
SWING_STRENGTH = 4
PEAK_TOL_TICKS = 6
MIN_VALLEY_DEPTH_TICKS = 10
MIN_BARS_BETWEEN = 6
MAX_BARS_BETWEEN = 120
NECKLINE_BUFFER_TICKS = 2
CONFIRM_WITHIN_BARS = 150
MIN_SCORE_TO_ALERT = 50  # only gates the *forming* alert in the live code; confirm is unconditional


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def clamp01(v):
    return clamp(v, 0.0, 1.0)


def band(x, zero_lo, full_lo, full_hi, zero_hi):
    if x <= zero_lo or x >= zero_hi:
        return 0.0
    if x < full_lo:
        return (x - zero_lo) / (full_lo - zero_lo)
    if x > full_hi:
        return (zero_hi - x) / (zero_hi - full_hi)
    return 1.0


def build_bars(prices: np.ndarray, n: int):
    """Group raw ticks into closed N-tick bars. O/H/L/C + index of each bar's last tick."""
    nbars = len(prices) // n
    if nbars == 0:
        return None
    O = np.empty(nbars); H = np.empty(nbars); L = np.empty(nbars); C = np.empty(nbars)
    end_idx = np.empty(nbars, dtype=np.int64)
    for i in range(nbars):
        s, e = i * n, (i + 1) * n
        seg = prices[s:e]
        O[i] = seg[0]; H[i] = seg.max(); L[i] = seg.min(); C[i] = seg[-1]
        end_idx[i] = e - 1
    return O, H, L, C, end_idx


def simulate_day(prices: np.ndarray, times: np.ndarray, n: int):
    """Returns list of trade dicts for one trading day at tick-interval n."""
    built = build_bars(prices, n)
    if built is None:
        return []
    O, H, L, C, end_idx = built
    nbars = len(O)
    if nbars < 2 * SWING_STRENGTH + 2:
        return []

    # True Range + 14-bar SMA ATR (NT8 default ATR = SMA of TR, not Wilder)
    TR = np.empty(nbars)
    TR[0] = H[0] - L[0]
    for i in range(1, nbars):
        TR[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    atr_sma = pd.Series(TR).rolling(14).mean().to_numpy()

    highs: list[tuple[float, int]] = []  # (price, bar_idx)
    lows: list[tuple[float, int]] = []
    pending_top = None   # dict: neckline, invalidate, form_bar, score
    pending_bottom = None
    trades = []

    def lowest_low_between(bar_a, bar_b):
        best = None
        for p, b in lows:
            if bar_a < b < bar_b and (best is None or p < best[0]):
                best = (p, b)
        return best

    def highest_high_between(bar_a, bar_b):
        best = None
        for p, b in highs:
            if bar_a < b < bar_b and (best is None or p > best[0]):
                best = (p, b)
        return best

    def last_pivot_before(lst, bar):
        best = None
        for p, b in lst:
            if b < bar and (best is None or b > best[1]):
                best = (p, b)
        return best

    tol = PEAK_TOL_TICKS * TICK_SIZE
    min_depth = MIN_VALLEY_DEPTH_TICKS * TICK_SIZE
    buf = NECKLINE_BUFFER_TICKS * TICK_SIZE

    for i in range(nbars):
        current_bar = i
        if current_bar < 2 * SWING_STRENGTH + 2:
            continue

        atr = atr_sma[i] if current_bar > 14 and not np.isnan(atr_sma[i]) else TICK_SIZE * 20
        if atr <= 0:
            atr = TICK_SIZE * 20

        offset = SWING_STRENGTH
        cand = current_bar - offset
        cand_high, cand_low = H[cand], L[cand]
        is_high = is_low = True
        for k in range(1, SWING_STRENGTH + 1):
            jf, jb = cand + k, cand - k
            if H[jf] >= cand_high or H[jb] >= cand_high:
                is_high = False
            if L[jf] <= cand_low or L[jb] <= cand_low:
                is_low = False
        abs_bar = cand

        if is_high:
            if not highs or highs[-1][1] != abs_bar:
                highs.append((cand_high, abs_bar))
                if len(highs) > 50:
                    highs.pop(0)
                if len(highs) >= 2:
                    p1, p2 = highs[-2], highs[-1]
                    valley = lowest_low_between(p1[1], p2[1])
                    if valley is not None:
                        peak_diff = abs(p1[0] - p2[0])
                        valley_depth = min(p1[0], p2[0]) - valley[0]
                        bars_between = p2[1] - p1[1]
                        if (peak_diff <= tol and valley_depth >= min_depth
                                and MIN_BARS_BETWEEN <= bars_between <= MAX_BARS_BETWEEN):
                            symmetry = clamp01(1.0 - peak_diff / tol)
                            depth_score = band(valley_depth / atr, 0.3, 1.5, 3.0, 6.0)
                            leg1, leg2 = valley[1] - p1[1], p2[1] - valley[1]
                            time_sym = clamp01(1.0 - abs(leg1 - leg2) / max(1, bars_between))
                            prior_low = last_pivot_before(lows, p1[1])
                            trend = 0.5 if prior_low is None else clamp01((p1[0] - prior_low[0]) / (atr * 3.0))
                            score = clamp(100.0 * (0.35 * symmetry + 0.25 * depth_score
                                                    + 0.15 * time_sym + 0.25 * trend), 0, 100)
                            pending_top = dict(neckline=valley[0], invalidate=max(p1[0], p2[0]),
                                                form_bar=current_bar, score=score)
        if is_low:
            if not lows or lows[-1][1] != abs_bar:
                lows.append((cand_low, abs_bar))
                if len(lows) > 50:
                    lows.pop(0)
                if len(lows) >= 2:
                    t1, t2 = lows[-2], lows[-1]
                    peak = highest_high_between(t1[1], t2[1])
                    if peak is not None:
                        trough_diff = abs(t1[0] - t2[0])
                        peak_height = peak[0] - max(t1[0], t2[0])
                        bars_between = t2[1] - t1[1]
                        if (trough_diff <= tol and peak_height >= min_depth
                                and MIN_BARS_BETWEEN <= bars_between <= MAX_BARS_BETWEEN):
                            symmetry = clamp01(1.0 - trough_diff / tol)
                            depth_score = band(peak_height / atr, 0.3, 1.5, 3.0, 6.0)
                            leg1, leg2 = peak[1] - t1[1], t2[1] - peak[1]
                            time_sym = clamp01(1.0 - abs(leg1 - leg2) / max(1, bars_between))
                            prior_high = last_pivot_before(highs, t1[1])
                            trend = 0.5 if prior_high is None else clamp01((prior_high[0] - t1[0]) / (atr * 3.0))
                            score = clamp(100.0 * (0.35 * symmetry + 0.25 * depth_score
                                                    + 0.15 * time_sym + 0.25 * trend), 0, 100)
                            pending_bottom = dict(neckline=peak[0], invalidate=min(t1[0], t2[0]),
                                                   form_bar=current_bar, score=score)

        # --- ManagePending (same bar) ---
        if pending_top is not None:
            if H[i] > pending_top["invalidate"]:
                pending_top = None
            elif current_bar - pending_top["form_bar"] > CONFIRM_WITHIN_BARS:
                pending_top = None
            elif C[i] < pending_top["neckline"] - buf:
                trades.append(make_trade("DT", "short", pending_top, i, end_idx, prices, times))
                pending_top = None

        if pending_bottom is not None:
            if L[i] < pending_bottom["invalidate"]:
                pending_bottom = None
            elif current_bar - pending_bottom["form_bar"] > CONFIRM_WITHIN_BARS:
                pending_bottom = None
            elif C[i] > pending_bottom["neckline"] + buf:
                trades.append(make_trade("DB", "long", pending_bottom, i, end_idx, prices, times))
                pending_bottom = None

    return trades


def make_trade(kind, direction, pending, confirm_bar_i, end_idx, prices, times):
    neckline = pending["neckline"]
    invalidate = pending["invalidate"]
    height = (invalidate - neckline) if direction == "short" else (neckline - invalidate)
    target_level = (neckline - height) if direction == "short" else (neckline + height)
    stop_level = invalidate

    entry_tick_idx = end_idx[confirm_bar_i]
    raw_entry = prices[entry_tick_idx]
    entry_price = raw_entry - TICK_SIZE if direction == "short" else raw_entry + TICK_SIZE
    risk_ticks = abs(raw_entry - stop_level) / TICK_SIZE

    path = prices[entry_tick_idx + 1:]
    path_times = times[entry_tick_idx + 1:]
    exit_price, exit_reason, exit_time = None, None, None

    if len(path) == 0:
        exit_price = raw_entry
        exit_reason = "EOD flat (no ticks left)"
        exit_time = times[entry_tick_idx]
    else:
        if direction == "short":
            stop_hit = np.flatnonzero(path >= stop_level)
            tgt_hit = np.flatnonzero(path <= target_level)
        else:
            stop_hit = np.flatnonzero(path <= stop_level)
            tgt_hit = np.flatnonzero(path >= target_level)

        si = stop_hit[0] if len(stop_hit) else None
        ti = tgt_hit[0] if len(tgt_hit) else None

        if si is not None and (ti is None or si <= ti):
            # stop first, or same-tick gap through both -> stop wins (conservative)
            exit_price = (stop_level + TICK_SIZE) if direction == "short" else (stop_level - TICK_SIZE)
            exit_reason = "stop"
            exit_time = path_times[si]
        elif ti is not None:
            exit_price = target_level
            exit_reason = "target"
            exit_time = path_times[ti]
        else:
            exit_price = (path[-1] + TICK_SIZE) if direction == "short" else (path[-1] - TICK_SIZE)
            exit_reason = "EOD flat"
            exit_time = path_times[-1]

    pnl_ticks = ((entry_price - exit_price) if direction == "short" else (exit_price - entry_price)) / TICK_SIZE

    return dict(
        kind=kind, direction=direction, score=round(pending["score"], 1),
        entry_time=times[entry_tick_idx], entry_price=entry_price,
        stop_level=stop_level, target_level=target_level, risk_ticks=round(risk_ticks, 2),
        exit_time=exit_time, exit_price=exit_price, exit_reason=exit_reason,
        pnl_ticks=round(pnl_ticks, 2),
        r_multiple=round(pnl_ticks / risk_ticks, 3) if risk_ticks > 0 else np.nan,
    )


def run():
    days = tickdata.available("rth")[-LOOKBACK_DAYS:]
    print(f"Period: {days[0]} -> {days[-1]}  ({len(days)} RTH trading days)")

    day_cache = {}
    for d in days:
        df = tickdata.load_rth(d)
        day_cache[d] = (df["Price"].to_numpy(dtype=np.float64), df["DateTime"].to_numpy())

    all_trades = []
    for n in TICK_INTERVALS:
        print(f"  simulating {n}t ...")
        for d in days:
            prices, times = day_cache[d]
            for t in simulate_day(prices, times, n):
                t["interval"] = n
                t["day"] = d
                all_trades.append(t)

    trades_df = pd.DataFrame(all_trades)
    return days, trades_df


def summarize(trades_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for n in TICK_INTERVALS:
        for kind in ["ALL", "DT", "DB"]:
            for qual in ["all", "score>=50"]:
                sub = trades_df[trades_df["interval"] == n]
                if kind != "ALL":
                    sub = sub[sub["kind"] == kind]
                if qual == "score>=50":
                    sub = sub[sub["score"] >= MIN_SCORE_TO_ALERT]
                if sub.empty:
                    rows.append(dict(interval=n, setup=kind, quality=qual, trades=0))
                    continue
                wins = sub[sub["pnl_ticks"] > 0]
                losses = sub[sub["pnl_ticks"] <= 0]
                gross_win_ticks = wins["pnl_ticks"].sum()
                gross_loss_ticks = -losses["pnl_ticks"].sum()
                pf = (gross_win_ticks / gross_loss_ticks) if gross_loss_ticks > 0 else np.inf
                cum = sub.sort_values("entry_time")["pnl_ticks"].cumsum()
                maxdd_ticks = (cum - cum.cummax()).min() if len(cum) else 0.0
                net_mes = sub["pnl_ticks"].sum() * MES_PER_TICK - len(sub) * MES_RT_COMMISSION
                rows.append(dict(
                    interval=n, setup=kind, quality=qual, trades=len(sub),
                    win_rate=round(100 * len(wins) / len(sub), 1),
                    avg_r=round(sub["r_multiple"].mean(), 3),
                    profit_factor=round(pf, 2) if np.isfinite(pf) else "inf",
                    total_ticks=round(sub["pnl_ticks"].sum(), 1),
                    total_usd_ES=round(sub["pnl_ticks"].sum() * ES_PER_TICK, 0),
                    total_usd_MES_net_comm=round(net_mes, 0),
                    max_dd_ticks=round(maxdd_ticks, 1),
                ))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    out_dir = Path(__file__).resolve().parent.parent / "data" / "dtdb_backtest"
    out_dir.mkdir(parents=True, exist_ok=True)

    days, trades_df = run()
    trades_path = out_dir / f"trades_{today}.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"trades -> {trades_path}  ({len(trades_df)} rows)")

    summary_df = summarize(trades_df)
    summary_path = out_dir / f"summary_{today}.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"summary -> {summary_path}")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(summary_df.to_string(index=False))
