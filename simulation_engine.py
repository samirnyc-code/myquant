import numpy as np
import pandas as pd

from data_loader import TICK_SIZE, bar_num_from_dt, RTH_START_MIN

INSTRUMENTS = {
    "ES":  {"tick_value": 12.50, "label": "ES  ($12.50/tick)", "default_commission": 3.0},
    "MES": {"tick_value":  1.25, "label": "MES ($1.25/tick)",  "default_commission": 1.0},
}
RTH_END_MIN = 15 * 60 + 15  # 915


def _ticks_after(day_ticks: pd.DataFrame, sig_dt):
    """Price/time numpy arrays for ticks strictly after sig_dt.

    Equivalent to `day_ticks[day_ticks["DateTime"] > sig_dt]` (the DateTime column
    is sorted ascending), but uses searchsorted — O(log n) + a view — instead of a
    full boolean mask + DataFrame copy on every signal. Returns None if no tick
    falls after sig_dt. side="right" excludes ticks exactly == sig_dt, matching the
    strict `>` comparison exactly.
    """
    dt_arr = day_ticks["DateTime"].values
    start = int(np.searchsorted(dt_arr, np.datetime64(pd.Timestamp(sig_dt)), side="right"))
    if start >= len(dt_arr):
        return None
    return day_ticks["Price"].values[start:], dt_arr[start:]


def _first_hit(mask: np.ndarray):
    """Index of the first True in a boolean array, or None. O(n) C-level scan —
    the vectorized analogue of the engine's `break` on the first matching tick."""
    nz = np.flatnonzero(mask)
    return int(nz[0]) if nz.size else None


# ── Empty trade template ──────────────────────────────────────────────────────

_EMPTY_TRADE = {
    "Filled": False,
    "SBClose": np.nan, "SEPrice": np.nan, "FillPrice": np.nan,
    "EntryTime": pd.NaT, "EntryBarNum": np.nan,
    "EntryPrice": np.nan, "ActualStop": np.nan, "Target": np.nan, "Target1": np.nan,
    "RiskPts": np.nan, "RiskDollar": np.nan,
    "ExitTime": pd.NaT, "ExitBarNum": np.nan,
    "ExitPrice": np.nan, "ExitReason": "",
    "GrossPnLPts": np.nan, "GrossPnL": np.nan, "NetPnL": np.nan,
    "R_achieved": np.nan,
    "MAE_pts": np.nan, "MAE_dollar": np.nan, "MAE_R": np.nan,
    "MFE_pts": np.nan, "MFE_dollar": np.nan, "MFE_R": np.nan,
    "CumPF": np.nan,
    "SlippagePts": np.nan, "SlippageDollar": np.nan,
    "Leg1ExitReason": np.nan, "Leg1ExitPrice": np.nan,
    "Leg1GrossPts": np.nan,   "Leg1GrossPnL": np.nan,
    "Leg2ExitReason": np.nan, "Leg2ExitPrice": np.nan,
    "Leg2GrossPts": np.nan,   "Leg2GrossPnL": np.nan,
    "Leg3ExitReason": np.nan, "Leg3ExitPrice": np.nan,
    "Leg3GrossPts": np.nan,   "Leg3GrossPnL": np.nan,
    # 3-leg specific
    "TradeType": "",   "BlendedEntry": np.nan,
    "PB1FillPrice": np.nan, "PB2FillPrice": np.nan,
    # 2-leg scale-in specific
    "PBLevel": np.nan, "PBLevelRaw": np.nan, "E2FillPrice": np.nan, "E2FillTime": pd.NaT,
    "T1_R": np.nan, "PB_R": np.nan,
    "SameBarConflict": False,
}


# ── Single-leg tick simulation ────────────────────────────────────────────────

def _simulate_one(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_ticks: pd.DataFrame,
    target_r: float, entry_slip: int, exit_slip: int, stop_offset: int, tv: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    manual_fill: dict | None = None,
    _force_loop: bool = False,
) -> dict:
    ts      = TICK_SIZE
    is_long = direction == "Long"

    _after = _ticks_after(day_ticks, sig_dt)
    if _after is None:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    if manual_fill is not None:
        fill_bar    = int(manual_fill["fill_bar"])
        fill_px_raw = float(manual_fill["fill_price"])
        bar_open_min = RTH_START_MIN + (fill_bar - 1) * 5
        sig_date     = pd.Timestamp(sig_dt).normalize()
        bar_open_dt  = sig_date + pd.Timedelta(minutes=bar_open_min)
        scan_ticks   = day_ticks[day_ticks["DateTime"] >= bar_open_dt]
        if scan_ticks.empty:
            return {"ok": False, "FilterStatus": "no_tick_data"}
        first_tick_px = fill_px_raw
        entry_dt      = scan_ticks.iloc[0]["DateTime"]
        prices        = scan_ticks["Price"].values
        times         = scan_ticks["DateTime"].values
    else:
        # Entry = first tick of the bar after the SB, unconditional
        prices, times = _after
        first_tick_px = float(prices[0])
        entry_dt      = pd.Timestamp(times[0])

    actual_entry = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    target_price = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar    = bar_num_from_dt(entry_dt)

    exit_px_raw   = float(prices[-1])
    exit_dt_raw   = times[-1]
    exit_reason   = "Session"
    mae = mfe     = 0.0
    active_stop   = actual_stop
    ratchet_fired = False

    if manual_fill is None and not _force_loop:
        # Vectorized scan: first-hit index instead of the Python loop.
        # Target is checked before stop in the loop, but for a single price the two
        # can never trigger on the same tick (target > entry >= stop for a long), so
        # the earlier index wins unambiguously.
        n   = len(prices)
        idx = np.arange(n)
        elig = idx >= 1
        exc  = (prices - actual_entry) if is_long else (actual_entry - prices)
        if is_long:
            tgt_m = (prices >  target_price) & elig
        else:
            tgt_m = (prices <  target_price) & elig
        ti = _first_hit(tgt_m)

        if ratchet_r == 0.0:
            # Stop never moves — active_stop == actual_stop throughout.
            if is_long:
                stop_m = (prices <= actual_stop) & elig
            else:
                stop_m = (prices >= actual_stop) & elig
            si = _first_hit(stop_m)
            rf = None
        else:
            # Ratchet on: stop moves to r_level the first eligible tick favorable
            # excursion >= ratchet_r·risk. Mirrors the loop (fire checked before the
            # exit checks; for a single price a fire and a stop-hit can't coincide).
            if ratchet_dest == "Lock-in":
                lk = ratchet_lock_r * risk_pts
                r_level = (actual_entry + lk) if is_long else (actual_entry - lk)
            else:
                r_level = actual_entry
            rf = _first_hit((exc >= ratchet_r * risk_pts) & elig)
            if rf is None:
                if is_long:
                    stop_m = (prices <= actual_stop) & elig
                else:
                    stop_m = (prices >= actual_stop) & elig
            else:
                pre  = idx < rf
                post = idx >= rf
                if is_long:
                    stop_m = elig & (((prices <= actual_stop) & pre) |
                                     ((prices <= r_level)     & post))
                else:
                    stop_m = elig & (((prices >= actual_stop) & pre) |
                                     ((prices >= r_level)     & post))
            si = _first_hit(stop_m)

        if si is None and ti is None:
            exit_idx = n - 1  # Session/EOD — exit_px_raw/exit_dt_raw already last tick
        elif ti is not None and (si is None or ti < si):
            exit_idx = ti
            exit_px_raw, exit_dt_raw, exit_reason = target_price, times[ti], "Target"
        else:
            exit_idx = si
            stop_lvl = actual_stop if (rf is None or si < rf) else r_level
            exit_px_raw, exit_dt_raw, exit_reason = stop_lvl, times[si], "Stop"
        seg = exc[:exit_idx + 1]
        mfe = max(0.0, float(seg.max()))
        mae = max(0.0, float(-seg.min()))
    else:
        for i, (p, t) in enumerate(zip(prices, times)):
            excursion = (p - actual_entry) if is_long else (actual_entry - p)
            mfe = max(mfe, excursion)
            mae = max(mae, -excursion)
            if i == 0:
                continue

            if ratchet_r > 0.0 and not ratchet_fired:
                favor = (p - actual_entry) if is_long else (actual_entry - p)
                if favor >= ratchet_r * risk_pts:
                    if ratchet_dest == "Lock-in":
                        lk = ratchet_lock_r * risk_pts
                        active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                    else:
                        active_stop = actual_entry
                    ratchet_fired = True

            if is_long:
                if p > target_price:
                    exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                    break
                if p <= active_stop:
                    exit_px_raw, exit_dt_raw, exit_reason = active_stop, t, "Stop"
                    break
            else:
                if p < target_price:
                    exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                    break
                if p >= active_stop:
                    exit_px_raw, exit_dt_raw, exit_reason = active_stop, t, "Stop"
                    break

    actual_exit     = exit_px_raw + (-exit_slip * ts if is_long else exit_slip * ts)
    exit_dt_ts      = pd.Timestamp(exit_dt_raw)
    exit_bar        = bar_num_from_dt(exit_dt_ts)
    gross_pts       = (actual_exit - actual_entry) if is_long else (actual_entry - actual_exit)
    gross_pnl       = gross_pts / ts * tv
    r_achieved      = gross_pts / risk_pts
    slippage_pts    = (entry_slip + exit_slip) * ts
    slippage_dollar = (entry_slip + exit_slip) * tv
    exit_label      = "EOD" if exit_reason == "Session" else exit_reason

    return {
        "ok": True,
        "SEPrice": signal_price, "FillPrice": first_tick_px,
        "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
        "EntryPrice": actual_entry, "ActualStop": actual_stop,
        "Target": target_price,
        "RiskPts": risk_pts, "RiskDollar": risk_pts / ts * tv,
        "ExitTime": exit_dt_ts, "ExitBarNum": exit_bar,
        "ExitPrice": actual_exit, "ExitReason": exit_label,
        "GrossPnLPts": gross_pts, "GrossPnL": gross_pnl,
        "R_achieved": r_achieved,
        "MAE_pts": mae, "MAE_dollar": mae / ts * tv, "MAE_R": mae / risk_pts,
        "MFE_pts": mfe, "MFE_dollar": mfe / ts * tv, "MFE_R": mfe / risk_pts,
        "SlippagePts": slippage_pts, "SlippageDollar": slippage_dollar,
    }


