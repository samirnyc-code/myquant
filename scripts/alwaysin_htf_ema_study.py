"""alwaysin_htf_ema_study.py — base-rate study for AlwaysInHtfEma flips.

Offline replication of nt8/indicators/AlwaysInHtfEma.cs against the canonical
RTH tick trove (tickdata.py). Step 1 of the new "flip + first pullback"
setup (user request, 2026-10-24): count flips, describe the bar that creates
them, and describe what the first pullback actually looks like. NO entry,
NO stop/target, NO filters, NO P&L — pure frequency + shape, by design.

INDICATOR LOGIC REPLICATED (from the recovered live .cs, its own defaults):
  - Primary series = 2000-tick bars (confirmed live chart setting, 2026-10-24)
  - Secondary series = 5-minute bars, same instrument
  - EMA(20) on the 2000t series' Close
  - ABR(8) = SMA(Range, 8) on the 2000t series (Range = High - Low per bar)
  - State flips LONG(+1) / SHORT(-1) on whichever fires first:
      (a) 2 consecutive 5-min closes above/below the tick EMA, or
      (b) "strong breakout": |5-min body| > 3.0 x tick-ABR, closing beyond
          both the 5-min bar's own open AND the tick EMA, or
      (c) opening-gap special case: overnight gap > 3.0 x tick-ABR, gap
          direction + close-vs-EMA agree -> immediate flip
  - State starts neutral (0) and then CARRIES FORWARD once established —
    matches the live indicator, which does not reset daily.

KNOWN SIMPLIFICATIONS — documented, NOT verified byte-identical to NT8:
  1. RTH-only ticks (canonical trove) -> tick bars are built fresh each
     session (reset at 08:30) rather than truly continuous across the
     overnight gap the way a live 2000t chart accumulates ticks. EMA/ABR
     VALUES still carry across the reset (seeded from the prior day's last
     value) so the lines themselves stay continuous; only the bar-count
     accumulation resets. The overnight-gap special case uses that carried
     EMA/ABR against today's first-bar gap — approximates intent, is not a
     literal port of NT8's IsFirstBarOfSessionByIndex bar handling.
  2. Each day's final (necessarily < 2000-tick) partial bar is dropped —
     it never actually closes within that session in this offline model.
  3. EMA uses pandas ewm(adjust=False) recursion, not NT8's SMA-seeded
     warmup — converges to the same value within a few bars, differs only
     early in the very first window.
  4. "First pullback" is a first-pass DESCRIPTIVE definition (see
     find_pullback()), not a trading rule: a pullback starts once price
     retraces >= 0.5x the current tick-ABR away from the post-flip extreme;
     it "ends" when price either resumes beyond that extreme (thrust
     continues) or the next flip occurs. The 0.5x threshold is reported
     here, not hidden — changing it changes every pullback stat below.
  Treat every number here as "not verified live-identical" per CLAUDE.md —
  this is a frequency/shape study, not a backtest, not a filter yet.

Usage:
    python scripts/alwaysin_htf_ema_study.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Output:
    data/alwaysin_htf_ema/_analysis/alwaysin_flips_<stamp>.csv   (one row per flip,
    flip metrics + first-pullback descriptive metrics)
    Printed summary (safe to paste back into chat per "present results inline").
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tickdata  # noqa: E402
OUT_DIR = ROOT / "data" / "alwaysin_htf_ema" / "_analysis"

EMA_PERIOD = 20
ABR_PERIOD = 8
CONSECUTIVE_CLOSES = 2
STRONG_BODY_MULT = 3.0
TICKS_PER_BAR = 2000
PULLBACK_RETRACE_ABR = 0.5  # first-pass threshold, see module docstring §4


def _safe_div(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return np.nan
    return a / b if b and not np.isnan(b) else np.nan


def build_tick_bars(day_df: pd.DataFrame, n: int = TICKS_PER_BAR) -> pd.DataFrame:
    df = day_df.reset_index(drop=True)
    df = df.assign(bar_idx=np.arange(len(df)) // n)
    full_bars = df.groupby("bar_idx").filter(lambda g: len(g) == n)
    bars = full_bars.groupby("bar_idx").agg(
        open=("Price", "first"), high=("Price", "max"), low=("Price", "min"),
        close=("Price", "last"), volume=("Volume", "sum"),
        start_time=("DateTime", "first"), end_time=("DateTime", "last"),
    ).reset_index(drop=True)
    bars["range"] = bars["high"] - bars["low"]
    return bars


def build_5min_bars(day_df: pd.DataFrame, session_date: str) -> pd.DataFrame:
    s = day_df.set_index("DateTime")
    origin = pd.Timestamp(f"{session_date} 08:30:00")
    g = s.groupby(pd.Grouper(freq="5min", origin=origin))
    bars = g["Price"].agg(open="first", high="max", low="min", close="last").dropna()
    bars = bars.reset_index().rename(columns={"DateTime": "bin_start"})
    bars["close_time"] = bars["bin_start"] + pd.Timedelta(minutes=5)
    rng = (bars["high"] - bars["low"]).replace(0, np.nan)
    bars["ibs"] = (bars["close"] - bars["low"]) / rng
    return bars


def add_ema_abr(tick_bars: pd.DataFrame, carried_ema, carried_hist: list[float]):
    tb = tick_bars.copy()
    closes, ranges = tb["close"].to_numpy(), tb["range"].to_numpy()
    alpha = 2.0 / (EMA_PERIOD + 1)

    ema = np.empty(len(tb))
    prev = carried_ema
    for i, c in enumerate(closes):
        prev = c if prev is None else (c - prev) * alpha + prev
        ema[i] = prev
    tb["ema"] = ema

    hist = list(carried_hist)
    abr = np.empty(len(tb))
    for i, r in enumerate(ranges):
        hist.append(r)
        if len(hist) > ABR_PERIOD:
            hist.pop(0)
        abr[i] = np.mean(hist)
    tb["abr"] = abr

    return tb, float(ema[-1]) if len(ema) else carried_ema, hist[-ABR_PERIOD:]


def find_pullback(tick_bars_global: pd.DataFrame, start_pos: int, end_pos: int, direction: int) -> dict:
    sub = tick_bars_global.iloc[start_pos:end_pos].reset_index(drop=True)
    if len(sub) < 2:
        return {"pullback_found": False}

    flip_price = sub["close"].iloc[0]
    extreme, extreme_pos = flip_price, 0
    pullback_start_pos = None

    for i in range(1, len(sub)):
        c, abr_i = sub["close"].iloc[i], sub["abr"].iloc[i]
        if direction == 1 and c > extreme:
            extreme, extreme_pos = c, i
        elif direction == -1 and c < extreme:
            extreme, extreme_pos = c, i
        retrace = (extreme - c) if direction == 1 else (c - extreme)
        if abr_i > 0 and retrace >= PULLBACK_RETRACE_ABR * abr_i and i > extreme_pos:
            pullback_start_pos = i
            break

    thrust_abr = _safe_div(abs(extreme - flip_price), sub["abr"].iloc[extreme_pos])
    if pullback_start_pos is None:
        return {"pullback_found": False, "bars_to_extreme": extreme_pos, "thrust_distance_abr": thrust_abr}

    max_retrace, deepest_pos, pullback_end_pos, touched_ema = -np.inf, pullback_start_pos, None, False
    for i in range(pullback_start_pos, len(sub)):
        c, lo, hi, ema_i = sub["close"].iloc[i], sub["low"].iloc[i], sub["high"].iloc[i], sub["ema"].iloc[i]
        retrace = (extreme - c) if direction == 1 else (c - extreme)
        if retrace > max_retrace:
            max_retrace, deepest_pos = retrace, i
        if (direction == 1 and lo <= ema_i) or (direction == -1 and hi >= ema_i):
            touched_ema = True
        if (direction == 1 and c > extreme) or (direction == -1 and c < extreme):
            pullback_end_pos = i
            break

    deepest = sub.iloc[deepest_pos]
    deepest_range = deepest["high"] - deepest["low"]
    raw_ibs = (deepest["close"] - deepest["low"]) / deepest_range if deepest_range > 0 else np.nan
    deepest_ibs_signed = raw_ibs if direction == 1 else (1 - raw_ibs if not np.isnan(raw_ibs) else np.nan)

    return {
        "pullback_found": True,
        "bars_to_extreme": extreme_pos,
        "thrust_distance_abr": thrust_abr,
        "bars_extreme_to_pullback_start": pullback_start_pos - extreme_pos,
        "max_pullback_depth_abr": _safe_div(max_retrace, sub["abr"].iloc[deepest_pos]),
        "pullback_touched_ema": touched_ema,
        "pullback_resumed_before_next_flip": pullback_end_pos is not None,
        "deepest_bar_ibs_signed": deepest_ibs_signed,
        "deepest_bar_range_abr": _safe_div(deepest_range, sub["abr"].iloc[deepest_pos]),
    }


def run(start: str, end: str):
    days = [d for d in tickdata.available("rth") if start <= d <= end]
    print(f"Loading {len(days)} RTH days: {days[0]} .. {days[-1]}")

    per_day_tick_bars, per_day_five = [], []
    carried_ema, carried_hist, prev_day_last_close = None, [], None
    global_offset = 0

    for di, day in enumerate(days):
        day_df = tickdata.load_rth(day)
        tb = build_tick_bars(day_df)
        if tb.empty:
            per_day_five.append((day, pd.DataFrame(), pd.DataFrame(), prev_day_last_close))
            continue
        tb, carried_ema, carried_hist = add_ema_abr(tb, carried_ema, carried_hist)
        tb["day"] = day
        tb["global_pos"] = np.arange(global_offset, global_offset + len(tb))
        global_offset += len(tb)
        per_day_tick_bars.append(tb)

        eligible = tb[tb.index >= max(EMA_PERIOD, ABR_PERIOD)]
        five = build_5min_bars(day_df, day)
        if not eligible.empty:
            five = pd.merge_asof(
                five.sort_values("close_time"),
                eligible[["end_time", "ema", "abr", "close", "global_pos"]]
                    .rename(columns={"close": "tick_close"}).sort_values("end_time"),
                left_on="close_time", right_on="end_time", direction="backward",
            ).dropna(subset=["ema", "abr"])
        per_day_five.append((day, eligible, five, prev_day_last_close))
        prev_day_last_close = tb["close"].iloc[-1]

        if (di + 1) % 200 == 0:
            print(f"  loaded {di + 1}/{len(days)} days...")

    tick_bars_global = pd.concat(per_day_tick_bars, ignore_index=True) if per_day_tick_bars else pd.DataFrame()
    print(f"Total 2000t bars across history: {len(tick_bars_global)}")

    flips, ai_state, above, below = [], 0, 0, 0
    for day, eligible, five, prev_close in per_day_five:
        if prev_close is not None and not eligible.empty:
            fb = eligible.iloc[0]
            gap = fb["open"] - prev_close
            threshold = STRONG_BODY_MULT * fb["abr"]
            new_dir = None
            if threshold > 0 and abs(gap) > threshold:
                if gap > 0 and fb["close"] > fb["ema"]:
                    new_dir = 1
                elif gap < 0 and fb["close"] < fb["ema"]:
                    new_dir = -1
            if new_dir is not None and new_dir != ai_state:
                ai_state, above, below = new_dir, 0, 0
                flips.append({
                    "date": day, "flip_time": fb["end_time"], "direction": new_dir, "mechanism": "gap",
                    "ema_at_flip": fb["ema"], "abr_at_flip": fb["abr"], "tick_close_at_flip": fb["close"],
                    "dist_beyond_ema_abr": _safe_div(abs(fb["close"] - fb["ema"]), fb["abr"]),
                    "htf_body": np.nan, "htf_range": np.nan, "htf_ibs_signed": np.nan,
                    "tod_minute_of_day": 0, "session_frac": 0.0,
                    "tick_bar_pos": int(fb["global_pos"]),
                })

        for _, row in five.iterrows():
            htf_close, htf_open, ema_v, abr_v, tick_close = row["close"], row["open"], row["ema"], row["abr"], row["tick_close"]

            if htf_close > ema_v:
                above, below = above + 1, 0
            elif htf_close < ema_v:
                above, below = 0, below + 1
            else:
                above = below = 0

            body = abs(htf_close - htf_open)
            threshold = STRONG_BODY_MULT * abr_v
            strong_bull = strong_bear = False
            if threshold > 0 and body > threshold:
                strong_bull = htf_close > htf_open and htf_close > ema_v
                strong_bear = htf_close < htf_open and htf_close < ema_v

            new_state, mechanism = ai_state, None
            if strong_bull or above >= CONSECUTIVE_CLOSES:
                new_state, mechanism = 1, ("strong_breakout" if strong_bull else "consecutive_close")
            elif strong_bear or below >= CONSECUTIVE_CLOSES:
                new_state, mechanism = -1, ("strong_breakout" if strong_bear else "consecutive_close")

            if new_state != ai_state and mechanism is not None:
                ai_state = new_state
                tod_min = row["close_time"].hour * 60 + row["close_time"].minute - 8 * 60 - 30
                flips.append({
                    "date": day, "flip_time": row["close_time"], "direction": new_state, "mechanism": mechanism,
                    "ema_at_flip": ema_v, "abr_at_flip": abr_v, "tick_close_at_flip": tick_close,
                    "dist_beyond_ema_abr": _safe_div(abs(tick_close - ema_v), abr_v),
                    "htf_body": body, "htf_range": row["high"] - row["low"],
                    "htf_ibs_signed": row["ibs"] if new_state == 1 else (1 - row["ibs"] if not pd.isna(row["ibs"]) else np.nan),
                    "tod_minute_of_day": tod_min, "session_frac": tod_min / (6 * 60 + 45) if tod_min else 0.0,
                    "tick_bar_pos": int(row["global_pos"]),
                })

    flips_df = pd.DataFrame(flips).reset_index(drop=True)
    print(f"Total flips found: {len(flips_df)}")
    if flips_df.empty:
        return flips_df

    pullback_rows = []
    for i in range(len(flips_df)):
        start_pos = int(flips_df.loc[i, "tick_bar_pos"])
        end_pos = int(flips_df.loc[i + 1, "tick_bar_pos"]) if i + 1 < len(flips_df) else len(tick_bars_global)
        pullback_rows.append(find_pullback(tick_bars_global, start_pos, end_pos, int(flips_df.loc[i, "direction"])))

    return pd.concat([flips_df, pd.DataFrame(pullback_rows)], axis=1)


def main():
    all_days = tickdata.available("rth")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=all_days[0])
    ap.add_argument("--end", default=all_days[-1])
    args = ap.parse_args()

    result = run(args.start, args.end)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"alwaysin_flips_{stamp}.csv"
    result.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")

    if result.empty:
        return

    n_days = result["date"].nunique()
    print("\n=== SUMMARY ===")
    print(f"Days covered: {n_days}  |  Total flips: {len(result)}  |  Flips/day: {len(result) / n_days:.2f}")
    print("\nMechanism counts:")
    print(result["mechanism"].value_counts())
    print("\ndist_beyond_ema_abr (how far close sat beyond EMA, in ABR units):")
    print(result["dist_beyond_ema_abr"].describe())
    print("\nhtf_ibs_signed (flip-direction IBS of the 5-min flip bar):")
    print(result["htf_ibs_signed"].describe())
    print("\ntod_minute_of_day (minutes since 08:30 open):")
    print(result["tod_minute_of_day"].describe())
    print("\npullback_found (did a qualifying pullback occur before the next flip):")
    print(result["pullback_found"].value_counts(normalize=True))
    pf = result[result["pullback_found"]]
    print("\n--- for flips WITH a qualifying pullback ---")
    print("bars_to_extreme:\n", pf["bars_to_extreme"].describe())
    print("thrust_distance_abr:\n", pf["thrust_distance_abr"].describe())
    print("bars_extreme_to_pullback_start:\n", pf["bars_extreme_to_pullback_start"].describe())
    print("max_pullback_depth_abr:\n", pf["max_pullback_depth_abr"].describe())
    print("pullback_touched_ema:\n", pf["pullback_touched_ema"].value_counts(normalize=True))
    print("deepest_bar_ibs_signed:\n", pf["deepest_bar_ibs_signed"].describe())
    print("deepest_bar_range_abr:\n", pf["deepest_bar_range_abr"].describe())


if __name__ == "__main__":
    main()