# ── Single-leg bar simulation ─────────────────────────────────────────────────

def _simulate_one_bars(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_bars: pd.DataFrame,
    target_r: float, entry_slip: int, exit_slip: int, stop_offset: int, tv: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
) -> dict:
    ts      = TICK_SIZE
    is_long = direction == "Long"

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    fill_px      = float(nb["Open"])
    actual_entry = fill_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    target_price     = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar        = bar_num_from_dt(nb["DateTime"])
    entry_dt         = nb["DateTime"]
    exit_px_raw      = float(next_bars.iloc[-1]["Close"])
    exit_dt_raw      = next_bars.iloc[-1]["DateTime"]
    exit_reason      = "Session"
    mae = mfe        = 0.0
    active_stop      = actual_stop
    ratchet_fired    = False
    same_bar_conflict = False

    for _, bar in next_bars.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - actual_entry) if is_long else (actual_entry - lo))
        mae = max(mae, (actual_entry - lo) if is_long else (hi - actual_entry))

        if ratchet_r > 0.0 and not ratchet_fired:
            favor = (hi - actual_entry) if is_long else (actual_entry - lo)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                else:
                    active_stop = actual_entry
                ratchet_fired = True

        hit_tgt  = (hi > target_price) if is_long else (lo < target_price)
        hit_stop = (lo <= active_stop) if is_long else (hi >= active_stop)

        if hit_stop and hit_tgt:
            same_bar_conflict = True
            exit_px_raw, exit_dt_raw, exit_reason = active_stop, bar["DateTime"], "Stop"
            break
        elif hit_tgt:
            exit_px_raw, exit_dt_raw, exit_reason = target_price, bar["DateTime"], "Target"
            break
        elif hit_stop:
            exit_px_raw, exit_dt_raw, exit_reason = active_stop, bar["DateTime"], "Stop"
            break

    actual_exit     = exit_px_raw + (-exit_slip * ts if is_long else exit_slip * ts)
    exit_dt_ts      = pd.Timestamp(exit_dt_raw)
    exit_bar        = bar_num_from_dt(exit_dt_ts)
    gross_pts       = (actual_exit - actual_entry) if is_long else (actual_entry - actual_exit)
    gross_pnl       = gross_pts / ts * tv
    r_achieved      = gross_pts / risk_pts
    slippage_pts    = (entry_slip + exit_slip) * ts
    slippage_dollar = (entry_slip + exit_slip) * tv

    return {
        "ok": True,
        "SEPrice": signal_price, "FillPrice": fill_px,
        "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
        "EntryPrice": actual_entry, "ActualStop": actual_stop,
        "Target": target_price,
        "RiskPts": risk_pts, "RiskDollar": risk_pts / ts * tv,
        "ExitTime": exit_dt_ts, "ExitBarNum": exit_bar,
        "ExitPrice": actual_exit, "ExitReason": "EOD" if exit_reason == "Session" else exit_reason,
        "GrossPnLPts": gross_pts, "GrossPnL": gross_pnl,
        "R_achieved": r_achieved,
        "MAE_pts": max(mae, 0.0), "MAE_dollar": max(mae, 0.0) / ts * tv,
        "MAE_R": max(mae, 0.0) / risk_pts,
        "MFE_pts": max(mfe, 0.0), "MFE_dollar": max(mfe, 0.0) / ts * tv,
        "MFE_R": max(mfe, 0.0) / risk_pts,
        "SlippagePts": slippage_pts, "SlippageDollar": slippage_dollar,
        "SameBarConflict": same_bar_conflict,
    }


# ── 2-leg tick simulation ─────────────────────────────────────────────────────

def _simulate_one_multileg(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_ticks: pd.DataFrame,
    target_r: float, t1_r: float, t1_action: str,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tv1: float, tv2: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    manual_fill: dict | None = None,
    ml_pb_r: float = 0.0,
    ml_pb_ticks: int = 0,
    scale_in_style: str = "e2",
    pb_round: str = "floor_ceil",
    _force_loop: bool = False,
) -> dict:
    ts       = TICK_SIZE
    is_long  = direction == "Long"
    tv_total = tv1 + tv2
    use_pb   = ml_pb_r < 0

    _after = _ticks_after(day_ticks, sig_dt)
    if _after is None:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    if manual_fill is not None:
        fill_bar     = int(manual_fill["fill_bar"])
        fill_px_raw  = float(manual_fill["fill_price"])
        bar_open_min = RTH_START_MIN + (fill_bar - 1) * 5
        sig_date     = pd.Timestamp(sig_dt).normalize()
        bar_open_dt  = sig_date + pd.Timedelta(minutes=bar_open_min)
        scan_ticks   = day_ticks[day_ticks["DateTime"] >= bar_open_dt]
        if scan_ticks.empty:
            return {"ok": False, "FilterStatus": "no_tick_data"}
        first_tick_px = fill_px_raw
        entry_dt      = scan_ticks.iloc[0]["DateTime"]
        prices        = scan_ticks["Price"].values
        times         = scan_ticks["DateTime"].values
    else:
        # Entry = first tick of the bar after the SB, unconditional
        prices, times = _after
        first_tick_px = float(prices[0])
        entry_dt      = pd.Timestamp(times[0])

    actual_entry = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price = actual_entry + (t1_r     * risk_pts if is_long else -t1_r     * risk_pts)
    t2_price = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar = bar_num_from_dt(entry_dt)
    mae = mfe = 0.0

    # PB trigger (only used when use_pb=True)
    pb_trigger   = None
    pb_level_raw = np.nan
    if use_pb:
        pb_level_raw = actual_entry + (ml_pb_r * risk_pts if is_long else -ml_pb_r * risk_pts)
        pb_raw = (pb_level_raw - ml_pb_ticks * ts) if is_long else (pb_level_raw + ml_pb_ticks * ts)
        if pb_round == "nearest":
            pb_trigger = round(round(pb_raw / ts) * ts, 10)
        else:  # floor_ceil — snap PB away from entry (conservative: harder to fill)
            pb_trigger = round(float(np.floor(pb_raw / ts) if is_long else np.ceil(pb_raw / ts)) * ts, 10)

    def _t2_for(blended_entry, e2_entry):
        # Post-E2 target — reference + R-unit depend on the scale-in style:
        #   "blended" — average the legs, target R off the blended risk
        #   "e2"      — E1 scratches at BE; target R off E2's own risk (at a 50%
        #               PB this lands T2 exactly on E1's entry, sizing-independent)
        if scale_in_style == "blended":
            ref, rr = blended_entry, abs(blended_entry - actual_stop)
        else:
            ref, rr = e2_entry, abs(e2_entry - actual_stop)
        raw = ref + (target_r * rr if is_long else -target_r * rr)
        return round(round(raw / ts) * ts, 10)

    # E2 state (populated if PB fills)
    e2_entry      = actual_entry
    e2_fill_dt    = None
    blended_entry = np.nan
    blended_risk  = np.nan

    def _leg_pts(exit_px):
        return (exit_px - actual_entry) if is_long else (actual_entry - exit_px)

    def _leg2_pts(exit_px):
        return (exit_px - e2_entry) if is_long else (e2_entry - exit_px)

    def _build(exit_reason, exit_price, exit_dt, leg1_er, leg1_px, leg2_er, leg2_px):
        _e2_filled  = leg2_er not in ("NoFill", None)
        l1_pts = _leg_pts(leg1_px) if leg1_px is not None else 0.0
        l2_pts = _leg2_pts(leg2_px) if (_e2_filled and leg2_px is not None) else 0.0
        l1_pnl = l1_pts / ts * tv1
        l2_pnl = l2_pts / ts * tv2
        g_pnl  = l1_pnl + l2_pnl
        g_pts  = l1_pts + l2_pts
        _e1_risk_dollar = risk_pts / ts * tv1
        r_ach  = g_pnl / _e1_risk_dollar if _e1_risk_dollar > 0 else 0.0
        _tv_active = tv_total if _e2_filled else tv1
        edt    = pd.Timestamp(exit_dt)
        return {
            "ok": True,
            "SEPrice": signal_price, "FillPrice": first_tick_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": actual_entry, "ActualStop": actual_stop,
            "Target": t2_price, "Target1": t1_price,
            "RiskPts": risk_pts, "RiskDollar": risk_pts / ts * tv1,
            "ExitTime": edt, "ExitBarNum": bar_num_from_dt(edt),
            "ExitPrice": exit_price, "ExitReason": exit_reason,
            "GrossPnLPts": g_pts, "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0), "MAE_dollar": max(mae, 0.0) / ts * _tv_active,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0), "MFE_dollar": max(mfe, 0.0) / ts * _tv_active,
            "MFE_R": max(mfe, 0.0) / risk_pts,
            "SlippagePts": (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * _tv_active,
            "Leg1ExitReason": leg1_er if leg1_px is not None else np.nan,
            "Leg1ExitPrice":  leg1_px if leg1_px is not None else np.nan,
            "Leg1GrossPts": l1_pts, "Leg1GrossPnL": l1_pnl,
            "Leg2ExitReason": leg2_er, "Leg2ExitPrice": leg2_px,
            "Leg2GrossPts": l2_pts, "Leg2GrossPnL": l2_pnl,
            "PBLevel":    round(float(pb_trigger), 2) if pb_trigger is not None else np.nan,
            "PBLevelRaw": round(float(pb_level_raw), 4) if not (isinstance(pb_level_raw, float) and np.isnan(pb_level_raw)) else np.nan,
            "E2FillPrice": round(float(e2_entry), 2) if _e2_filled else np.nan,
            "E2FillTime":  pd.Timestamp(e2_fill_dt) if (e2_fill_dt is not None and _e2_filled) else pd.NaT,
            "BlendedEntry": round(float(blended_entry), 2) if _e2_filled else np.nan,
        }

    # ── PB SCALE-IN MODE ─────────────────────────────────────────────────────────
    # Rule: if T1 hits before PB → trade over (single leg at T1).
    # Rule: if PB hits before T1 → E2 fills, T2 recomputed from blended entry.
    #       After PB fills, T1 is ignored; both legs hold to T2 or stop.
    if use_pb and ratchet_r == 0.0 and manual_fill is None and not _force_loop:
        # Vectorized ratchet-off PB scan — mirrors the loop below via first-hit
        # indices (same mechanism proven correct by scripts/validate_oracle.py).
        # Tick-priority within the loop: PB fill (then `continue`) → stop (touch) →
        # T2 (post-PB) or T1 (pre-PB). Stop sits deeper than pb_trigger, so any
        # stop tick is also a PB tick → no stop can fire before PB fills; only T1
        # can fire pre-PB. Post-PB, stop is checked before T2 (earlier index wins;
        # a single price can't hit both).
        n    = len(prices)
        idx  = np.arange(n)
        elig = idx >= 1
        exc  = (prices - actual_entry) if is_long else (actual_entry - prices)
        if is_long:
            pb_m   = (prices <  pb_trigger) & elig
            stop_m = (prices <= actual_stop) & elig
            t1_m   = (prices >  t1_price) & elig
        else:
            pb_m   = (prices >  pb_trigger) & elig
            stop_m = (prices >= actual_stop) & elig
            t1_m   = (prices <  t1_price) & elig

        def _exc_mae_mfe(end_idx):
            seg = exc[:end_idx + 1]
            return max(0.0, float(-seg.min())), max(0.0, float(seg.max()))

        pb_i = _first_hit(pb_m)

        if pb_i is None:
            # PB never fills → single leg, T1/stop/EOD only (stop can't fire here).
            si = _first_hit(stop_m)
            ti = _first_hit(t1_m)
            if si is None and ti is None:
                mae, mfe = _exc_mae_mfe(n - 1)
                eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("EOD", eod_px, times[-1], "EOD", eod_px, "NoFill", actual_entry)
            if ti is not None and (si is None or ti < si):
                mae, mfe = _exc_mae_mfe(ti)
                t1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("T1_only", t1_exit_px, times[ti], "T1", t1_exit_px, "NoFill", actual_entry)
            mae, mfe = _exc_mae_mfe(si)
            sp = actual_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("Stop", sp, times[si], "Stop", sp, "NoFill", actual_entry)

        # T1 before PB → leg-1-only exit, no scale-in
        t1_pre = _first_hit(t1_m & (idx < pb_i))
        if t1_pre is not None:
            mae, mfe = _exc_mae_mfe(t1_pre)
            t1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("T1_only", t1_exit_px, times[t1_pre], "T1", t1_exit_px, "NoFill", actual_entry)

        # PB fills at pb_i — arithmetic copied verbatim from the loop
        e2_raw        = pb_trigger + (entry_slip * ts if is_long else -entry_slip * ts)
        e2_entry      = round(round(e2_raw / ts) * ts, 10)
        e2_fill_dt    = times[pb_i]
        blended_entry = (actual_entry * tv1 + e2_entry * tv2) / tv_total
        blended_risk  = abs(blended_entry - actual_stop)
        t2_price      = _t2_for(blended_entry, e2_entry)

        post = idx > pb_i
        if is_long:
            t2_m = (prices > t2_price) & elig
        else:
            t2_m = (prices < t2_price) & elig
        stop_post = _first_hit(stop_m & post)
        t2_post   = _first_hit(t2_m & post)

        if stop_post is None and t2_post is None:
            mae, mfe = _exc_mae_mfe(n - 1)
            eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("E1E2+EOD", eod_px, times[-1], "E2filled", eod_px, "EOD", eod_px)
        if t2_post is not None and (stop_post is None or t2_post < stop_post):
            mae, mfe = _exc_mae_mfe(t2_post)
            t2_exit_px = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("E1E2+Target", t2_exit_px, times[t2_post], "E2filled", t2_exit_px, "Target", t2_exit_px)
        mae, mfe = _exc_mae_mfe(stop_post)
        sp = actual_stop + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("Stop", sp, times[stop_post], "Stop", sp, "Stop", sp)

    if use_pb and ratchet_r > 0.0 and manual_fill is None and not _force_loop:
        # Vectorized ratchet-ON PB scan — encodes the loop's state machine via
        # first-hit indices. Ratchet ref switches: actual_entry pre-PB, blended
        # post-PB; threshold/lock use the ORIGINAL risk_pts. A pre-PB fire moves
        # the stop up to BE, which can preempt the PB fill (in-tick priority:
        # PB > stop > T1, matching the loop's check order). Once fired the latch
        # holds across the PB transition, so the stop never re-moves to blended.
        n    = len(prices)
        idx  = np.arange(n)
        elig = idx >= 1
        exc  = (prices - actual_entry) if is_long else (actual_entry - prices)
        thresh = ratchet_r * risk_pts

        def _mm(end_idx):
            seg = exc[:end_idx + 1]
            return max(0.0, float(-seg.min())), max(0.0, float(seg.max()))

        if ratchet_dest == "Lock-in":
            lk = ratchet_lock_r * risk_pts
            be_pre = (actual_entry + lk) if is_long else (actual_entry - lk)
        else:
            lk = 0.0
            be_pre = actual_entry

        if is_long:
            pb_all   = prices <  pb_trigger
            t1_all   = prices >  t1_price
            bes_pre  = prices <= be_pre
        else:
            pb_all   = prices >  pb_trigger
            t1_all   = prices <  t1_price
            bes_pre  = prices >= be_pre

        rf_pre = _first_hit((exc >= thresh) & elig)
        pb_i0  = _first_hit(pb_all & elig)
        t1_i0  = _first_hit(t1_all & elig)

        fired_pre = False
        pb_i      = None
        pre_fires = (rf_pre is not None
                     and (pb_i0 is None or rf_pre < pb_i0)
                     and (t1_i0 is None or rf_pre < t1_i0))

        if pre_fires:
            fired_pre = True
            after = (idx > rf_pre) & elig
            pb_a  = _first_hit(pb_all & after)
            bes_a = _first_hit(bes_pre & after)
            t1_a  = _first_hit(t1_all & after)
            # earliest event; in-tick priority PB > stop > T1 (can't truly coincide)
            cands = []
            if pb_a  is not None: cands.append((pb_a, 0, "PB"))
            if bes_a is not None: cands.append((bes_a, 1, "Stop"))
            if t1_a  is not None: cands.append((t1_a, 2, "T1"))
            if not cands:
                mae, mfe = _mm(n - 1)
                eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("EOD", eod_px, times[-1], "EOD", eod_px, "NoFill", actual_entry)
            cands.sort(key=lambda c: (c[0], c[1]))
            widx, _, wkind = cands[0]
            if wkind == "Stop":
                mae, mfe = _mm(widx)
                sp = be_pre + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("Stop", sp, times[widx], "Stop", sp, "NoFill", actual_entry)
            if wkind == "T1":
                mae, mfe = _mm(widx)
                t1px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("T1_only", t1px, times[widx], "T1", t1px, "NoFill", actual_entry)
            pb_i = widx  # PB fills; fired_pre stays True (active_stop fixed at be_pre)
        else:
            if t1_i0 is not None and (pb_i0 is None or t1_i0 < pb_i0):
                mae, mfe = _mm(t1_i0)
                t1px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("T1_only", t1px, times[t1_i0], "T1", t1px, "NoFill", actual_entry)
            if pb_i0 is None:
                mae, mfe = _mm(n - 1)
                eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
                return _build("EOD", eod_px, times[-1], "EOD", eod_px, "NoFill", actual_entry)
            pb_i = pb_i0

        # ── Phase 2: PB filled at pb_i (arithmetic copied verbatim from the loop) ──
        e2_raw        = pb_trigger + (entry_slip * ts if is_long else -entry_slip * ts)
        e2_entry      = round(round(e2_raw / ts) * ts, 10)
        e2_fill_dt    = times[pb_i]
        blended_entry = (actual_entry * tv1 + e2_entry * tv2) / tv_total
        blended_risk  = abs(blended_entry - actual_stop)
        t2_price      = _t2_for(blended_entry, e2_entry)

        post = (idx > pb_i) & elig
        if is_long:
            t2_all = prices > t2_price
        else:
            t2_all = prices < t2_price
        ti = _first_hit(t2_all & post)

        if fired_pre:
            # active_stop fixed at be_pre throughout phase 2 (latch already set)
            si = _first_hit(bes_pre & post)
            stop_lvl = be_pre
        else:
            favor_post = (prices - blended_entry) if is_long else (blended_entry - prices)
            rf_post = _first_hit((favor_post >= thresh) & post)
            be_post = (blended_entry + lk) if (is_long) else (blended_entry - lk)
            if not (ratchet_dest == "Lock-in"):
                be_post = blended_entry
            if is_long:
                stop_orig = prices <= actual_stop
                stop_be   = prices <= be_post
            else:
                stop_orig = prices >= actual_stop
                stop_be   = prices >= be_post
            if rf_post is None:
                si = _first_hit(stop_orig & post)
                stop_lvl = actual_stop
            else:
                pre2 = post & (idx < rf_post)
                aft2 = post & (idx >= rf_post)
                si = _first_hit((stop_orig & pre2) | (stop_be & aft2))
                stop_lvl = actual_stop if (si is not None and si < rf_post) else be_post

        if si is None and ti is None:
            mae, mfe = _mm(n - 1)
            eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("E1E2+EOD", eod_px, times[-1], "E2filled", eod_px, "EOD", eod_px)
        if ti is not None and (si is None or ti < si):
            mae, mfe = _mm(ti)
            t2px = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            return _build("E1E2+Target", t2px, times[ti], "E2filled", t2px, "Target", t2px)
        mae, mfe = _mm(si)
        sp = stop_lvl + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("Stop", sp, times[si], "Stop", sp, "Stop", sp)

    if use_pb:
        pb_filled       = False
        full_stop_price = None
        full_stop_dt    = None
        t1_only         = False
        t1_exit_px      = None
        t1_exit_dt      = None
        t2_exit_px      = None
        t2_exit_dt      = None
        active_stop     = actual_stop
        ratchet_fired   = False

        for i, (p, t) in enumerate(zip(prices, times)):
            excursion = (p - actual_entry) if is_long else (actual_entry - p)
            mfe = max(mfe, excursion)
            mae = max(mae, -excursion)
            if i == 0:
                continue

            # PB fill: tick-through (strict < for long, strict > for short)
            if not pb_filled:
                if (p < pb_trigger) if is_long else (p > pb_trigger):
                    e2_raw = pb_trigger + (entry_slip * ts if is_long else -entry_slip * ts)
                    e2_entry   = round(round(e2_raw / ts) * ts, 10)
                    e2_fill_dt = t
                    blended_entry = (actual_entry * tv1 + e2_entry * tv2) / tv_total
                    blended_risk  = abs(blended_entry - actual_stop)
                    t2_price = _t2_for(blended_entry, e2_entry)
                    pb_filled = True
                    continue  # don't check stop/target on this same tick

            # Ratchet (stop trail) — active after PB fills; uses blended entry as reference
            if ratchet_r > 0.0 and not ratchet_fired:
                ref   = blended_entry if pb_filled else actual_entry
                favor = (p - ref) if is_long else (ref - p)
                if favor >= ratchet_r * risk_pts:
                    if ratchet_dest == "Lock-in":
                        lk = ratchet_lock_r * risk_pts
                        active_stop = (ref + lk) if is_long else (ref - lk)
                    else:
                        active_stop = ref
                    ratchet_fired = True

            # Stop check (fills on touch)
            if (p <= active_stop) if is_long else (p >= active_stop):
                sp = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
                full_stop_price = sp
                full_stop_dt    = t
                break

            if pb_filled:
                # T2 check (tick-through, blended target)
                if (p > t2_price) if is_long else (p < t2_price):
                    t2_exit_px = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
                    t2_exit_dt = t
                    break
            else:
                # T1 check (tick-through) — only relevant before PB fills
                if (p > t1_price) if is_long else (p < t1_price):
                    t1_only    = True
                    t1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
                    t1_exit_dt = t
                    break

        if full_stop_price is not None:
            sp = full_stop_price
            if pb_filled:
                return _build("Stop", sp, full_stop_dt, "Stop", sp, "Stop", sp)
            return _build("Stop", sp, full_stop_dt, "Stop", sp, "NoFill", actual_entry)

        if t1_only:
            return _build("T1_only", t1_exit_px, t1_exit_dt, "T1", t1_exit_px, "NoFill", actual_entry)

        if t2_exit_px is not None:
            return _build("E1E2+Target", t2_exit_px, t2_exit_dt, "E2filled", t2_exit_px, "Target", t2_exit_px)

        # EOD: session ended without T1, stop, or T2
        eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
        if pb_filled:
            return _build("E1E2+EOD", eod_px, times[-1], "E2filled", eod_px, "EOD", eod_px)
        return _build("EOD", eod_px, times[-1], "EOD", eod_px, "NoFill", actual_entry)

    # ── ORIGINAL T1+T2 MODE (no PB) ──────────────────────────────────────────────
    active_stop   = actual_stop
    ratchet_fired = False
    phase1_end_idx  = None
    leg1_exit_price = None
    full_stop_price = None
    full_stop_dt    = None

    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - actual_entry) if is_long else (actual_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if i == 0:
            continue

        if ratchet_r > 0.0 and not ratchet_fired:
            favor = (p - actual_entry) if is_long else (actual_entry - p)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                else:
                    active_stop = actual_entry
                ratchet_fired = True

        hit_t1   = (p > t1_price)    if is_long else (p < t1_price)
        hit_stop = (p <= active_stop) if is_long else (p >= active_stop)
        if hit_t1:
            if t1_action == "exit":
                leg1_exit_price = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            phase1_end_idx = i
            break
        if hit_stop:
            full_stop_price = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            full_stop_dt    = t
            break

    if full_stop_price is not None:
        sp = full_stop_price
        return _build("Stop", sp, full_stop_dt, "Stop", sp, "NoFill", actual_entry)

    if phase1_end_idx is None:
        eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, times[-1], "EOD", eod_px, "NoFill", actual_entry)

    be_stop       = actual_entry
    p2            = prices[phase1_end_idx:]
    t2_arr        = times[phase1_end_idx:]
    l2_reason_raw = "Session"
    l2_px_raw     = float(p2[-1])
    l2_dt_raw     = t2_arr[-1]

    for j, (p2v, t2v) in enumerate(zip(p2, t2_arr)):
        excursion = (p2v - actual_entry) if is_long else (actual_entry - p2v)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if j == 0:
            continue
        hit_t2 = (p2v > t2_price)  if is_long else (p2v < t2_price)
        hit_be = (p2v <= be_stop)  if is_long else (p2v >= be_stop)
        if hit_t2:
            l2_reason_raw, l2_px_raw, l2_dt_raw = "Target", t2_price, t2v
            break
        if hit_be:
            l2_reason_raw, l2_px_raw, l2_dt_raw = "BE", be_stop, t2v
            break

    l2_exit_px = l2_px_raw + (-exit_slip * ts if is_long else exit_slip * ts)
    reason_map = {"Target": ("T1+Target", "Target"),
                  "BE":     ("T1+BE",     "BE"),
                  "Session":("T1+EOD",    "EOD")}
    exit_str, l2_er = reason_map[l2_reason_raw]
    l1_er = "T1" if leg1_exit_price is not None else np.nan
    return _build(exit_str, l2_exit_px, l2_dt_raw, l1_er, leg1_exit_price, l2_er, l2_exit_px)


# ── 2-leg bar simulation ──────────────────────────────────────────────────────

def _simulate_one_bars_multileg(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_bars: pd.DataFrame,
    target_r: float, t1_r: float, t1_action: str,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tv1: float, tv2: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    e2_pb_r: float = 0.0,
    e2_pb_ticks: int = 0,
) -> dict:
    ts       = TICK_SIZE
    is_long  = direction == "Long"
    tv_total = tv1 + tv2

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    fill_px          = float(nb["Open"])
    actual_entry_raw = fill_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_entry     = round(round(actual_entry_raw / ts) * ts, 10)
    actual_stop      = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts         = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price  = actual_entry + (t1_r * risk_pts if is_long else -t1_r * risk_pts)
    t2_price  = t1_price  # overwritten after E2 fills
    entry_bar = bar_num_from_dt(nb["DateTime"])
    entry_dt  = nb["DateTime"]
    mae = mfe = 0.0

    e2_entry      = actual_entry
    e2_fill_dt    = None
    blended_entry = np.nan
    blended_risk  = np.nan

    def _leg_pts(exit_px):
        return (exit_px - actual_entry) if is_long else (actual_entry - exit_px)

    def _leg2_pts(exit_px):
        return (exit_px - e2_entry) if is_long else (e2_entry - exit_px)

    same_bar_conflict = False

    def _build(exit_reason, exit_price, exit_dt, leg1_er, leg1_px, leg2_er, leg2_px):
        l1_pts = _leg_pts(leg1_px) if leg1_px is not None else 0.0
        l2_pts = _leg2_pts(leg2_px) if leg2_px is not None else 0.0
        l1_pnl = l1_pts / ts * tv1
        l2_pnl = l2_pts / ts * tv2
        g_pnl  = l1_pnl + l2_pnl
        g_pts  = l1_pts + l2_pts
        _e2_filled   = (leg2_er not in ("NoFill", None))
        _tv_active   = tv_total if _e2_filled else tv1
        _risk_dollar = (blended_risk / ts * tv_total
                        if (_e2_filled and not (isinstance(blended_risk, float) and np.isnan(blended_risk)))
                        else risk_pts / ts * tv1)
        _e1_risk_dollar = risk_pts / ts * tv1
        r_ach  = g_pnl / _e1_risk_dollar if _e1_risk_dollar > 0 else 0.0
        edt    = pd.Timestamp(exit_dt)
        return {
            "ok": True,
            "SEPrice": signal_price, "FillPrice": fill_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": actual_entry, "ActualStop": actual_stop,
            "Target": t2_price, "Target1": t1_price,
            "RiskPts": risk_pts, "RiskDollar": _risk_dollar,
            "ExitTime": edt, "ExitBarNum": bar_num_from_dt(edt),
            "ExitPrice": exit_price, "ExitReason": exit_reason,
            "GrossPnLPts": g_pts, "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0), "MAE_dollar": max(mae, 0.0) / ts * _tv_active,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0), "MFE_dollar": max(mfe, 0.0) / ts * _tv_active,
            "MFE_R": max(mfe, 0.0) / risk_pts,
            "SlippagePts": (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * _tv_active,
            "Leg1ExitReason": leg1_er if leg1_px is not None else np.nan,
            "Leg1ExitPrice":  leg1_px if leg1_px is not None else np.nan,
            "Leg1GrossPts": l1_pts, "Leg1GrossPnL": l1_pnl,
            "Leg2ExitReason": leg2_er, "Leg2ExitPrice": leg2_px,
            "Leg2GrossPts": l2_pts, "Leg2GrossPnL": l2_pnl,
            "PBLevel":    round(float(pb_trigger), 2) if pb_trigger is not None else np.nan,
            "PBLevelRaw": round(float(pb_level_raw), 4) if not np.isnan(pb_level_raw) else np.nan,
            "E2FillPrice": round(float(e2_entry), 2) if _e2_filled else np.nan,
            "E2FillTime":  pd.Timestamp(e2_fill_dt) if (e2_fill_dt is not None and _e2_filled) else pd.NaT,
            "BlendedEntry": round(float(blended_entry), 2) if _e2_filled else np.nan,
            "SameBarConflict": same_bar_conflict,
        }

    use_pb       = e2_pb_r < 0
    pb_trigger   = None
    pb_level_raw = np.nan
    if use_pb:
        pb_level_raw = actual_entry + (e2_pb_r * risk_pts if is_long else -e2_pb_r * risk_pts)
        pb_raw       = (pb_level_raw - e2_pb_ticks * ts) if is_long else (pb_level_raw + e2_pb_ticks * ts)
        if is_long:
            pb_trigger = round(float(np.floor(pb_raw / ts)) * ts, 10)
        else:
            pb_trigger = round(float(np.ceil(pb_raw / ts)) * ts, 10)

    p1_result  = "Session"
    p1_dt      = None
    p1_exit_px = None
    p1_fill_pos = None

    for pos, (_, bar) in enumerate(next_bars.iterrows()):
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - actual_entry) if is_long else (actual_entry - lo))
        mae = max(mae, (actual_entry - lo) if is_long else (hi - actual_entry))

        hit_t1   = (hi > t1_price)     if is_long else (lo < t1_price)
        hit_stop = (lo <= actual_stop) if is_long else (hi >= actual_stop)
        hit_pb   = use_pb and ((lo < pb_trigger) if is_long else (hi > pb_trigger))

        if hit_stop and (hit_t1 or hit_pb):
            same_bar_conflict = True
        if hit_t1 and hit_pb:
            same_bar_conflict = True

        if hit_stop:
            p1_result  = "Stop"
            p1_dt      = bar["DateTime"]
            p1_exit_px = actual_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            break
        if hit_t1 and not hit_pb:
            p1_result  = "T1_only"
            p1_dt      = bar["DateTime"]
            p1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            break
        if hit_pb:
            if hit_t1:
                same_bar_conflict = True
                p1_result  = "T1_only"
                p1_dt      = bar["DateTime"]
                p1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            else:
                e2_entry      = round(round((pb_trigger + (entry_slip * ts if is_long else -entry_slip * ts)) / ts) * ts, 10)
                e2_fill_dt    = bar["DateTime"]
                blended_entry = (actual_entry * tv1 + e2_entry * tv2) / tv_total
                blended_risk  = abs(blended_entry - actual_stop)
                t2_price      = _t2_for(blended_entry, e2_entry)
                p1_result     = "PB_filled"
                p1_fill_pos   = pos
            break

    if p1_result == "Stop":
        return _build("Stop", p1_exit_px, p1_dt, "Stop", p1_exit_px, "NoFill", actual_entry)
    if p1_result == "T1_only":
        return _build("T1_only", p1_exit_px, p1_dt, "T1", p1_exit_px, "NoFill", actual_entry)
    if p1_result == "Session":
        last_bar = next_bars.iloc[-1]
        eod_px   = float(last_bar["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, last_bar["DateTime"], "EOD", eod_px, "NoFill", actual_entry)

    phase2   = next_bars.iloc[p1_fill_pos + 1:]
    last_bar = next_bars.iloc[-1]
    p2_result = "Session"
    p2_px_r   = float(last_bar["Close"])
    p2_dt     = last_bar["DateTime"]

    for _, bar2 in phase2.iterrows():
        hi2, lo2 = float(bar2["High"]), float(bar2["Low"])
        mfe = max(mfe, (hi2 - actual_entry) if is_long else (actual_entry - lo2))
        mae = max(mae, (actual_entry - lo2) if is_long else (hi2 - actual_entry))

        hit_t2    = (hi2 > t2_price)  if is_long else (lo2 < t2_price)
        hit_stop2 = (lo2 <= actual_stop) if is_long else (hi2 >= actual_stop)

        if hit_stop2 and hit_t2:
            same_bar_conflict = True
        if hit_stop2:
            p2_result, p2_px_r, p2_dt = "Stop", actual_stop, bar2["DateTime"]
            break
        if hit_t2:
            p2_result, p2_px_r, p2_dt = "Target", t2_price, bar2["DateTime"]
            break

    p2_exit_px = p2_px_r + (-exit_slip * ts if is_long else exit_slip * ts)
    reason_map = {"Target":  ("E1E2+Target", "Target"),
                  "Stop":    ("E1E2+Stop",   "Stop"),
                  "Session": ("E1E2+EOD",    "EOD")}
    exit_str, l2_er = reason_map[p2_result]
    return _build(exit_str, p2_exit_px, p2_dt, "E2filled", p2_exit_px, l2_er, p2_exit_px)


# ── 3-leg tick simulation ─────────────────────────────────────────────────────

def _simulate_one_3leg(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_ticks: pd.DataFrame,
    t1_r: float, t2_r: float, target_r: float,
    t1_action: str,
    tv1: float, tv2: float, tv3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_r: float, pb1_ticks: int,
    pb2_r: float, pb2_ticks: int,
    entry_slip: float, exit_slip: float, stop_offset: int,
    ratchet_r: float = 0.0, ratchet_dest: str = "BE", ratchet_lock_r: float = 0.0,
    manual_fill: dict | None = None,
) -> dict:
    ts      = TICK_SIZE
    is_long = direction == "Long"

    _after = _ticks_after(day_ticks, sig_dt)
    if _after is None:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    if manual_fill is not None:
        fill_bar     = int(manual_fill["fill_bar"])
        fill_px_raw  = float(manual_fill["fill_price"])
        bar_open_min = RTH_START_MIN + (fill_bar - 1) * 5
        sig_date     = pd.Timestamp(sig_dt).normalize()
        bar_open_dt  = sig_date + pd.Timedelta(minutes=bar_open_min)
        scan_ticks   = day_ticks[day_ticks["DateTime"] >= bar_open_dt]
        if scan_ticks.empty:
            return {"ok": False, "FilterStatus": "no_tick_data"}
        first_tick_px = fill_px_raw
        entry_dt      = scan_ticks.iloc[0]["DateTime"]
        prices        = scan_ticks["Price"].values
        times         = scan_ticks["DateTime"].values
    else:
        # Entry = first tick of the bar after the SB, unconditional
        prices, times = _after
        first_tick_px = float(prices[0])
        entry_dt      = pd.Timestamp(times[0])

    e1_entry    = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts    = abs(e1_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price  = e1_entry + (t1_r     * risk_pts if is_long else -t1_r     * risk_pts)
    t2_price  = e1_entry + (t2_r     * risk_pts if is_long else -t2_r     * risk_pts)
    t3_price  = e1_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar = bar_num_from_dt(entry_dt)

    if is_long:
        pb1_price_raw = e1_entry - pb1_r * risk_pts + pb1_ticks * ts
        pb2_price_raw = e1_entry - pb2_r * risk_pts + pb2_ticks * ts
        pb1_price = max(pb1_price_raw, actual_stop + ts)
        pb2_price = max(pb2_price_raw, actual_stop + ts)
        pb2_price = min(pb2_price, pb1_price - ts)
    else:
        pb1_price_raw = e1_entry + pb1_r * risk_pts - pb1_ticks * ts
        pb2_price_raw = e1_entry + pb2_r * risk_pts - pb2_ticks * ts
        pb1_price = min(pb1_price_raw, actual_stop - ts)
        pb2_price = min(pb2_price_raw, actual_stop - ts)
        pb2_price = max(pb2_price, pb1_price + ts)

    active_stop    = actual_stop
    ratchet_fired  = False
    pb1_filled     = False
    pb2_filled     = False
    e2_entry_px    = None
    e3_entry_px    = None
    phase1_end_idx = None
    full_stop_px   = None
    full_stop_dt   = None
    mae = mfe      = 0.0

    def _blended():
        if pb2_filled and e2_entry_px is not None and e3_entry_px is not None:
            tot = tv1 + tv2 + tv3
            return (e1_entry*tv1 + e2_entry_px*tv2 + e3_entry_px*tv3) / tot if tot > 0 else e1_entry
        if pb1_filled and e2_entry_px is not None:
            tot = tv1 + tv2
            return (e1_entry*tv1 + e2_entry_px*tv2) / tot if tot > 0 else e1_entry
        return e1_entry

    def _build(exit_reason, exit_px, exit_dt, leg1_exit_px=None,
               e2_exit=None, e2_rsn=None, e3_exit=None, e3_rsn=None):
        tv_used  = tv1 + (tv2 if pb1_filled else 0.0) + (tv3 if pb2_filled else 0.0)
        l1_ep    = leg1_exit_px if leg1_exit_px is not None else exit_px
        l1_pts   = (l1_ep - e1_entry) if is_long else (e1_entry - l1_ep)
        l1_pnl   = l1_pts / ts * tv1
        l2_ep    = e2_exit if e2_exit is not None else exit_px
        l2_pts   = (l2_ep - e2_entry_px) if (is_long and pb1_filled) else \
                   (e2_entry_px - l2_ep) if (not is_long and pb1_filled) else 0.0
        l2_pnl   = l2_pts / ts * tv2 if pb1_filled else 0.0
        l3_ep    = e3_exit if e3_exit is not None else exit_px
        l3_pts   = (l3_ep - e3_entry_px) if (is_long and pb2_filled) else \
                   (e3_entry_px - l3_ep) if (not is_long and pb2_filled) else 0.0
        l3_pnl   = l3_pts / ts * tv3 if pb2_filled else 0.0
        g_pnl    = l1_pnl + l2_pnl + l3_pnl
        g_pts    = l1_pts + l2_pts + l3_pts
        r_risk   = risk_pts / ts * tv1
        r_ach    = g_pnl / r_risk if r_risk > 0 else 0.0
        ttype    = ("E1+PB1+PB2" if pb2_filled else "E1+PB1" if pb1_filled else "Rocket")
        filled_c = e1c + (e2c if pb1_filled else 0) + (e3c if pb2_filled else 0)
        edt      = pd.Timestamp(exit_dt)
        l1_er    = "T1" if leg1_exit_px is not None else exit_reason
        return {
            "ok": True,
            "SEPrice": signal_price, "FillPrice": first_tick_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": e1_entry, "ActualStop": actual_stop,
            "Target": t3_price, "Target1": t1_price,
            "RiskPts": risk_pts, "RiskDollar": risk_pts / ts * tv1,
            "ExitTime": edt, "ExitBarNum": bar_num_from_dt(edt),
            "ExitPrice": exit_px, "ExitReason": exit_reason,
            "GrossPnLPts": g_pts, "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0), "MAE_dollar": max(mae, 0.0) / ts * tv_used,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0), "MFE_dollar": max(mfe, 0.0) / ts * tv_used,
            "MFE_R": max(mfe, 0.0) / risk_pts,
            "SlippagePts": (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * tv_used,
            "Leg1ExitReason": l1_er, "Leg1ExitPrice": l1_ep,
            "Leg1GrossPts": l1_pts,  "Leg1GrossPnL": l1_pnl,
            "Leg2ExitReason": (e2_rsn or exit_reason) if pb1_filled else np.nan,
            "Leg2ExitPrice":  l2_ep if pb1_filled else np.nan,
            "Leg2GrossPts": l2_pts,  "Leg2GrossPnL": l2_pnl,
            "Leg3ExitReason": (e3_rsn or exit_reason) if pb2_filled else np.nan,
            "Leg3ExitPrice":  l3_ep if pb2_filled else np.nan,
            "Leg3GrossPts": l3_pts,  "Leg3GrossPnL": l3_pnl,
            "TradeType": ttype, "BlendedEntry": _blended(),
            "PB1FillPrice": e2_entry_px if pb1_filled else np.nan,
            "PB2FillPrice": e3_entry_px if pb2_filled else np.nan,
            "FilledContracts": filled_c,
        }

    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - e1_entry) if is_long else (e1_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if i == 0:
            continue
        if not pb1_filled and tv2 > 0:
            if (p < pb1_price) if is_long else (p > pb1_price):
                e2_fill = pb1_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e2_fill > actual_stop) or (not is_long and e2_fill < actual_stop):
                    e2_entry_px = e2_fill
                    pb1_filled  = True
        if pb1_filled and not pb2_filled and tv3 > 0:
            if (p < pb2_price) if is_long else (p > pb2_price):
                e3_fill = pb2_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e3_fill > actual_stop) or (not is_long and e3_fill < actual_stop):
                    e3_entry_px = e3_fill
                    pb2_filled  = True
        if ratchet_r > 0.0 and not ratchet_fired:
            bl    = _blended()
            favor = (p - bl) if is_long else (bl - p)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (bl + lk) if is_long else (bl - lk)
                elif ratchet_dest == "E1":
                    active_stop = e1_entry
                else:
                    active_stop = _blended()
                ratchet_fired = True
        if (p <= active_stop) if is_long else (p >= active_stop):
            sp = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            full_stop_px = sp; full_stop_dt = t
            break
        if (p > t1_price) if is_long else (p < t1_price):
            phase1_end_idx = i
            break

    if full_stop_px is not None:
        return _build("Stop", full_stop_px, full_stop_dt)
    if phase1_end_idx is None:
        eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, times[-1])

    leg1_exit_px = None
    if t1_action == "exit":
        leg1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)

    be_stop_p2 = _blended()
    p2_pr      = prices[phase1_end_idx:]
    p2_ts      = times[phase1_end_idx:]
    last_p2_px = float(p2_pr[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
    last_p2_dt = p2_ts[-1]

    e2_done = not pb1_filled; e3_done = not pb2_filled
    e2_exit = None; e2_rsn = None
    e3_exit = None; e3_rsn = None
    be_px   = None; be_dt  = None

    for j, (p2v, t2v) in enumerate(zip(p2_pr, p2_ts)):
        excursion = (p2v - e1_entry) if is_long else (e1_entry - p2v)
        mfe = max(mfe, excursion); mae = max(mae, -excursion)
        if j == 0: continue
        if (p2v <= be_stop_p2) if is_long else (p2v >= be_stop_p2):
            sp2 = be_stop_p2 + (-exit_slip * ts if is_long else exit_slip * ts)
            if not e2_done: e2_exit = sp2; e2_rsn = "BE"; e2_done = True
            if not e3_done: e3_exit = sp2; e3_rsn = "BE"; e3_done = True
            be_px = sp2; be_dt = t2v; break
        if not e2_done and ((p2v > t2_price) if is_long else (p2v < t2_price)):
            e2_exit = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e2_rsn = "T2"; e2_done = True
        if not e3_done and ((p2v > t3_price) if is_long else (p2v < t3_price)):
            e3_exit = t3_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e3_rsn = "T3"; e3_done = True
        if e2_done and e3_done: break

    if not e2_done: e2_exit = last_p2_px; e2_rsn = "EOD"
    if not e3_done: e3_exit = last_p2_px; e3_rsn = "EOD"

    p2_rsns = {r for r in [e2_rsn if pb1_filled else None,
                            e3_rsn if pb2_filled else None] if r}
    if be_px is not None:
        overall = "T1+BE"; final_px = be_px; final_dt = be_dt
    elif not p2_rsns:
        overall = "Target"; final_px = leg1_exit_px or last_p2_px; final_dt = last_p2_dt
    elif p2_rsns <= {"T2", "T3"}:
        overall = "Target"; final_px = e3_exit or e2_exit; final_dt = last_p2_dt
    elif "EOD" in p2_rsns and not (p2_rsns & {"T2", "T3"}):
        overall = "T1+EOD"; final_px = last_p2_px; final_dt = last_p2_dt
    else:
        overall = "Target"; final_px = e3_exit or e2_exit or last_p2_px; final_dt = last_p2_dt

    return _build(overall, final_px, final_dt, leg1_exit_px, e2_exit, e2_rsn, e3_exit, e3_rsn)


# ── 3-leg bar simulation ──────────────────────────────────────────────────────

def _simulate_one_bars_3leg(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_bars: pd.DataFrame,
    t1_r: float, t2_r: float, target_r: float,
    t1_action: str,
    tv1: float, tv2: float, tv3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_r: float, pb1_ticks: int,
    pb2_r: float, pb2_ticks: int,
    entry_slip: float, exit_slip: float, stop_offset: int,
    ratchet_r: float = 0.0, ratchet_dest: str = "BE", ratchet_lock_r: float = 0.0,
) -> dict:
    ts      = TICK_SIZE
    is_long = direction == "Long"

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    fill_px     = float(nb["Open"])
    e1_entry    = fill_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts    = abs(e1_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price  = e1_entry + (t1_r     * risk_pts if is_long else -t1_r     * risk_pts)
    t2_price  = e1_entry + (t2_r     * risk_pts if is_long else -t2_r     * risk_pts)
    t3_price  = e1_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar = bar_num_from_dt(nb["DateTime"])
    entry_dt  = nb["DateTime"]

    if is_long:
        pb1_price = max(e1_entry - pb1_r * risk_pts + pb1_ticks * ts, actual_stop + ts)
        pb2_price = max(e1_entry - pb2_r * risk_pts + pb2_ticks * ts, actual_stop + ts)
        pb2_price = min(pb2_price, pb1_price - ts)
    else:
        pb1_price = min(e1_entry + pb1_r * risk_pts - pb1_ticks * ts, actual_stop - ts)
        pb2_price = min(e1_entry + pb2_r * risk_pts - pb2_ticks * ts, actual_stop - ts)
        pb2_price = max(pb2_price, pb1_price + ts)

    active_stop   = actual_stop
    ratchet_fired = False
    pb1_filled    = False
    pb2_filled    = False
    e2_entry_px   = None
    e3_entry_px   = None
    t1_bar_idx    = None
    full_stop_px  = None
    full_stop_dt  = None
    mae = mfe     = 0.0

    def _blended():
        if pb2_filled and e2_entry_px is not None and e3_entry_px is not None:
            tot = tv1 + tv2 + tv3
            return (e1_entry*tv1 + e2_entry_px*tv2 + e3_entry_px*tv3) / tot if tot > 0 else e1_entry
        if pb1_filled and e2_entry_px is not None:
            tot = tv1 + tv2
            return (e1_entry*tv1 + e2_entry_px*tv2) / tot if tot > 0 else e1_entry
        return e1_entry

    def _build(exit_reason, exit_px, exit_dt, leg1_exit_px=None,
               e2_exit=None, e2_rsn=None, e3_exit=None, e3_rsn=None):
        tv_used  = tv1 + (tv2 if pb1_filled else 0.0) + (tv3 if pb2_filled else 0.0)
        l1_ep    = leg1_exit_px if leg1_exit_px is not None else exit_px
        l1_pts   = (l1_ep - e1_entry) if is_long else (e1_entry - l1_ep)
        l1_pnl   = l1_pts / ts * tv1
        l2_ep    = e2_exit if e2_exit is not None else exit_px
        l2_pts   = (l2_ep - e2_entry_px) if (is_long and pb1_filled) else \
                   (e2_entry_px - l2_ep) if (not is_long and pb1_filled) else 0.0
        l2_pnl   = l2_pts / ts * tv2 if pb1_filled else 0.0
        l3_ep    = e3_exit if e3_exit is not None else exit_px
        l3_pts   = (l3_ep - e3_entry_px) if (is_long and pb2_filled) else \
                   (e3_entry_px - l3_ep) if (not is_long and pb2_filled) else 0.0
        l3_pnl   = l3_pts / ts * tv3 if pb2_filled else 0.0
        g_pnl    = l1_pnl + l2_pnl + l3_pnl
        g_pts    = l1_pts + l2_pts + l3_pts
        r_risk   = risk_pts / ts * tv1
        r_ach    = g_pnl / r_risk if r_risk > 0 else 0.0
        ttype    = ("E1+PB1+PB2" if pb2_filled else "E1+PB1" if pb1_filled else "Rocket")
        filled_c = e1c + (e2c if pb1_filled else 0) + (e3c if pb2_filled else 0)
        l1_er    = "T1" if leg1_exit_px is not None else exit_reason
        return {
            "ok": True,
            "SEPrice": signal_price, "FillPrice": fill_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": e1_entry, "ActualStop": actual_stop,
            "Target": t3_price, "Target1": t1_price,
            "RiskPts": risk_pts, "RiskDollar": risk_pts / ts * tv1,
            "ExitTime": pd.Timestamp(exit_dt), "ExitBarNum": bar_num_from_dt(pd.Timestamp(exit_dt)),
            "ExitPrice": exit_px, "ExitReason": exit_reason,
            "GrossPnLPts": g_pts, "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0), "MAE_dollar": max(mae, 0.0) / ts * tv_used,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0), "MFE_dollar": max(mfe, 0.0) / ts * tv_used,
            "MFE_R": max(mfe, 0.0) / risk_pts,
            "SlippagePts": (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * tv_used,
            "Leg1ExitReason": l1_er, "Leg1ExitPrice": l1_ep,
            "Leg1GrossPts": l1_pts,  "Leg1GrossPnL": l1_pnl,
            "Leg2ExitReason": (e2_rsn or exit_reason) if pb1_filled else np.nan,
            "Leg2ExitPrice":  l2_ep if pb1_filled else np.nan,
            "Leg2GrossPts": l2_pts,  "Leg2GrossPnL": l2_pnl,
            "Leg3ExitReason": (e3_rsn or exit_reason) if pb2_filled else np.nan,
            "Leg3ExitPrice":  l3_ep if pb2_filled else np.nan,
            "Leg3GrossPts": l3_pts,  "Leg3GrossPnL": l3_pnl,
            "TradeType": ttype, "BlendedEntry": _blended(),
            "PB1FillPrice": e2_entry_px if pb1_filled else np.nan,
            "PB2FillPrice": e3_entry_px if pb2_filled else np.nan,
            "FilledContracts": filled_c,
        }

    for idx, bar in next_bars.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - e1_entry) if is_long else (e1_entry - lo))
        mae = max(mae, (e1_entry - lo) if is_long else (hi - e1_entry))
        if (lo <= active_stop) if is_long else (hi >= active_stop):
            sp = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            full_stop_px, full_stop_dt = sp, bar["DateTime"]; break
        if not pb1_filled and tv2 > 0:
            if (lo < pb1_price) if is_long else (hi > pb1_price):
                e2_fill = pb1_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e2_fill > actual_stop) or (not is_long and e2_fill < actual_stop):
                    e2_entry_px = e2_fill; pb1_filled = True
        if pb1_filled and not pb2_filled and tv3 > 0:
            if (lo < pb2_price) if is_long else (hi > pb2_price):
                e3_fill = pb2_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e3_fill > actual_stop) or (not is_long and e3_fill < actual_stop):
                    e3_entry_px = e3_fill; pb2_filled = True
        if ratchet_r > 0.0 and not ratchet_fired:
            bl    = _blended()
            favor = (hi - bl) if is_long else (bl - lo)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (bl + lk) if is_long else (bl - lk)
                elif ratchet_dest == "E1":
                    active_stop = e1_entry
                else:
                    active_stop = _blended()
                ratchet_fired = True
        if (hi > t1_price) if is_long else (lo < t1_price):
            t1_bar_idx = idx; break

    if full_stop_px is not None:
        return _build("Stop", full_stop_px, full_stop_dt)
    if t1_bar_idx is None:
        last   = next_bars.iloc[-1]
        eod_px = float(last["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, last["DateTime"])

    leg1_exit_px = None
    if t1_action == "exit":
        leg1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)

    be_stop_p2 = _blended()
    phase2     = next_bars[next_bars.index >= t1_bar_idx].reset_index(drop=True)
    last2      = phase2.iloc[-1]
    last_p2_px = float(last2["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
    last_p2_dt = last2["DateTime"]

    e2_done = not pb1_filled; e3_done = not pb2_filled
    e2_exit = None; e2_rsn = None
    e3_exit = None; e3_rsn = None
    be_px   = None; be_dt  = None

    for j, (_, bar2) in enumerate(phase2.iterrows()):
        hi2, lo2 = float(bar2["High"]), float(bar2["Low"])
        mfe = max(mfe, (hi2 - e1_entry) if is_long else (e1_entry - lo2))
        mae = max(mae, (e1_entry - lo2) if is_long else (hi2 - e1_entry))
        if j == 0: continue
        if (lo2 <= be_stop_p2) if is_long else (hi2 >= be_stop_p2):
            sp2 = be_stop_p2 + (-exit_slip * ts if is_long else exit_slip * ts)
            if not e2_done: e2_exit = sp2; e2_rsn = "BE"; e2_done = True
            if not e3_done: e3_exit = sp2; e3_rsn = "BE"; e3_done = True
            be_px = sp2; be_dt = bar2["DateTime"]; break
        if not e2_done and ((hi2 > t2_price) if is_long else (lo2 < t2_price)):
            e2_exit = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e2_rsn = "T2"; e2_done = True
        if not e3_done and ((hi2 > t3_price) if is_long else (lo2 < t3_price)):
            e3_exit = t3_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e3_rsn = "T3"; e3_done = True
        if e2_done and e3_done: break

    if not e2_done: e2_exit = last_p2_px; e2_rsn = "EOD"
    if not e3_done: e3_exit = last_p2_px; e3_rsn = "EOD"

    p2_rsns = {r for r in [e2_rsn if pb1_filled else None,
                            e3_rsn if pb2_filled else None] if r}
    if be_px is not None:
        overall = "T1+BE"; final_px = be_px; final_dt = be_dt
    elif not p2_rsns:
        overall = "Target"; final_px = leg1_exit_px or last_p2_px; final_dt = last_p2_dt
    elif p2_rsns <= {"T2", "T3"}:
        overall = "Target"; final_px = e3_exit or e2_exit; final_dt = last_p2_dt
    elif "EOD" in p2_rsns and not (p2_rsns & {"T2", "T3"}):
        overall = "T1+EOD"; final_px = last_p2_px; final_dt = last_p2_dt
    else:
        overall = "Target"; final_px = e3_exit or e2_exit or last_p2_px; final_dt = last_p2_dt

    return _build(overall, final_px, final_dt, leg1_exit_px, e2_exit, e2_rsn, e3_exit, e3_rsn)


# ── Bar-level dispatch (used by alt-path mismatch analysis) ──────────────────

def _resimulate_bars(mode: str, sig_dt, direction: str, signal_price: float, stop_csv: float,
                     day_bars: pd.DataFrame, p: dict) -> dict:
    if mode == "3leg":
        return _simulate_one_bars_3leg(
            sig_dt, direction, signal_price, stop_csv, day_bars,
            p["t1_r"], p["t2_r"], p["target_r"], p["t1_action"],
            p["tv_e1"], p["tv_e2"], p["tv_e3"],
            p["contracts_e1"], p["contracts_e2"], p["contracts_e3"],
            p["pb1_r"], p["pb1_ticks"], p["pb2_r"], p["pb2_ticks"],
            p["entry_slip"], p["exit_slip"], p["stop_offset"],
            p["ratchet_r"], p["ratchet_dest"], p["ratchet_lock_r"],
        )
    elif mode == "multileg":
        return _simulate_one_bars_multileg(
            sig_dt, direction, signal_price, stop_csv, day_bars,
            p["target_r"], p["t1_r"], p["t1_action"],
            p["entry_slip"], p["exit_slip"], p["stop_offset"],
            p["tv1"], p["tv2"],
            p["ratchet_r"], p["ratchet_dest"], p["ratchet_lock_r"],
            e2_pb_r=p["ml_pb_r"], e2_pb_ticks=p["ml_pb_ticks"],
        )
    else:
        return _simulate_one_bars(
            sig_dt, direction, signal_price, stop_csv, day_bars,
            p["target_r"], p["entry_slip"], p["exit_slip"], p["stop_offset"], p["tv"],
            p["ratchet_r"], p["ratchet_dest"], p["ratchet_lock_r"],
        )


# ── Main simulation entry point ───────────────────────────────────────────────

def simulate_trades(
    signals: pd.DataFrame,
    ticks_by_date: dict,
    target_r: float,
    entry_slip: float,
    exit_slip: float,
    stop_offset: int,
    tick_value: float,
    contracts: int,
    commission: float,
    overrides: dict | None = None,
    bars_by_date: dict | None = None,
    multileg: bool = False,
    t1_r: float = 1.0,
    t1_action: str = "exit",
    contracts_t1: int = 1,
    contracts_t2: int = 1,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    ml_pb_r: float = 0.0,
    ml_pb_ticks: int = 0,
    threeleg: bool = False,
    contracts_e1: int = 1,
    contracts_e2: int = 1,
    contracts_e3: int = 1,
    pb1_r: float = 0.5,
    pb1_ticks: int = 0,
    pb2_r: float = 1.0,
    pb2_ticks: int = 0,
    t2_r: float = 0.0,
    scale_in_style: str = "e2",
    pb_round: str = "floor_ceil",
    _force_loop: bool = False,
) -> pd.DataFrame:
    _t2_r = t2_r if t2_r > 0 else target_r
    tv    = tick_value * contracts
    tv1   = tick_value * contracts_t1
    tv2   = tick_value * contracts_t2
    tv_e1 = tick_value * contracts_e1
    tv_e2 = tick_value * contracts_e2
    tv_e3 = tick_value * contracts_e3
    rows  = []

    for _, sig in signals.iterrows():
        base = sig.to_dict()
        base["TargetR"] = target_r
        base.update(_EMPTY_TRADE)
        if multileg:
            base["T1_R"] = t1_r
            base["PB_R"] = ml_pb_r if ml_pb_r < 0 else np.nan
        base["FilterStatus"] = sig.get("FilterStatus", "ok")

        manual_fill = (overrides or {}).get(int(base.get("SignalNum", -1)))

        if base["FilterStatus"] != "ok" and not manual_fill:
            rows.append(base)
            continue

        day_ticks = ticks_by_date.get(base["Date"])
        no_ticks  = day_ticks is None or day_ticks.empty

        if no_ticks and not manual_fill:
            base["FilterStatus"] = "no_tick_data"; rows.append(base); continue

        if threeleg and not manual_fill:
            res = _simulate_one_3leg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, t1_r, _t2_r, target_r, t1_action,
                    tv_e1, tv_e2, tv_e3, contracts_e1, contracts_e2, contracts_e3,
                    pb1_r, pb1_ticks, pb2_r, pb2_ticks,
                    entry_slip, exit_slip, stop_offset,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                )
        elif multileg and not manual_fill:
            res = _simulate_one_multileg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, target_r, t1_r, t1_action,
                    entry_slip, exit_slip, stop_offset, tv1, tv2,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                    ml_pb_r=ml_pb_r, ml_pb_ticks=ml_pb_ticks,
                    scale_in_style=scale_in_style, pb_round=pb_round, _force_loop=_force_loop,
                )
        else:
                res = _simulate_one(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, target_r, entry_slip, exit_slip, stop_offset, tv,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                    manual_fill=manual_fill, _force_loop=_force_loop,
                )

        if not res.get("ok", False):
            base["FilterStatus"] = res.get("FilterStatus", "no_fill")
            rows.append(base)
            continue

        for k, v in res.items():
            if k != "ok" and k != "FilledContracts":
                base[k] = v
        base["Filled"] = True
        if threeleg and not manual_fill:
            _comm = commission * res.get("FilledContracts", contracts_e1)
        elif multileg and not manual_fill:
            _e2_traded = str(base.get("Leg2ExitReason", "NoFill")) != "NoFill"
            _active_c  = (contracts_t1 + contracts_t2) if _e2_traded else contracts_t1
            _comm = commission * _active_c
        else:
            _comm = commission * contracts
        base["NetPnL"] = base["GrossPnL"] - _comm
        if manual_fill:
            base["FilterStatus"] = "manual_override"
        rows.append(base)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    filled_mask = df["Filled"] == True
    df["CumPF"] = np.nan
    if filled_mask.any():
        g_pnl    = df.loc[filled_mask, "GrossPnL"]
        cum_wins = g_pnl.clip(lower=0).cumsum()
        cum_loss = g_pnl.clip(upper=0).cumsum().abs()
        df.loc[filled_mask, "CumPF"] = (cum_wins / cum_loss.replace(0, np.nan)).values

    # Concurrent risk: at each trade's entry, sum RiskDollar of all simultaneously open trades.
    # Peak concurrent risk always falls at an entry moment (exits only decrease it).
    df["ConcurrentRiskDollar"] = np.nan
    if filled_mask.any():
        f = df.loc[filled_mask, ["EntryTime", "ExitTime", "RiskDollar"]].copy()
        et_arr = f["EntryTime"].values
        ex_arr = f["ExitTime"].values
        rd_arr = f["RiskDollar"].values
        concurrent = np.empty(len(f))
        for i in range(len(f)):
            t = et_arr[i]
            open_mask = (et_arr <= t) & (ex_arr > t)
            concurrent[i] = rd_arr[open_mask].sum()
        df.loc[filled_mask, "ConcurrentRiskDollar"] = concurrent

    return df


# ── Summary metrics ───────────────────────────────────────────────────────────

def _compute_prom(filled: pd.DataFrame, max_dd: float) -> float:
    """Pardo's Pessimistic Return on Margin.
    Applies a 1/√N reliability penalty to both the win and loss sides,
    then divides by absolute max drawdown. Returns nan when no drawdown."""
    if max_dd >= 0:
        return float("nan")
    wins = filled.loc[filled["GrossPnL"] > 0, "GrossPnL"]
    loss = filled.loc[filled["GrossPnL"] < 0, "GrossPnL"]
    nw, nl = len(wins), len(loss)
    gw = wins.sum() if nw > 0 else 0.0
    gl = abs(loss.sum()) if nl > 0 else 0.0
    w_factor = (1.0 - 1.0 / np.sqrt(nw)) if nw > 0 else 0.0
    l_factor = (1.0 + 1.0 / np.sqrt(nl)) if nl > 0 else 1.0
    return (gw * w_factor - gl * l_factor) / abs(max_dd)


def compute_summary(results: pd.DataFrame, commission: float,
                    contracts: int = 1,
                    is_multileg: bool = False, t1_action: str = "exit",
                    contracts_t1: int = 1, contracts_t2: int = 1) -> dict:
    if results.empty:
        return {}
    filled = results[results["Filled"] == True]
    if filled.empty:
        return {}

    n_total    = len(results)
    n_filtered = int((results["FilterStatus"] != "ok").sum())
    n_no_fill  = int(results["FilterStatus"].isin(
        ["no_fill", "no_next_bar", "no_tick_data", "zero_risk"]).sum())
    n_trades   = len(filled)

    _tgt_mask  = (
        filled["ExitReason"].str.contains("Target", na=False) |
        filled["ExitReason"].isin(["T1+BE", "T1_only"])
    )
    _stop_mask = filled["ExitReason"].isin(["Stop", "E1E2+Stop"])
    _eod_mask  = ~_tgt_mask & ~_stop_mask

    _eod_w = _eod_mask & (filled["NetPnL"] > 0)
    _eod_l = _eod_mask & (filled["NetPnL"] < 0)
    _eod_b = _eod_mask & (filled["NetPnL"] == 0)

    wins   = filled[_tgt_mask  | _eod_w]
    stops  = filled[_stop_mask | _eod_l]
    sess   = filled[_eod_b]
    n_wins = len(wins)
    n_stop = len(stops)
    n_sess = len(sess)
    win_pct = n_wins / n_trades * 100 if n_trades else 0

    gross_total = filled["GrossPnL"].sum()
    net_total   = filled["NetPnL"].sum()

    pos_pnl = filled.loc[filled["GrossPnL"] > 0, "GrossPnL"].sum()
    neg_pnl = filled.loc[filled["GrossPnL"] < 0, "GrossPnL"].sum()
    pf = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else (float("inf") if pos_pnl > 0 else 0)

    exp_dollar = filled["NetPnL"].mean()
    exp_r      = filled["R_achieved"].mean()
    avg_win    = wins["NetPnL"].mean()   if n_wins else 0
    avg_loss   = stops["NetPnL"].mean()  if n_stop else 0
    wl_ratio   = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    equity       = filled.sort_values(["Date", "EntryTime"])["NetPnL"].cumsum()
    peak         = equity.cummax()
    max_dd       = float((equity - peak).min())
    trading_days = int(filled["Date"].nunique())

    r_vals = filled["R_achieved"].dropna().values
    r_std  = float(np.std(r_vals, ddof=1)) if len(r_vals) > 1 else 0.0

    n_sqn = min(n_trades, 100)
    sqn   = float(exp_r / r_std * np.sqrt(n_sqn)) if r_std > 0 else 0.0

    median_win  = float(wins["NetPnL"].median())  if n_wins else 0.0
    median_loss = float(stops["NetPnL"].median()) if n_stop else 0.0

    exp_r_ci_lo = exp_r_ci_hi = np.nan
    if len(r_vals) >= 5:
        rng  = np.random.default_rng(42)
        boot = rng.choice(r_vals, size=(2000, len(r_vals)), replace=True).mean(axis=1)
        exp_r_ci_lo = float(np.percentile(boot, 2.5))
        exp_r_ci_hi = float(np.percentile(boot, 97.5))

    pnl_dd = net_total / abs(max_dd) if max_dd < 0 else float("nan")
    prom   = _compute_prom(filled, max_dd)

    return dict(
        n_total=n_total, n_filtered=n_filtered, n_no_fill=n_no_fill,
        n_trades=n_trades, n_wins=n_wins, n_stop=n_stop, n_sess=n_sess,
        win_pct=win_pct, gross_total=gross_total, net_total=net_total,
        pf=pf, exp_dollar=exp_dollar, exp_r=exp_r,
        avg_win=avg_win, avg_loss=avg_loss, wl_ratio=wl_ratio,
        median_win=median_win, median_loss=median_loss,
        r_std=r_std, sqn=sqn,
        exp_r_ci_lo=exp_r_ci_lo, exp_r_ci_hi=exp_r_ci_hi,
        avg_mae_pts=filled["MAE_pts"].mean(), avg_mfe_pts=filled["MFE_pts"].mean(),
        avg_mae_R=filled["MAE_R"].mean(),     avg_mfe_R=filled["MFE_R"].mean(),
        largest_win=wins["NetPnL"].max()    if n_wins else 0,
        largest_loss=stops["NetPnL"].min()  if n_stop else 0,
        commission_total=n_trades * commission * ((contracts_t1 + contracts_t2) if is_multileg else contracts),
        slippage_total=float(filled["SlippageDollar"].sum()) if "SlippageDollar" in filled.columns else 0.0,
        max_dd=max_dd, trading_days=trading_days,
        max_risk_dollar=float(filled["RiskDollar"].max()) if "RiskDollar" in filled.columns else 0.0,
        avg_risk_dollar=float(filled["RiskDollar"].mean()) if "RiskDollar" in filled.columns else 0.0,
        max_concurrent_risk_dollar=float(filled["ConcurrentRiskDollar"].max()) if "ConcurrentRiskDollar" in filled.columns else 0.0,
        pnl_dd=pnl_dd,
        prom=prom,
    )
