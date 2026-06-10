import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pathlib import Path

from data_loader import load_sc_bars, load_sc_ticks, get_market_holidays, TICK_SIZE, bar_num_from_dt
from economic_calendar import get_economic_events, fred_key_configured, EVENT_COLOR

_BA_DEFAULTS_FILE = Path(__file__).parent / "ba_filter_defaults.json"

INSTRUMENTS = {
    "ES":  {"tick_value": 12.50, "label": "ES  ($12.50/tick)", "default_commission": 3.0},
    "MES": {"tick_value":  1.25, "label": "MES ($1.25/tick)",  "default_commission": 1.0},
}
RTH_END_MIN = 15 * 60 + 15  # 915


def _load_ba_defaults() -> dict:
    if _BA_DEFAULTS_FILE.exists():
        try:
            return json.loads(_BA_DEFAULTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_ba_defaults(d: dict):
    _BA_DEFAULTS_FILE.write_text(json.dumps(d, indent=2))


# ── CSV parser ────────────────────────────────────────────────────────────────

def parse_signals(raw: str) -> pd.DataFrame | None:
    """Parse MC signals text.
    Format: Num  Type  Dir  DD/MM/YYYY  HH:MM:SS  BarNum  Price  Stop
    """
    rows = []
    for line in raw.strip().splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            rows.append({
                "SignalNum":   int(parts[0]),
                "SignalType":  parts[1],
                "Direction":   parts[2],
                "DateTime":    pd.to_datetime(f"{parts[3]} {parts[4]}", dayfirst=True),
                "BarNum":      int(parts[5]),
                "SignalPrice": float(parts[6].replace(",", "")),
                "StopPrice":   float(parts[7].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["Date"] = df["DateTime"].dt.date
    return df.sort_values("SignalNum").reset_index(drop=True)


# ── Filter logic ──────────────────────────────────────────────────────────────

def apply_signal_filters(
    signals: pd.DataFrame,
    date_from, date_to,
    excl_holidays: bool,
    incl_dow: list,          # [mon, tue, wed, thu, fri]
    excl_first_n: int,
    excl_last_min: int,
    event_types: tuple,
    event_filter_mode: str,
    event_window: int,
    incl_cc1: bool,
    incl_cc2: bool,
    incl_cc3: bool,
    incl_cc4: bool,
    incl_cc5: bool,
    direction: str,          # "Both", "Long", "Short"
) -> pd.DataFrame:
    df = signals.copy()
    df["FilterStatus"] = "ok"

    # Date range
    df.loc[(df["Date"] < date_from) | (df["Date"] > date_to), "FilterStatus"] = "date_range"

    # Signal type
    for stype, incl in [("CC1", incl_cc1), ("CC2", incl_cc2), ("CC3", incl_cc3), ("CC4", incl_cc4), ("CC5", incl_cc5)]:
        if not incl:
            df.loc[(df["FilterStatus"] == "ok") & (df["SignalType"] == stype),
                   "FilterStatus"] = "signal_type"

    # Direction
    if direction != "Both":
        df.loc[(df["FilterStatus"] == "ok") & (df["Direction"] != direction),
               "FilterStatus"] = "direction"

    # NYSE holidays
    if excl_holidays:
        hols = get_market_holidays(str(date_from), str(date_to))
        hol_mask = df["DateTime"].dt.strftime("%Y-%m-%d").isin(hols)
        df.loc[(df["FilterStatus"] == "ok") & hol_mask, "FilterStatus"] = "holiday"

    # Day of week
    dow_map  = {i: v for i, v in enumerate(incl_dow)}
    excl_dow = ~df["DateTime"].dt.dayofweek.map(dow_map).fillna(False)
    df.loc[(df["FilterStatus"] == "ok") & excl_dow, "FilterStatus"] = "dow"

    # Session: first N bars  (BarNum is 1-indexed session bar; signal time = bar close)
    if excl_first_n > 0:
        df.loc[(df["FilterStatus"] == "ok") & (df["BarNum"] <= excl_first_n),
               "FilterStatus"] = "first_bars"

    # Session: last N minutes
    if excl_last_min > 0:
        cutoff_min  = RTH_END_MIN - excl_last_min
        cutoff_time = pd.Timestamp(f"{cutoff_min // 60:02d}:{cutoff_min % 60:02d}:00").time()
        late_mask   = df["DateTime"].dt.time >= cutoff_time
        df.loc[(df["FilterStatus"] == "ok") & late_mask, "FilterStatus"] = "last_bars"

    # Economic events
    if event_types:
        events_df = get_economic_events(event_types, str(date_from), str(date_to))
        if not events_df.empty:
            if event_filter_mode == "Skip full day":
                ev_dates = set(events_df["DateTime"].dt.date)
                df.loc[(df["FilterStatus"] == "ok") & df["Date"].isin(ev_dates),
                       "FilterStatus"] = "event"
            else:
                ev_mask = pd.Series(False, index=df.index)
                for _, ev in events_df.iterrows():
                    dt = ev["DateTime"]
                    ev_mask |= (
                        (df["DateTime"] >= dt - pd.Timedelta(minutes=event_window)) &
                        (df["DateTime"] <= dt + pd.Timedelta(minutes=event_window))
                    )
                df.loc[(df["FilterStatus"] == "ok") & ev_mask, "FilterStatus"] = "event"

    return df


# ── Trade simulation ──────────────────────────────────────────────────────────

# bar_num_from_dt imported from data_loader — shared with app.py


def _simulate_one(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_ticks: pd.DataFrame,
    target_r: float, entry_slip: int, exit_slip: int, stop_offset: int, tv: float,
    ratchet_r: float = 0.0,       # 0 = disabled; >0 = trigger R from entry
    ratchet_dest: str = "BE",     # "BE" | "E1" | "Lock-in"
    ratchet_lock_r: float = 0.0,  # lock-in R (only used when dest="Lock-in")
    manual_fill: dict | None = None,   # {"fill_price": float, "fill_bar": int}
) -> dict:
    from data_loader import RTH_START_MIN
    ts      = TICK_SIZE
    is_long = direction == "Long"

    after = day_ticks[day_ticks["DateTime"] > sig_dt]
    if after.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    if manual_fill is not None:
        # Manual override: bypass fill check, start scan from the specified bar
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
        # Scan ALL ticks for first qualifying tick (stop order: ticks through signal price)
        qualifying = after[after["Price"] >= signal_price] if is_long else after[after["Price"] <= signal_price]
        if qualifying.empty:
            return {"ok": False, "FilterStatus": "no_fill"}
        fill_tick     = qualifying.iloc[0]
        first_tick_px = fill_tick["Price"]
        entry_dt      = fill_tick["DateTime"]
        # Exit scan starts at fill tick
        after  = after[after["DateTime"] >= fill_tick["DateTime"]]
        prices = after["Price"].values
        times  = after["DateTime"].values

    # Actual entry = fill price ± entry slippage
    actual_entry = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)

    # Actual stop = CSV stop ± stop_offset ticks (one extra tick beyond level)
    actual_stop = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)

    risk_pts = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    target_price = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar    = bar_num_from_dt(entry_dt)

    # Scan for exit + MAE/MFE

    exit_px_raw   = float(prices[-1])
    exit_dt_raw   = times[-1]
    exit_reason   = "Session"
    mae = mfe     = 0.0
    active_stop   = actual_stop
    ratchet_fired = False

    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - actual_entry) if is_long else (actual_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)

        if i == 0:
            continue  # entry tick — no exit check on entry itself

        # Stop ratchet
        if ratchet_r > 0.0 and not ratchet_fired:
            favor = (p - actual_entry) if is_long else (actual_entry - p)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                else:  # "BE" or "E1" — same for single-leg
                    active_stop = actual_entry
                ratchet_fired = True

        if is_long:
            if p >= target_price:
                exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                break
            if p <= active_stop:
                exit_px_raw, exit_dt_raw, exit_reason = active_stop, t, "Stop"
                break
        else:
            if p <= target_price:
                exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                break
            if p >= active_stop:
                exit_px_raw, exit_dt_raw, exit_reason = active_stop, t, "Stop"
                break

    # Exit fill = theoretical exit ± exit slippage (always adverse)
    actual_exit  = exit_px_raw + (-exit_slip * ts if is_long else exit_slip * ts)
    exit_dt_ts   = pd.Timestamp(exit_dt_raw)
    exit_bar     = bar_num_from_dt(exit_dt_ts)

    gross_pts       = (actual_exit - actual_entry) if is_long else (actual_entry - actual_exit)
    gross_pnl       = gross_pts / ts * tv
    r_achieved      = gross_pts / risk_pts
    slippage_pts    = (entry_slip + exit_slip) * ts
    slippage_dollar = (entry_slip + exit_slip) * tv

    exit_label = "EOD" if exit_reason == "Session" else exit_reason

    return {
        "ok":          True,
        "SEPrice":     signal_price,          # stop-entry level (signal bar close)
        "FillPrice":   first_tick_px,         # first qualifying tick, pre-slippage
        "EntryTime":   pd.Timestamp(entry_dt),
        "EntryBarNum": entry_bar,
        "EntryPrice":  actual_entry,          # fill price ± entry slippage
        "ActualStop":  actual_stop,
        "Target":      target_price,
        "RiskPts":     risk_pts,
        "RiskDollar":  risk_pts / ts * tv,
        "ExitTime":    exit_dt_ts,
        "ExitBarNum":  exit_bar,
        "ExitPrice":   actual_exit,
        "ExitReason":  exit_label,
        "GrossPnLPts": gross_pts,
        "GrossPnL":    gross_pnl,
        "R_achieved":  r_achieved,
        "MAE_pts":        mae,
        "MAE_dollar":     mae / ts * tv,
        "MAE_R":          mae / risk_pts,
        "MFE_pts":        mfe,
        "MFE_dollar":     mfe / ts * tv,
        "MFE_R":          mfe / risk_pts,
        "SlippagePts":    slippage_pts,
        "SlippageDollar": slippage_dollar,
    }


def _simulate_one_bars(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_bars: pd.DataFrame,
    target_r: float, entry_slip: int, exit_slip: int, stop_offset: int, tv: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
) -> dict:
    """Bar-level fill simulation — used when tick data is unavailable.
    Entry: stop order triggers if next bar's H/L reaches signal price.
    Fill: max(Open, signal_price) for Long (handles gap-open above signal).
    Exit scan: conservative — if both stop and target reachable in same bar, stop wins."""
    ts      = TICK_SIZE
    is_long = direction == "Long"

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    if is_long  and float(nb["High"]) < signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}
    if not is_long and float(nb["Low"]) > signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}

    fill_px      = max(float(nb["Open"]), signal_price) if is_long else min(float(nb["Open"]), signal_price)
    actual_entry = fill_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    target_price = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar    = bar_num_from_dt(nb["DateTime"])
    entry_dt     = nb["DateTime"]

    exit_px_raw      = float(next_bars.iloc[-1]["Close"])
    exit_dt_raw      = next_bars.iloc[-1]["DateTime"]
    exit_reason      = "Session"
    mae = mfe        = 0.0
    active_stop      = actual_stop
    ratchet_fired    = False
    same_bar_conflict = False   # True when stop AND target both reachable in same bar

    for _, bar in next_bars.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - actual_entry) if is_long else (actual_entry - lo))
        mae = max(mae, (actual_entry - lo) if is_long else (hi - actual_entry))

        # Stop ratchet (bar-level: trigger based on bar high/low in favor direction)
        if ratchet_r > 0.0 and not ratchet_fired:
            favor = (hi - actual_entry) if is_long else (actual_entry - lo)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                else:
                    active_stop = actual_entry
                ratchet_fired = True

        hit_tgt  = (hi >= target_price) if is_long else (lo <= target_price)
        hit_stop = (lo <= active_stop)  if is_long else (hi >= active_stop)

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
        "ok":               True,
        "SEPrice":          signal_price,
        "FillPrice":        fill_px,
        "EntryTime":        pd.Timestamp(entry_dt),
        "EntryBarNum":      entry_bar,
        "EntryPrice":       actual_entry,
        "ActualStop":       actual_stop,
        "Target":           target_price,
        "RiskPts":          risk_pts,
        "RiskDollar":       risk_pts / ts * tv,
        "ExitTime":         exit_dt_ts,
        "ExitBarNum":       exit_bar,
        "ExitPrice":        actual_exit,
        "ExitReason":       "EOD" if exit_reason == "Session" else exit_reason,
        "GrossPnLPts":      gross_pts,
        "GrossPnL":         gross_pnl,
        "R_achieved":       r_achieved,
        "MAE_pts":          max(mae, 0.0),
        "MAE_dollar":       max(mae, 0.0) / ts * tv,
        "MAE_R":            max(mae, 0.0) / risk_pts,
        "MFE_pts":          max(mfe, 0.0),
        "MFE_dollar":       max(mfe, 0.0) / ts * tv,
        "MFE_R":            max(mfe, 0.0) / risk_pts,
        "SlippagePts":      slippage_pts,
        "SlippageDollar":   slippage_dollar,
        "SameBarConflict":  same_bar_conflict,
    }


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
) -> dict:
    """Tick-level 2-leg simulation.
    t1_action='exit'    — Leg1 exits at T1, BE stop set for Leg2.
    t1_action='be_only' — T1 level just moves stop to BE, full position continues (tv1=0).
    Phase 1: T1 wins over Stop at same tick. Phase 2: T2 wins over BE at same tick."""
    from data_loader import RTH_START_MIN
    ts       = TICK_SIZE
    is_long  = direction == "Long"
    tv_total = tv1 + tv2

    after = day_ticks[day_ticks["DateTime"] > sig_dt]
    if after.empty:
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
        qualifying = after[after["Price"] >= signal_price] if is_long else after[after["Price"] <= signal_price]
        if qualifying.empty:
            return {"ok": False, "FilterStatus": "no_fill"}
        fill_tick     = qualifying.iloc[0]
        first_tick_px = fill_tick["Price"]
        entry_dt      = fill_tick["DateTime"]
        after         = after[after["DateTime"] >= fill_tick["DateTime"]]
        prices        = after["Price"].values
        times         = after["DateTime"].values

    actual_entry = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price  = actual_entry + (t1_r     * risk_pts if is_long else -t1_r     * risk_pts)
    t2_price  = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_bar = bar_num_from_dt(entry_dt)
    mae = mfe = 0.0

    def _leg_pts(exit_px):
        return (exit_px - actual_entry) if is_long else (actual_entry - exit_px)

    def _build(exit_reason, exit_price, exit_dt, leg1_er, leg1_px, leg2_er, leg2_px):
        l1_pts = _leg_pts(leg1_px) if leg1_px is not None else 0.0
        l2_pts = _leg_pts(leg2_px)
        l1_pnl = l1_pts / ts * tv1
        l2_pnl = l2_pts / ts * tv2
        g_pnl  = l1_pnl + l2_pnl
        g_pts  = l1_pts + l2_pts
        r_ach  = g_pnl / (risk_pts / ts * tv_total) if tv_total > 0 else 0.0
        edt    = pd.Timestamp(exit_dt)
        return {
            "ok": True,
            "SEPrice": signal_price,    "FillPrice": first_tick_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": actual_entry, "ActualStop": actual_stop,
            "Target": t2_price,         "Target1": t1_price,
            "RiskPts": risk_pts,        "RiskDollar": risk_pts / ts * tv_total,
            "ExitTime": edt,            "ExitBarNum": bar_num_from_dt(edt),
            "ExitPrice": exit_price,    "ExitReason": exit_reason,
            "GrossPnLPts": g_pts,       "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0),   "MAE_dollar": max(mae, 0.0) / ts * tv_total,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0),   "MFE_dollar": max(mfe, 0.0) / ts * tv_total,
            "MFE_R": max(mfe, 0.0) / risk_pts,
            "SlippagePts": (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * tv_total,
            "Leg1ExitReason": leg1_er if leg1_px is not None else np.nan,
            "Leg1ExitPrice":  leg1_px if leg1_px is not None else np.nan,
            "Leg1GrossPts": l1_pts, "Leg1GrossPnL": l1_pnl,
            "Leg2ExitReason": leg2_er, "Leg2ExitPrice": leg2_px,
            "Leg2GrossPts": l2_pts, "Leg2GrossPnL": l2_pnl,
        }

    # ── Phase 1: scan for Stop (all contracts) or T1 level ────────────────────
    phase1_end_idx  = None
    leg1_exit_price = None
    full_stop_price = None
    full_stop_dt    = None
    active_stop     = actual_stop
    ratchet_fired   = False

    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - actual_entry) if is_long else (actual_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if i == 0:
            continue

        # Stop ratchet (Phase 1 only; Phase 2 BE stop takes over after T1)
        if ratchet_r > 0.0 and not ratchet_fired:
            favor = (p - actual_entry) if is_long else (actual_entry - p)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (actual_entry + lk) if is_long else (actual_entry - lk)
                else:  # "BE" or "E1"
                    active_stop = actual_entry
                ratchet_fired = True

        hit_t1   = (p >= t1_price)   if is_long else (p <= t1_price)
        hit_stop = (p <= active_stop) if is_long else (p >= active_stop)
        if hit_t1:
            if t1_action == "exit":
                leg1_exit_price = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            # be_only: leg1_exit_price stays None (no Leg1 exit, just move BE)
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

    # ── Phase 2: Leg2 / full position with BE stop ────────────────────────────
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
        hit_t2 = (p2v >= t2_price) if is_long else (p2v <= t2_price)
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


def _simulate_one_bars_multileg(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_bars: pd.DataFrame,
    target_r: float, t1_r: float, t1_action: str,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tv1: float, tv2: float,
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    e2_pb_r: float = 0.0,    # R from E1 entry where E2 fills (0 = fills immediately at T1)
    e2_pb_ticks: int = 0,    # additional tick offset applied to the PB level
) -> dict:
    """Bar-level 2-leg simulation. Conservative: stop wins over T1 (Phase 1); BE wins over T2 (Phase 2).
    When e2_pb_r > 0, E2 only fills after price retraces to that level from T1."""
    ts       = TICK_SIZE
    is_long  = direction == "Long"
    tv_total = tv1 + tv2

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    if is_long  and float(nb["High"]) < signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}
    if not is_long and float(nb["Low"]) > signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}

    fill_px      = max(float(nb["Open"]), signal_price) if is_long else min(float(nb["Open"]), signal_price)
    actual_entry_raw = fill_px + (entry_slip * ts if is_long else -entry_slip * ts)
    actual_entry = round(round(actual_entry_raw / ts) * ts, 10)
    actual_stop  = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)
    risk_pts     = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    t1_price  = actual_entry + (t1_r * risk_pts if is_long else -t1_r * risk_pts)
    t2_price  = t1_price  # placeholder; overwritten after E2 fills using blended-entry R
    entry_bar = bar_num_from_dt(nb["DateTime"])
    entry_dt  = nb["DateTime"]
    mae = mfe = 0.0

    # e2_entry / e2_fill_dt / blended_entry / blended_risk: updated when PB fills.
    e2_entry      = actual_entry
    e2_fill_dt    = None
    blended_entry = np.nan
    blended_risk  = np.nan

    def _leg_pts(exit_px):
        return (exit_px - actual_entry) if is_long else (actual_entry - exit_px)

    def _leg2_pts(exit_px):
        return (exit_px - e2_entry) if is_long else (e2_entry - exit_px)

    same_bar_conflict = False  # set True when stop+T1 OR BE+T2 both reachable same bar

    def _build(exit_reason, exit_price, exit_dt, leg1_er, leg1_px, leg2_er, leg2_px):
        l1_pts = _leg_pts(leg1_px) if leg1_px is not None else 0.0
        l2_pts = _leg2_pts(leg2_px) if leg2_px is not None else 0.0
        l1_pnl = l1_pts / ts * tv1
        l2_pnl = l2_pts / ts * tv2
        g_pnl  = l1_pnl + l2_pnl
        g_pts  = l1_pts + l2_pts
        # Use only tv1 when E2 never filled (T1_only / Stop before E2 / EOD before E2)
        _e2_filled = (leg2_er not in ("NoFill", None))
        _tv_active = tv_total if _e2_filled else tv1
        # True combined stop-out risk: blended_risk×tv_total = E1_risk×tv1 + E2_risk×tv2
        _risk_dollar = (blended_risk / ts * tv_total
                        if (_e2_filled and not (isinstance(blended_risk, float) and np.isnan(blended_risk)))
                        else risk_pts / ts * tv1)
        # R always expressed as multiples of E1's original 1R (standardised basis)
        _e1_risk_dollar = risk_pts / ts * tv1
        r_ach  = g_pnl / _e1_risk_dollar if _e1_risk_dollar > 0 else 0.0
        edt    = pd.Timestamp(exit_dt)
        return {
            "ok": True,
            "SEPrice": signal_price,    "FillPrice": fill_px,
            "EntryTime": pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": actual_entry, "ActualStop": actual_stop,
            "Target": t2_price,         "Target1": t1_price,
            "RiskPts": risk_pts,        "RiskDollar": _risk_dollar,
            "ExitTime": edt,            "ExitBarNum": bar_num_from_dt(edt),
            "ExitPrice": exit_price,    "ExitReason": exit_reason,
            "GrossPnLPts": g_pts,       "GrossPnL": g_pnl,
            "R_achieved": r_ach,
            "MAE_pts": max(mae, 0.0),   "MAE_dollar": max(mae, 0.0) / ts * _tv_active,
            "MAE_R": max(mae, 0.0) / risk_pts,
            "MFE_pts": max(mfe, 0.0),   "MFE_dollar": max(mfe, 0.0) / ts * _tv_active,
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

    # ── Phase 1: Stop or T1 ───────────────────────────────────────────────────
    t1_bar_idx      = None
    leg1_exit_price = None
    full_stop_price = None
    full_stop_dt    = None
    active_stop     = actual_stop
    # ── Pre-compute PB trigger (if scale-in enabled) ──────────────────────────
    # PB is negative R from E1 entry (a dip below entry before T1 is reached).
    # e2_pb_r = -0.5 → PB = entry - 0.5R (for long)
    use_pb       = e2_pb_r < 0
    pb_trigger   = None
    pb_level_raw = np.nan   # exact R-based level before tick-snap; stored for inspection
    if use_pb:
        pb_level_raw = actual_entry + (e2_pb_r * risk_pts if is_long else -e2_pb_r * risk_pts)
        pb_raw       = (pb_level_raw - e2_pb_ticks * ts) if is_long else (pb_level_raw + e2_pb_ticks * ts)
        # Snap conservatively: long PB is below entry → floor (price must come further down);
        # short PB is above entry → ceil (price must go further up).
        if is_long:
            pb_trigger = round(float(np.floor(pb_raw / ts)) * ts, 10)
        else:
            pb_trigger = round(float(np.ceil(pb_raw / ts)) * ts, 10)

    # ── Phase 1: Scan simultaneously for T1, stop, and PB fill ───────────────
    # Scale-in model: E2 must fill BEFORE T1 is hit.
    #   • If T1 hits first  → trade over, E1 profit only (no scale-in)
    #   • If PB fills first → E2 added, proceed to Phase 2 targeting T1/T2
    #   • If stop hits first → E1 stops out
    # Same-bar conservative priorities: stop > T1 > PB fill
    p1_result  = "Session"   # "T1_only" | "PB_filled" | "Stop" | "Session" (EOD)
    p1_dt      = None
    p1_exit_px = None
    p1_fill_pos = None       # bar position where PB fills (to slice Phase 2)

    for pos, (_, bar) in enumerate(next_bars.iterrows()):
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - actual_entry) if is_long else (actual_entry - lo))
        mae = max(mae, (actual_entry - lo) if is_long else (hi - actual_entry))

        hit_t1   = (hi >= t1_price)    if is_long else (lo <= t1_price)
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
            # T1 hit before PB → trade over, E1 wins at T1
            p1_result  = "T1_only"
            p1_dt      = bar["DateTime"]
            p1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            break
        if hit_pb:
            # PB filled (T1 not yet hit on this bar, or same bar hit both → PB got in first
            # not possible since stop > T1 > PB priority; if T1 also hit same bar, conflict)
            if hit_t1:
                # Same bar: T1 hit AND PB triggered. Conservative: T1 wins, no scale-in.
                same_bar_conflict = True
                p1_result  = "T1_only"
                p1_dt      = bar["DateTime"]
                p1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)
            else:
                # Clean PB fill: E2 scales in
                e2_entry      = round(round((pb_trigger + (entry_slip * ts if is_long else -entry_slip * ts)) / ts) * ts, 10)
                e2_fill_dt    = bar["DateTime"]
                # Blended avg entry (tv1/tv2 are proportional to contract counts)
                blended_entry = (actual_entry * tv1 + e2_entry * tv2) / tv_total
                blended_risk  = abs(blended_entry - actual_stop)
                t2_price      = round(round((blended_entry + (target_r * blended_risk if is_long else -target_r * blended_risk)) / ts) * ts, 10)
                p1_result     = "PB_filled"
                p1_fill_pos   = pos
            break

    # ── Resolve Phase 1 outcome ───────────────────────────────────────────────
    if p1_result == "Stop":
        # E2 never filled — NoFill keeps _e2_filled=False so only E1 P&L counts
        return _build("Stop", p1_exit_px, p1_dt, "Stop", p1_exit_px, "NoFill", actual_entry)

    if p1_result == "T1_only":
        # Leg 1 exits at T1; Leg 2 never entered → e2_entry still = actual_entry → l2_pts = 0
        return _build("T1_only", p1_exit_px, p1_dt, "T1", p1_exit_px, "NoFill", actual_entry)

    if p1_result == "Session":
        # EOD before PB fills — E2 never entered
        last_bar   = next_bars.iloc[-1]
        eod_px     = float(last_bar["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, last_bar["DateTime"], "EOD", eod_px, "NoFill", actual_entry)

    # ── Phase 2: E2 filled — combined position (Leg1+Leg2) targets T2 or stop ─
    # T2 = blended_entry + target_r * blended_risk (blended avg of E1+E2, original stop)
    phase2   = next_bars.iloc[p1_fill_pos + 1:]
    last_bar = next_bars.iloc[-1]
    p2_result = "Session"
    p2_px_r   = float(last_bar["Close"])
    p2_dt     = last_bar["DateTime"]

    for _, bar2 in phase2.iterrows():
        hi2, lo2 = float(bar2["High"]), float(bar2["Low"])
        mfe = max(mfe, (hi2 - actual_entry) if is_long else (actual_entry - lo2))
        mae = max(mae, (actual_entry - lo2) if is_long else (hi2 - actual_entry))

        hit_t2   = (hi2 >= t2_price) if is_long else (lo2 <= t2_price)
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
    """Tick-level 3-leg simulation. E1→T1, E2→T2, E3→T3(=target_r).
    All legs share original stop; after T1 hit, stop moves to blended BE."""
    from data_loader import RTH_START_MIN
    ts      = TICK_SIZE
    is_long = direction == "Long"

    after = day_ticks[day_ticks["DateTime"] > sig_dt]
    if after.empty:
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
        qualifying = (after[after["Price"] >= signal_price] if is_long
                      else after[after["Price"] <= signal_price])
        if qualifying.empty:
            return {"ok": False, "FilterStatus": "no_fill"}
        fill_tick     = qualifying.iloc[0]
        first_tick_px = fill_tick["Price"]
        entry_dt      = fill_tick["DateTime"]
        after         = after[after["DateTime"] >= fill_tick["DateTime"]]
        prices        = after["Price"].values
        times         = after["DateTime"].values

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
        tv_used = tv1 + (tv2 if pb1_filled else 0.0) + (tv3 if pb2_filled else 0.0)
        l1_ep   = leg1_exit_px if leg1_exit_px is not None else exit_px
        l1_pts  = (l1_ep - e1_entry) if is_long else (e1_entry - l1_ep)
        l1_pnl  = l1_pts / ts * tv1
        l2_ep   = e2_exit if e2_exit is not None else exit_px
        l2_pts  = (l2_ep - e2_entry_px) if (is_long and pb1_filled) else \
                  (e2_entry_px - l2_ep) if (not is_long and pb1_filled) else 0.0
        l2_pnl  = l2_pts / ts * tv2 if pb1_filled else 0.0
        l3_ep   = e3_exit if e3_exit is not None else exit_px
        l3_pts  = (l3_ep - e3_entry_px) if (is_long and pb2_filled) else \
                  (e3_entry_px - l3_ep) if (not is_long and pb2_filled) else 0.0
        l3_pnl  = l3_pts / ts * tv3 if pb2_filled else 0.0
        g_pnl   = l1_pnl + l2_pnl + l3_pnl
        g_pts   = l1_pts + l2_pts + l3_pts
        r_risk  = risk_pts / ts * tv1
        r_ach   = g_pnl / r_risk if r_risk > 0 else 0.0
        ttype   = ("E1+PB1+PB2" if pb2_filled else "E1+PB1" if pb1_filled else "Rocket")
        filled_c = e1c + (e2c if pb1_filled else 0) + (e3c if pb2_filled else 0)
        edt     = pd.Timestamp(exit_dt)
        l1_er   = "T1" if leg1_exit_px is not None else exit_reason
        return {
            "ok": True,
            "SEPrice":    signal_price,        "FillPrice":   first_tick_px,
            "EntryTime":  pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": e1_entry,            "ActualStop":  actual_stop,
            "Target":     t3_price,            "Target1":     t1_price,
            "RiskPts":    risk_pts,            "RiskDollar":  risk_pts / ts * tv1,
            "ExitTime":   edt,                 "ExitBarNum":  bar_num_from_dt(edt),
            "ExitPrice":  exit_px,             "ExitReason":  exit_reason,
            "GrossPnLPts": g_pts,              "GrossPnL":    g_pnl,
            "R_achieved": r_ach,
            "MAE_pts":    max(mae, 0.0),       "MAE_dollar":  max(mae, 0.0) / ts * tv_used,
            "MAE_R":      max(mae, 0.0) / risk_pts,
            "MFE_pts":    max(mfe, 0.0),       "MFE_dollar":  max(mfe, 0.0) / ts * tv_used,
            "MFE_R":      max(mfe, 0.0) / risk_pts,
            "SlippagePts":    (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * tv_used,
            "Leg1ExitReason": l1_er,           "Leg1ExitPrice": l1_ep,
            "Leg1GrossPts":   l1_pts,          "Leg1GrossPnL":  l1_pnl,
            "Leg2ExitReason": (e2_rsn or exit_reason) if pb1_filled else np.nan,
            "Leg2ExitPrice":  l2_ep if pb1_filled else np.nan,
            "Leg2GrossPts":   l2_pts,          "Leg2GrossPnL":  l2_pnl,
            "Leg3ExitReason": (e3_rsn or exit_reason) if pb2_filled else np.nan,
            "Leg3ExitPrice":  l3_ep if pb2_filled else np.nan,
            "Leg3GrossPts":   l3_pts,          "Leg3GrossPnL":  l3_pnl,
            "TradeType":      ttype,
            "BlendedEntry":   _blended(),
            "PB1FillPrice":   e2_entry_px if pb1_filled else np.nan,
            "PB2FillPrice":   e3_entry_px if pb2_filled else np.nan,
            "FilledContracts": filled_c,
        }

    # ── Phase 1: PB fills → ratchet → stop → T1 ──────────────────────────────
    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - e1_entry) if is_long else (e1_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if i == 0:
            continue

        # PB1 fill (limit order below/above entry)
        if not pb1_filled and tv2 > 0:
            if (p <= pb1_price) if is_long else (p >= pb1_price):
                e2_fill = pb1_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e2_fill > actual_stop) or (not is_long and e2_fill < actual_stop):
                    e2_entry_px = e2_fill
                    pb1_filled  = True

        # PB2 fill (requires PB1 first)
        if pb1_filled and not pb2_filled and tv3 > 0:
            if (p <= pb2_price) if is_long else (p >= pb2_price):
                e3_fill = pb2_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e3_fill > actual_stop) or (not is_long and e3_fill < actual_stop):
                    e3_entry_px = e3_fill
                    pb2_filled  = True

        # Ratchet (uses blended entry after any fills this tick)
        if ratchet_r > 0.0 and not ratchet_fired:
            bl    = _blended()
            favor = (p - bl) if is_long else (bl - p)
            if favor >= ratchet_r * risk_pts:
                if ratchet_dest == "Lock-in":
                    lk = ratchet_lock_r * risk_pts
                    active_stop = (bl + lk) if is_long else (bl - lk)
                elif ratchet_dest == "E1":
                    active_stop = e1_entry
                else:  # "BE"
                    active_stop = _blended()
                ratchet_fired = True

        # Stop (all contracts)
        if (p <= active_stop) if is_long else (p >= active_stop):
            sp = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            full_stop_px = sp
            full_stop_dt = t
            break

        # T1
        if (p >= t1_price) if is_long else (p <= t1_price):
            phase1_end_idx = i
            break

    if full_stop_px is not None:
        return _build("Stop", full_stop_px, full_stop_dt)

    if phase1_end_idx is None:
        eod_px = float(prices[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, times[-1])

    # ── Phase 2: E2→T2, E3→T3, blended-BE stop ───────────────────────────────
    leg1_exit_px = None
    if t1_action == "exit":
        leg1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)

    be_stop_p2 = _blended()
    p2_pr      = prices[phase1_end_idx:]
    p2_ts      = times[phase1_end_idx:]
    last_p2_px = float(p2_pr[-1]) + (-exit_slip * ts if is_long else exit_slip * ts)
    last_p2_dt = p2_ts[-1]

    e2_done = not pb1_filled
    e3_done = not pb2_filled
    e2_exit = None; e2_rsn = None
    e3_exit = None; e3_rsn = None
    be_px   = None; be_dt  = None

    for j, (p2v, t2v) in enumerate(zip(p2_pr, p2_ts)):
        excursion = (p2v - e1_entry) if is_long else (e1_entry - p2v)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)
        if j == 0:
            continue
        if (p2v <= be_stop_p2) if is_long else (p2v >= be_stop_p2):
            sp2 = be_stop_p2 + (-exit_slip * ts if is_long else exit_slip * ts)
            if not e2_done: e2_exit = sp2; e2_rsn = "BE"; e2_done = True
            if not e3_done: e3_exit = sp2; e3_rsn = "BE"; e3_done = True
            be_px = sp2; be_dt = t2v
            break
        if not e2_done and ((p2v >= t2_price) if is_long else (p2v <= t2_price)):
            e2_exit = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e2_rsn = "T2"; e2_done = True
        if not e3_done and ((p2v >= t3_price) if is_long else (p2v <= t3_price)):
            e3_exit = t3_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e3_rsn = "T3"; e3_done = True
        if e2_done and e3_done:
            break

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
    """Bar-level 3-leg simulation. E1→T1, E2→T2, E3→T3. Conservative: stop wins same bar."""
    ts      = TICK_SIZE
    is_long = direction == "Long"

    next_bars = day_bars[day_bars["DateTime"] >= sig_dt].reset_index(drop=True)
    if next_bars.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    nb = next_bars.iloc[0]
    if is_long  and float(nb["High"]) < signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}
    if not is_long and float(nb["Low"])  > signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}

    fill_px     = max(float(nb["Open"]), signal_price) if is_long else min(float(nb["Open"]), signal_price)
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
        tv_used = tv1 + (tv2 if pb1_filled else 0.0) + (tv3 if pb2_filled else 0.0)
        l1_ep   = leg1_exit_px if leg1_exit_px is not None else exit_px
        l1_pts  = (l1_ep - e1_entry) if is_long else (e1_entry - l1_ep)
        l1_pnl  = l1_pts / ts * tv1
        l2_ep   = e2_exit if e2_exit is not None else exit_px
        l2_pts  = (l2_ep - e2_entry_px) if (is_long and pb1_filled) else \
                  (e2_entry_px - l2_ep) if (not is_long and pb1_filled) else 0.0
        l2_pnl  = l2_pts / ts * tv2 if pb1_filled else 0.0
        l3_ep   = e3_exit if e3_exit is not None else exit_px
        l3_pts  = (l3_ep - e3_entry_px) if (is_long and pb2_filled) else \
                  (e3_entry_px - l3_ep) if (not is_long and pb2_filled) else 0.0
        l3_pnl  = l3_pts / ts * tv3 if pb2_filled else 0.0
        g_pnl   = l1_pnl + l2_pnl + l3_pnl
        g_pts   = l1_pts + l2_pts + l3_pts
        r_risk  = risk_pts / ts * tv1
        r_ach   = g_pnl / r_risk if r_risk > 0 else 0.0
        ttype   = ("E1+PB1+PB2" if pb2_filled else "E1+PB1" if pb1_filled else "Rocket")
        filled_c = e1c + (e2c if pb1_filled else 0) + (e3c if pb2_filled else 0)
        l1_er   = "T1" if leg1_exit_px is not None else exit_reason
        return {
            "ok": True,
            "SEPrice":    signal_price,        "FillPrice":   fill_px,
            "EntryTime":  pd.Timestamp(entry_dt), "EntryBarNum": entry_bar,
            "EntryPrice": e1_entry,            "ActualStop":  actual_stop,
            "Target":     t3_price,            "Target1":     t1_price,
            "RiskPts":    risk_pts,            "RiskDollar":  risk_pts / ts * tv1,
            "ExitTime":   pd.Timestamp(exit_dt), "ExitBarNum":  bar_num_from_dt(pd.Timestamp(exit_dt)),
            "ExitPrice":  exit_px,             "ExitReason":  exit_reason,
            "GrossPnLPts": g_pts,              "GrossPnL":    g_pnl,
            "R_achieved": r_ach,
            "MAE_pts":    max(mae, 0.0),       "MAE_dollar":  max(mae, 0.0) / ts * tv_used,
            "MAE_R":      max(mae, 0.0) / risk_pts,
            "MFE_pts":    max(mfe, 0.0),       "MFE_dollar":  max(mfe, 0.0) / ts * tv_used,
            "MFE_R":      max(mfe, 0.0) / risk_pts,
            "SlippagePts":    (entry_slip + exit_slip) * ts,
            "SlippageDollar": (entry_slip + exit_slip) * ts / ts * tv_used,
            "Leg1ExitReason": l1_er,           "Leg1ExitPrice": l1_ep,
            "Leg1GrossPts":   l1_pts,          "Leg1GrossPnL":  l1_pnl,
            "Leg2ExitReason": (e2_rsn or exit_reason) if pb1_filled else np.nan,
            "Leg2ExitPrice":  l2_ep if pb1_filled else np.nan,
            "Leg2GrossPts":   l2_pts,          "Leg2GrossPnL":  l2_pnl,
            "Leg3ExitReason": (e3_rsn or exit_reason) if pb2_filled else np.nan,
            "Leg3ExitPrice":  l3_ep if pb2_filled else np.nan,
            "Leg3GrossPts":   l3_pts,          "Leg3GrossPnL":  l3_pnl,
            "TradeType":      ttype,
            "BlendedEntry":   _blended(),
            "PB1FillPrice":   e2_entry_px if pb1_filled else np.nan,
            "PB2FillPrice":   e3_entry_px if pb2_filled else np.nan,
            "FilledContracts": filled_c,
        }

    # ── Phase 1: bar-level scan ────────────────────────────────────────────────
    for idx, bar in next_bars.iterrows():
        hi, lo = float(bar["High"]), float(bar["Low"])
        mfe = max(mfe, (hi - e1_entry) if is_long else (e1_entry - lo))
        mae = max(mae, (e1_entry - lo) if is_long else (hi - e1_entry))

        # Stop check first (conservative — stop wins before PB on same bar)
        if (lo <= active_stop) if is_long else (hi >= active_stop):
            sp = active_stop + (-exit_slip * ts if is_long else exit_slip * ts)
            full_stop_px, full_stop_dt = sp, bar["DateTime"]
            break

        # PB fills (only if stop didn't fire)
        if not pb1_filled and tv2 > 0:
            if (lo <= pb1_price) if is_long else (hi >= pb1_price):
                e2_fill = pb1_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e2_fill > actual_stop) or (not is_long and e2_fill < actual_stop):
                    e2_entry_px = e2_fill
                    pb1_filled  = True

        if pb1_filled and not pb2_filled and tv3 > 0:
            if (lo <= pb2_price) if is_long else (hi >= pb2_price):
                e3_fill = pb2_price + (-entry_slip * ts if is_long else entry_slip * ts)
                if (is_long and e3_fill > actual_stop) or (not is_long and e3_fill < actual_stop):
                    e3_entry_px = e3_fill
                    pb2_filled  = True

        # Ratchet
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

        # T1 check
        if (hi >= t1_price) if is_long else (lo <= t1_price):
            t1_bar_idx = idx
            break

    if full_stop_px is not None:
        return _build("Stop", full_stop_px, full_stop_dt)

    if t1_bar_idx is None:
        last   = next_bars.iloc[-1]
        eod_px = float(last["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
        return _build("EOD", eod_px, last["DateTime"])

    # ── Phase 2: E2→T2, E3→T3, blended-BE stop ───────────────────────────────
    leg1_exit_px = None
    if t1_action == "exit":
        leg1_exit_px = t1_price + (-exit_slip * ts if is_long else exit_slip * ts)

    be_stop_p2 = _blended()
    phase2     = next_bars[next_bars.index >= t1_bar_idx].reset_index(drop=True)
    last2      = phase2.iloc[-1]
    last_p2_px = float(last2["Close"]) + (-exit_slip * ts if is_long else exit_slip * ts)
    last_p2_dt = last2["DateTime"]

    e2_done = not pb1_filled
    e3_done = not pb2_filled
    e2_exit = None; e2_rsn = None
    e3_exit = None; e3_rsn = None
    be_px   = None; be_dt  = None

    for j, (_, bar2) in enumerate(phase2.iterrows()):
        hi2, lo2 = float(bar2["High"]), float(bar2["Low"])
        mfe = max(mfe, (hi2 - e1_entry) if is_long else (e1_entry - lo2))
        mae = max(mae, (e1_entry - lo2) if is_long else (hi2 - e1_entry))
        if j == 0:
            continue
        if (lo2 <= be_stop_p2) if is_long else (hi2 >= be_stop_p2):
            sp2 = be_stop_p2 + (-exit_slip * ts if is_long else exit_slip * ts)
            if not e2_done: e2_exit = sp2; e2_rsn = "BE"; e2_done = True
            if not e3_done: e3_exit = sp2; e3_rsn = "BE"; e3_done = True
            be_px = sp2; be_dt = bar2["DateTime"]
            break
        if not e2_done and ((hi2 >= t2_price) if is_long else (lo2 <= t2_price)):
            e2_exit = t2_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e2_rsn = "T2"; e2_done = True
        if not e3_done and ((hi2 >= t3_price) if is_long else (lo2 <= t3_price)):
            e3_exit = t3_price + (-exit_slip * ts if is_long else exit_slip * ts)
            e3_rsn = "T3"; e3_done = True
        if e2_done and e3_done:
            break

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
    "BlendedEntry": np.nan, "T1_R": np.nan, "PB_R": np.nan,
    "SameBarConflict": False,
}


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
    # ratchet (single-leg and 2-leg)
    ratchet_r: float = 0.0,
    ratchet_dest: str = "BE",
    ratchet_lock_r: float = 0.0,
    # 2-leg pullback for E2
    ml_pb_r: float = 0.0,
    ml_pb_ticks: int = 0,
    # 3-leg
    threeleg: bool = False,
    contracts_e1: int = 1,
    contracts_e2: int = 1,
    contracts_e3: int = 1,
    pb1_r: float = 0.5,
    pb1_ticks: int = 0,
    pb2_r: float = 1.0,
    pb2_ticks: int = 0,
    t2_r: float = 0.0,   # E2 target; defaults to target_r if 0
) -> pd.DataFrame:
    _t2_r = t2_r if t2_r > 0 else target_r   # default E2 target = T3 if not set
    tv   = tick_value * contracts
    tv1  = tick_value * contracts_t1
    tv2  = tick_value * contracts_t2
    # 3-leg tick values
    tv_e1 = tick_value * contracts_e1
    tv_e2 = tick_value * contracts_e2
    tv_e3 = tick_value * contracts_e3
    rows = []

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

        # ── 3-leg routing ──────────────────────────────────────────────────────
        if threeleg and not manual_fill:
            if no_ticks and bars_by_date is not None:
                day_bars_sim = bars_by_date.get(base["Date"])
                if day_bars_sim is None or day_bars_sim.empty:
                    base["FilterStatus"] = "no_tick_data"
                    rows.append(base)
                    continue
                res = _simulate_one_bars_3leg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_bars_sim, t1_r, _t2_r, target_r, t1_action,
                    tv_e1, tv_e2, tv_e3, contracts_e1, contracts_e2, contracts_e3,
                    pb1_r, pb1_ticks, pb2_r, pb2_ticks,
                    entry_slip, exit_slip, stop_offset,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                )
            elif no_ticks:
                base["FilterStatus"] = "no_tick_data"
                rows.append(base)
                continue
            else:
                res = _simulate_one_3leg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, t1_r, _t2_r, target_r, t1_action,
                    tv_e1, tv_e2, tv_e3, contracts_e1, contracts_e2, contracts_e3,
                    pb1_r, pb1_ticks, pb2_r, pb2_ticks,
                    entry_slip, exit_slip, stop_offset,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                )
        # ── 2-leg routing ──────────────────────────────────────────────────────
        elif multileg and not manual_fill:
            if no_ticks and bars_by_date is not None:
                day_bars_sim = bars_by_date.get(base["Date"])
                if day_bars_sim is None or day_bars_sim.empty:
                    base["FilterStatus"] = "no_tick_data"
                    rows.append(base)
                    continue
                res = _simulate_one_bars_multileg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_bars_sim, target_r, t1_r, t1_action,
                    entry_slip, exit_slip, stop_offset, tv1, tv2,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                    e2_pb_r=ml_pb_r, e2_pb_ticks=ml_pb_ticks,
                )
            elif no_ticks:
                base["FilterStatus"] = "no_tick_data"
                rows.append(base)
                continue
            else:
                res = _simulate_one_multileg(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, target_r, t1_r, t1_action,
                    entry_slip, exit_slip, stop_offset, tv1, tv2,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                )
        # ── single-leg routing ─────────────────────────────────────────────────
        else:
            if no_ticks and bars_by_date is not None and not manual_fill:
                day_bars_sim = bars_by_date.get(base["Date"])
                if day_bars_sim is None or day_bars_sim.empty:
                    base["FilterStatus"] = "no_tick_data"
                    rows.append(base)
                    continue
                res = _simulate_one_bars(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_bars_sim, target_r, entry_slip, exit_slip, stop_offset, tv,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                )
            elif no_ticks and not manual_fill:
                base["FilterStatus"] = "no_tick_data"
                rows.append(base)
                continue
            else:
                res = _simulate_one(
                    base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
                    day_ticks, target_r, entry_slip, exit_slip, stop_offset, tv,
                    ratchet_r, ratchet_dest, ratchet_lock_r,
                    manual_fill=manual_fill,
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

    # Cumulative PF column (over filled trades sorted by date/time)
    filled_mask = df["Filled"] == True
    df["CumPF"]  = np.nan
    if filled_mask.any():
        g_pnl     = df.loc[filled_mask, "GrossPnL"]
        cum_wins  = g_pnl.clip(lower=0).cumsum()
        cum_loss  = g_pnl.clip(upper=0).cumsum().abs()
        df.loc[filled_mask, "CumPF"] = (cum_wins / cum_loss.replace(0, np.nan)).values

    return df


# ── Summary metrics ───────────────────────────────────────────────────────────

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
    _eod_mask  = ~_tgt_mask & ~_stop_mask          # EOD / Session exits

    # EOD trades count as W or L based on NetPnL vs avg position price
    _eod_w = _eod_mask & (filled["NetPnL"] > 0)
    _eod_l = _eod_mask & (filled["NetPnL"] < 0)
    _eod_b = _eod_mask & (filled["NetPnL"] == 0)   # exactly breakeven — rare

    wins   = filled[_tgt_mask  | _eod_w]
    stops  = filled[_stop_mask | _eod_l]
    sess   = filled[_eod_b]                         # only true breakeven EOD
    n_wins = len(wins)
    n_stop = len(stops)
    n_sess = len(sess)
    win_pct = n_wins / n_trades * 100 if n_trades else 0

    gross_total = filled["GrossPnL"].sum()
    net_total   = filled["NetPnL"].sum()

    # PF based on all outcomes (positive / |negative|)
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

    # R distribution
    r_vals = filled["R_achieved"].dropna().values
    r_std  = float(np.std(r_vals, ddof=1)) if len(r_vals) > 1 else 0.0

    # SQN — Van Tharp, N capped at 100
    n_sqn = min(n_trades, 100)
    sqn   = float(exp_r / r_std * np.sqrt(n_sqn)) if r_std > 0 else 0.0

    # Median win / loss (net)
    median_win  = float(wins["NetPnL"].median())  if n_wins else 0.0
    median_loss = float(stops["NetPnL"].median()) if n_stop else 0.0

    # Bootstrap 95% CI on Exp R (2 000 resamples, fixed seed for reproducibility)
    exp_r_ci_lo = exp_r_ci_hi = np.nan
    if len(r_vals) >= 5:
        rng  = np.random.default_rng(42)
        boot = rng.choice(r_vals, size=(2000, len(r_vals)), replace=True).mean(axis=1)
        exp_r_ci_lo = float(np.percentile(boot, 2.5))
        exp_r_ci_hi = float(np.percentile(boot, 97.5))

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
    )


# ── Ratchet/BE-Stop bar-ambiguity diagnostic ──────────────────────────────────

def diagnose_ratchet_bar_ambiguities(
    results_df: pd.DataFrame,
    ticks_by_date: dict,
    bars_by_date: dict | None,
    ratchet_r: float,
    target_r: float,
    tick_value: float,
    entry_slip: float,
    exit_slip: float,
    stop_offset: int,
    commission: float,
    contracts: int,
) -> pd.DataFrame:
    """Identify AIAO trades that stopped at ~BE after ratchet, then re-simulate as
    BE Stop to show whether the same trade would have continued and hit the target.
    Returns a comparison DataFrame showing the PnL delta per trade."""
    ts = TICK_SIZE
    tv = tick_value * contracts
    tol = (exit_slip + 1.5) * ts   # price tolerance for "exit ≈ entry"

    filled = results_df[results_df["Filled"] == True].copy()
    # Candidate trades: Stop exit priced within tol of entry (ratcheted BE stop)
    be_stops = filled[
        (filled["ExitReason"] == "Stop") &
        (abs(filled["ExitPrice"] - filled["EntryPrice"]) <= tol)
    ].copy()

    rows = []
    for _, row in be_stops.iterrows():
        date       = row["Date"]
        sig_dt     = row["DateTime"]
        direction  = row["Direction"]
        is_long    = direction == "Long"
        entry_px   = float(row["EntryPrice"])
        actual_stop = float(row["ActualStop"])
        risk_pts   = float(row["RiskPts"])
        sig_price  = float(row.get("SignalPrice", entry_px))
        stop_price = float(row.get("StopPrice",  actual_stop))
        t1_level   = entry_px + (ratchet_r * risk_pts if is_long else -ratchet_r * risk_pts)

        # ── Find the exit bar to verify the Hi/Lo pattern ─────────────────────
        bar_hi = bar_lo = None
        is_ambiguous = False
        day_bars = (bars_by_date or {}).get(date)
        exit_time = row.get("ExitTime")

        if day_bars is not None and exit_time is not None:
            exit_ts = pd.Timestamp(exit_time)
            candidates = day_bars[day_bars["DateTime"] <= exit_ts]
            if not candidates.empty:
                eb = candidates.iloc[-1]
                bar_hi = float(eb["High"])
                bar_lo = float(eb["Low"])
                if is_long:
                    is_ambiguous = (
                        bar_hi >= t1_level - 0.001 and
                        bar_lo <= entry_px + 0.001 and
                        bar_lo > actual_stop - 0.001
                    )
                else:
                    is_ambiguous = (
                        bar_lo <= t1_level + 0.001 and
                        bar_hi >= entry_px - 0.001 and
                        bar_hi < actual_stop + 0.001
                    )

        # ── Re-simulate as BE Stop (same T1 level, full position continues) ───
        be_exit_reason = be_exit_px = be_net_pnl = None
        day_ticks = ticks_by_date.get(date)
        no_ticks  = day_ticks is None or day_ticks.empty

        try:
            if not no_ticks:
                res = _simulate_one_multileg(
                    sig_dt, direction, sig_price, stop_price,
                    day_ticks, target_r, ratchet_r, "be_only",
                    entry_slip, exit_slip, stop_offset,
                    tv1=0.0, tv2=tv,
                )
            elif day_bars is not None:
                res = _simulate_one_bars_multileg(
                    sig_dt, direction, sig_price, stop_price,
                    day_bars, target_r, ratchet_r, "be_only",
                    entry_slip, exit_slip, stop_offset,
                    tv1=0.0, tv2=tv,
                )
            else:
                res = {"ok": False}

            if res.get("ok"):
                be_exit_reason = res["ExitReason"]
                be_exit_px     = round(float(res["ExitPrice"]), 2)
                be_net_pnl     = round(float(res["GrossPnL"]) - commission * contracts, 2)
        except Exception:
            pass

        pnl_diff = round(be_net_pnl - float(row["NetPnL"]), 2) if be_net_pnl is not None else None

        rows.append({
            "Date":          str(date),
            "Dir":           direction,
            "Entry":         round(entry_px, 2),
            "Stop":          round(actual_stop, 2),
            "T1_Level":      round(t1_level, 2),
            "Bar_Hi":        round(bar_hi, 2) if bar_hi else None,
            "Bar_Lo":        round(bar_lo, 2) if bar_lo else None,
            "Ambiguous_Bar": is_ambiguous,
            "AIAO_Exit":     row["ExitReason"],
            "AIAO_Px":       round(float(row["ExitPrice"]), 2),
            "AIAO_Net":      round(float(row["NetPnL"]), 2),
            "BEStop_Exit":   be_exit_reason,
            "BEStop_Px":     be_exit_px,
            "BEStop_Net":    be_net_pnl,
            "PnL_Delta":     pnl_diff,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Date").reset_index(drop=True)
    return df


# ── Chart ─────────────────────────────────────────────────────────────────────

def _outcome_color(exit_reason: str) -> str:
    if "Target" in exit_reason:
        return "#26a69a"   # green — full or partial win
    if exit_reason == "Stop":
        return "#ef5350"   # red — full stop
    if exit_reason in ("T1+BE", "T1+EOD"):
        return "#ff9800"   # orange — partial profit
    return "#9e9e9e"       # grey — EOD, session


def make_analysis_chart(
    day_bars: pd.DataFrame,
    day_results: pd.DataFrame,
    date_str: str,
    show_bar_nums: bool = False,
    excl_first_n: int = 0,
    excl_last_min: int = 0,
    contract: str = "ES",
    show_hover: bool = True,
) -> go.Figure:
    df = day_bars
    fig = go.Figure(
        go.Candlestick(
            x=df["DateTime"], open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=contract,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        )
    )

    half  = pd.Timedelta(minutes=2, seconds=30)
    shade = dict(fillcolor="rgba(180,180,180,0.15)", line_width=0, layer="below")
    if excl_first_n > 0 and excl_first_n <= len(df):
        fig.add_vrect(x0=df.iloc[0]["DateTime"] - half,
                      x1=df.iloc[min(excl_first_n, len(df)) - 1]["DateTime"] + half, **shade)
    if excl_last_min > 0:
        ct = 15 * 60 + 15 - excl_last_min
        cs = f"{ct // 60:02d}:{ct % 60:02d}"
        cb = df[df["DateTime"].dt.strftime("%H:%M") >= cs]
        if not cb.empty:
            fig.add_vrect(x0=cb.iloc[0]["DateTime"] - half,
                          x1=df.iloc[-1]["DateTime"] + half, **shade)

    if show_bar_nums:
        labeled = sorted(set(range(0, len(df), 3)) | {len(df) - 1})
        for i in labeled:
            fig.add_annotation(
                x=df.iloc[i]["DateTime"], y=df.iloc[i]["Low"],
                yshift=-6, text=str(bar_num_from_dt(df.iloc[i]["DateTime"])),
                showarrow=False, font=dict(size=12),
                xanchor="center", yanchor="top",
            )

    # Collect all relevant prices for Y-range calculation
    y_prices = list(df["Low"].values) + list(df["High"].values)

    # Pre-compute chart y-range for hover rectangles (extend well beyond bars)
    y_lo_pre = df["Low"].min()
    y_hi_pre = df["High"].max()
    h_pad    = (y_hi_pre - y_lo_pre) * 0.30

    if not day_results.empty:
        day_range = df["High"].max() - df["Low"].min()
        marker_offset = day_range * 0.003

        for _, row in day_results.iterrows():
            sig_dt   = row["DateTime"]
            is_long  = row["Direction"] == "Long"
            filtered = row["FilterStatus"] != "ok"

            # Signal bar open = sig_dt - 5min (bars use label="left")
            bar_open = sig_dt - pd.Timedelta(minutes=5)
            bar_rows = df[df["DateTime"] == bar_open]
            if bar_rows.empty:
                continue
            bar_row = bar_rows.iloc[0]

            if filtered:
                rect_color   = "rgba(160,160,160,0.10)"
                border_color = "rgba(160,160,160,0.30)"
                dot_color    = "#aaaaaa"
            elif is_long:
                rect_color   = "rgba(0,230,118,0.18)"
                border_color = "rgba(0,230,118,0.70)"
                dot_color    = "#00e676"
            else:
                rect_color   = "rgba(255,80,80,0.18)"
                border_color = "rgba(255,80,80,0.70)"
                dot_color    = "#ff5252"

            fig.add_vrect(
                x0=bar_open - half, x1=bar_open + half,
                fillcolor=rect_color,
                line=dict(color=border_color, width=1.0),
                layer="below",
            )

            htxt = (
                f"Signal #{int(row['SignalNum'])} {row['SignalType']} {row['Direction']}<br>"
                f"Date: {row['Date']}  Bar: {int(row['BarNum'])} | {sig_dt.strftime('%H:%M')}<br>"
                f"Signal Price: {row['SignalPrice']:.2f} | Stop: {row['StopPrice']:.2f}<br>"
                f"Status: {row['FilterStatus']}"
            )
            if show_hover:
                fig.add_trace(go.Scatter(
                    x=[bar_open],
                    y=[(float(bar_row["High"]) + float(bar_row["Low"])) / 2],
                    mode="markers",
                    marker=dict(size=20, color=dot_color, opacity=0.001),
                    hovertemplate=htxt + "<extra></extra>",
                    showlegend=False, name="",
                ))

            if not row["Filled"]:
                continue

            entry_dt  = row["EntryTime"]
            entry_px  = row["EntryPrice"]
            stop_px   = row["ActualStop"]
            target_px = row["Target"]
            exit_dt   = row["ExitTime"]
            exit_px   = row["ExitPrice"]
            reason    = row["ExitReason"]
            oc        = _outcome_color(reason)
            net_pnl   = row["NetPnL"]
            gross_pts = row["GrossPnLPts"]
            sign      = "+" if net_pnl >= 0 else ""

            _t1_px_yrange = row.get("Target1", np.nan)
            for p in [entry_px, stop_px, target_px, _t1_px_yrange, exit_px]:
                if pd.notna(p):
                    y_prices.append(p)

            entry_ts = pd.Timestamp(entry_dt)
            exit_ts  = pd.Timestamp(exit_dt)

            entry_htxt = (
                f"ENTRY #{int(row['SignalNum'])}<br>"
                f"Date: {entry_ts.strftime('%Y-%m-%d')}  Bar {int(row['EntryBarNum'])} | {entry_ts.strftime('%H:%M:%S')}<br>"
                f"Price: {entry_px:.2f}<br>"
                f"Stop: {stop_px:.2f} | Target: {target_px:.2f}<br>"
                f"Risk: {row['RiskPts']:.2f} pts (${row['RiskDollar']:.0f})"
            )
            # Entry marker — hover directly on the circle
            _ekw = {"hovertemplate": entry_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
            fig.add_trace(go.Scatter(
                x=[entry_ts], y=[entry_px], mode="markers",
                marker=dict(symbol="circle-open", size=9, color=oc, line=dict(width=2)),
                showlegend=False, name="", **_ekw,
            ))

            exit_htxt = (
                f"EXIT #{int(row['SignalNum'])}  ({reason})<br>"
                f"Date: {exit_ts.strftime('%Y-%m-%d')}  Bar {int(row['ExitBarNum'])} | {exit_ts.strftime('%H:%M:%S')}<br>"
                f"Price: {exit_px:.2f}<br>"
                f"Gross: {sign}{gross_pts:.2f} pts | Net: {sign}${net_pnl:.0f}<br>"
                f"R: {row['R_achieved']:+.2f}<br>"
                f"MAE: {row['MAE_pts']:.2f} pts | MFE: {row['MFE_pts']:.2f} pts"
            )
            # Exit marker — hover directly on the x marker
            _xkw = {"hovertemplate": exit_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
            fig.add_trace(go.Scatter(
                x=[exit_ts], y=[exit_px], mode="markers",
                marker=dict(symbol="x", size=9, color=oc, line=dict(width=2)),
                showlegend=False, name="", **_xkw,
            ))

            xref, yref = "x", "y"

            # Stop line — extends from signal bar left edge to exit
            fig.add_shape(type="line",
                x0=bar_open, x1=exit_ts,
                y0=stop_px, y1=stop_px,
                line=dict(color="#ef5350", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # T1 line (dotted teal, shown when multileg)
            target1_px = row.get("Target1", np.nan)
            risk_pts   = row.get("RiskPts",  np.nan)
            _has_t1    = pd.notna(target1_px) and pd.notna(risk_pts) and risk_pts > 0.001
            if _has_t1:
                t1_r_disp = abs(float(target1_px) - entry_px) / risk_pts
                fig.add_shape(type="line",
                    x0=entry_ts, x1=exit_ts,
                    y0=float(target1_px), y1=float(target1_px),
                    line=dict(color="#26a69a", width=1.0, dash="dot"),
                    xref=xref, yref=yref)
                fig.add_annotation(
                    x=exit_ts, y=float(target1_px),
                    xshift=6, yshift=0,
                    text=f"T1 {t1_r_disp:.2f}R",
                    showarrow=False, xanchor="left",
                    font=dict(size=10, color="#26a69a"),
                )

            # PB level line + E2 fill circle (scale-in model)
            pb_level_px  = row.get("PBLevel",    np.nan)
            e2_fill_px   = row.get("E2FillPrice", np.nan)
            e2_fill_time = row.get("E2FillTime",  pd.NaT)
            if pd.notna(pb_level_px):
                y_prices.append(pb_level_px)
                e2_end_ts = pd.Timestamp(e2_fill_time) if pd.notna(e2_fill_time) else exit_ts
                fig.add_shape(type="line",
                    x0=entry_ts, x1=e2_end_ts,
                    y0=pb_level_px, y1=pb_level_px,
                    line=dict(color="#ffa726", width=1.2, dash="dashdot"),
                    xref=xref, yref=yref)
                fig.add_annotation(
                    x=entry_ts, y=pb_level_px,
                    xshift=-4, yshift=0,
                    text="PB", showarrow=False, xanchor="right",
                    font=dict(size=9, color="#ffa726"),
                )
                if pd.notna(e2_fill_px) and pd.notna(e2_fill_time):
                    e2_htxt = (
                        f"E2 FILL (scale-in)<br>"
                        f"Time: {e2_end_ts.strftime('%H:%M')}<br>"
                        f"Fill price: {e2_fill_px:.2f}"
                    )
                    _e2kw = {"hovertemplate": e2_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
                    fig.add_trace(go.Scatter(
                        x=[e2_end_ts], y=[e2_fill_px], mode="markers",
                        marker=dict(symbol="circle", size=9, color="#ffa726",
                                    line=dict(color="#ffa726", width=2)),
                        showlegend=False, name="", **_e2kw,
                    ))

            # T2 / Target line (dashed teal)
            t2_label = f"T2 {row['TargetR']:.2f}R" if _has_t1 else f"<b>{row['TargetR']:.2f}R</b>"
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=target_px, y1=target_px,
                line=dict(color="#26a69a", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # R label — right end of target line
            fig.add_annotation(
                x=exit_ts, y=target_px,
                xshift=6, yshift=0,
                text=t2_label,
                showarrow=False, xanchor="left",
                font=dict(size=11, color="#26a69a"),
            )

            # BE line (orange) = entry price
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=entry_px, y1=entry_px,
                line=dict(color="#ff9800", width=1.0),
                xref=xref, yref=yref)

            # Dotted diagonal: entry price → exit price
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=entry_px, y1=exit_px,
                line=dict(color=oc, width=1.5, dash="dot"),
                xref=xref, yref=yref)

    # Y-range with padding
    if y_prices:
        y_lo, y_hi = min(y_prices), max(y_prices)
        pad = (y_hi - y_lo) * 0.06
        fig.update_layout(yaxis=dict(range=[y_lo - pad, y_hi + pad]))

    # x-axis: bar DateTimes are open times; label ticks as close time (+5 min)
    _tick_vals = [t for t in df["DateTime"] if t.minute % 15 == 0]
    _tick_text = [(t + pd.Timedelta(minutes=5)).strftime("%H:%M") for t in _tick_vals]
    spike = dict(showspikes=True, spikethickness=1, spikedash="dot",
                 spikecolor="rgba(128,128,128,0.40)", spikesnap="cursor")
    fig.update_layout(
        title=f"{contract} — Bar Analysis  ({date_str})",
        xaxis_title="Time (CT)", yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis=dict(tickvals=_tick_vals, ticktext=_tick_text, tickangle=-45, **spike),
        yaxis=dict(**spike),
        height=560,
        margin=dict(l=50, r=20, t=60, b=60),
        template="plotly_white",
        hovermode="closest" if show_hover else False,
        hoverlabel=dict(font_size=15, bgcolor="rgba(30,30,30,0.90)", font_color="white"),
        spikedistance=200,
    )
    return fig


# ── Signal table ──────────────────────────────────────────────────────────────

_STATUS_LABELS = {
    "ok":             "Filtered",    # shouldn't appear if not filled
    "date_range":     "Date range",
    "signal_type":    "Signal type",
    "direction":      "Direction",
    "holiday":        "Holiday",
    "dow":            "Day of week",
    "first_bars":     "Open excl.",
    "last_bars":      "Close excl.",
    "event":          "Econ event",
    "first_trade_day":"2nd+ trade",
    "no_fill":        "No fill",
    "no_next_bar":    "Session end",
    "no_tick_data":   "No tick data",
    "zero_risk":      "Zero risk",
}


def _show_signal_table(results: pd.DataFrame, key_suffix: str = ""):
    if results.empty:
        st.info("No signals to display.")
        return

    _has_multileg = (
        "Leg1ExitReason" in results.columns and
        results["Leg1ExitReason"].notna().any()
    )
    _group_opts = ["Core", "Entry/Exit", "P&L", "Risk & R", "MAE/MFE"]
    if _has_multileg:
        _group_opts.append("Multileg")

    col_groups = st.multiselect(
        "Column groups",
        _group_opts,
        default=["Core", "Entry/Exit", "P&L", "Risk & R"],
        key=f"ba_col_groups{key_suffix}",
    )

    cols = []
    if "Core" in col_groups:
        cols += ["#", "Type", "Dir", "Date", "Sig Time", "Sig Bar", "Status"]
    if "Entry/Exit" in col_groups:
        cols += ["SB Close", "SE Px", "Bar Open", "Entry Time", "Entry Bar", "Entry Px", "Stop", "Target",
                 "Exit Time", "Exit Bar", "Exit Px", "Exit Type"]
    if "P&L" in col_groups:
        cols += ["Gross$", "Net$", "Cum PF"]
    if "Risk & R" in col_groups:
        cols += ["Risk$", "Target R", "R"]
    if "MAE/MFE" in col_groups:
        cols += ["MAE pts", "MAE$", "MAE R", "MFE pts", "MFE$", "MFE R"]
    if "Multileg" in col_groups and _has_multileg:
        cols += ["T1 R", "T2 R", "T1", "L1 Exit", "L1 Px", "L1 $",
                 "PB R", "PB Exact", "PB Lvl", "E2 Fill", "E2 Time", "Blend", "L2 Exit", "L2 Px", "L2 $"]

    if not cols:
        st.info("Select at least one column group above.")
        return

    def fmt_time(t):
        try:
            ts = pd.Timestamp(t)
            if not pd.notna(ts):
                return "—"
            base = ts.strftime("%H:%M:%S")
            ms = ts.microsecond // 1000
            return f"{base}.{ms:03d}" if ms else base
        except Exception:
            return "—"

    def fmt_f(v, decimals=2):
        return f"{v:.{decimals}f}" if pd.notna(v) else "—"

    def fmt_pf(v):
        if pd.isna(v):
            return "—"
        return "∞" if v > 99 else f"{v:.2f}"

    def fmt_status(s):
        return _STATUS_LABELS.get(s, s)

    disp = pd.DataFrame()
    disp["#"]          = results["SignalNum"]
    disp["Type"]       = results["SignalType"]
    disp["Dir"]        = results["Direction"]
    disp["Date"]       = results["Date"].astype(str)
    disp["Sig Time"]   = results["DateTime"].dt.strftime("%H:%M")
    disp["Sig Bar"]    = results["BarNum"]
    disp["Status"]     = results.apply(
        lambda r: "✓ Filled" if r["Filled"] else fmt_status(r["FilterStatus"]), axis=1
    )
    disp["SB Close"]   = results["SBClose"].apply(fmt_f) if "SBClose" in results.columns else "—"
    disp["SE Px"]      = results["SEPrice"].apply(fmt_f)
    disp["Bar Open"]   = results["FillPrice"].apply(fmt_f)
    disp["Entry Time"] = results["EntryTime"].apply(fmt_time)
    disp["Entry Bar"]  = results["EntryBarNum"].apply(lambda v: int(v) if pd.notna(v) else "—")
    disp["Entry Px"]   = results["EntryPrice"].apply(fmt_f)
    disp["Stop"]       = results["ActualStop"].apply(fmt_f)
    disp["Target"]     = results["Target"].apply(fmt_f)
    disp["Exit Time"]  = results["ExitTime"].apply(fmt_time)
    disp["Exit Bar"]   = results["ExitBarNum"].apply(lambda v: int(v) if pd.notna(v) else "—")
    disp["Exit Px"]    = results["ExitPrice"].apply(fmt_f)
    disp["Exit Type"]  = results["ExitReason"].replace("", "—")
    disp["Gross$"]     = results["GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
    disp["Net$"]       = results["NetPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
    disp["Cum PF"]     = results["CumPF"].apply(fmt_pf)
    disp["Risk$"]      = results["RiskDollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["Target R"]   = results["TargetR"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    disp["R"]          = results["R_achieved"].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
    disp["MAE pts"]    = results["MAE_pts"].apply(fmt_f)
    disp["MAE$"]       = results["MAE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MAE R"]      = results["MAE_R"].apply(fmt_f)
    disp["MFE pts"]    = results["MFE_pts"].apply(fmt_f)
    disp["MFE$"]       = results["MFE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MFE R"]      = results["MFE_R"].apply(fmt_f)
    if _has_multileg:
        disp["T1 R"]   = results["T1_R"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
        disp["T2 R"]   = results["TargetR"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
        disp["T1"]     = results["Target1"].apply(fmt_f)
        disp["L1 Exit"]= results["Leg1ExitReason"].fillna("—")
        disp["L1 Px"]  = results["Leg1ExitPrice"].apply(fmt_f)
        disp["L1 $"]   = results["Leg1GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        disp["L2 Exit"]= results["Leg2ExitReason"].fillna("—")
        disp["L2 Px"]  = results["Leg2ExitPrice"].apply(fmt_f)
        disp["L2 $"]   = results["Leg2GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        if "PBLevel" in results.columns:
            disp["PB R"]     = results["PB_R"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
            disp["PB Lvl"]   = results["PBLevel"].apply(fmt_f)
            disp["PB Exact"] = results["PBLevelRaw"].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "—")
            disp["E2 Fill"]= results["E2FillPrice"].apply(fmt_f)
            disp["E2 Time"]= results["E2FillTime"].apply(
                lambda t: pd.Timestamp(t).strftime("%H:%M") if pd.notna(t) else "—"
            )
            disp["Blend"]  = results["BlendedEntry"].apply(fmt_f)

    # Filter to selected column groups
    visible = [c for c in cols if c in disp.columns]
    disp    = disp[visible]

    st.dataframe(disp, use_container_width=True, hide_index=True,
                 height=min(35 * len(disp) + 38, 600))
    st.caption(f"{len(results)} signals  |  {int(results['Filled'].sum())} filled trades")


# ── Optimal R sweep ───────────────────────────────────────────────────────────

def _apply_day_trade_filters(
    results: pd.DataFrame,
    first_trade_only: bool,
    first_2_filled_only: bool,
) -> pd.DataFrame:
    """Apply post-simulation per-day trade count filters (mirrors main sim path)."""
    if results.empty:
        return results
    if first_trade_only:
        _fm = results["Filled"] == True
        _keep = results[_fm].sort_values(["Date", "SignalNum"]).groupby("Date").head(1).index
        results = results.drop(results[_fm & ~results.index.isin(_keep)].index).reset_index(drop=True)
    if first_2_filled_only and not results.empty:
        _fm = results["Filled"] == True
        _keep = results[_fm].sort_values(["Date", "SignalNum"]).groupby("Date").head(2).index
        results = results.drop(results[_fm & ~results.index.isin(_keep)].index).reset_index(drop=True)
    return results


def _run_r_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    max_r: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    _n_steps = max(1, round(max_r / 0.25))
    r_values = [round(r * 0.25, 2) for r in range(2, _n_steps + 1)]  # 0.50 – max_r
    rows = []
    for r in r_values:
        res = simulate_trades(signals, ticks_by_date, r,
                               entry_slip, exit_slip, stop_offset,
                               tick_value, contracts, commission,
                               bars_by_date=bars_by_date,
                               multileg=multileg, t1_r=t1_r,
                               t1_action=t1_action, contracts_t1=contracts_t1,
                               contracts_t2=contracts_t2)
        res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
        s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                            t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        if not s or s["n_trades"] == 0:
            continue
        _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
        rows.append({
            "R":       r,
            "Win %":   round(s["win_pct"], 1),
            "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
            "Net PnL": round(s["net_total"], 0),
            "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
            "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
            "Exp $":   round(s["exp_dollar"], 0),
        })
    return pd.DataFrame(rows)


def _run_t1t2_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    max_t1: float = 3.0, max_t2: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Grid sweep over all valid (T1, T2) pairs for 2-leg / BE-stop mode."""
    _n_t1 = max(1, round(max_t1 / 0.25))
    _n_t2 = max(1, round(max_t2 / 0.25))
    t1_vals = [round(r * 0.25, 2) for r in range(1, _n_t1 + 1)]
    t2_vals = [round(r * 0.25, 2) for r in range(2, _n_t2 + 1)]
    rows = []
    for t1 in t1_vals:
        for t2 in t2_vals:
            if t1 >= t2:
                continue
            res = simulate_trades(
                signals, ticks_by_date, t2,
                entry_slip, exit_slip, stop_offset,
                tick_value, contracts, commission,
                bars_by_date=bars_by_date,
                multileg=True, t1_r=t1,
                t1_action=t1_action,
                contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            s = compute_summary(
                res, commission, contracts=contracts, is_multileg=True,
                t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "T1":      t1,
                "T2":      t2,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


def _run_ml_scalein_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    contracts_t1: int, contracts_t2: int,
    bars_by_date: dict | None = None,
    pb_vals: list | None = None,
    t1_vals: list | None = None,
    t2_vals: list | None = None,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Sweep PB_R × T1_R × T2_R for 2-leg scale-in mode."""
    if pb_vals is None:
        pb_vals = [-0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50]
    if t1_vals is None:
        t1_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    if t2_vals is None:
        t2_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    rows = []
    for pb in pb_vals:
        for t1 in t1_vals:
            for t2 in t2_vals:
                res = simulate_trades(
                    signals, ticks_by_date, t2,
                    entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission,
                    bars_by_date=bars_by_date,
                    multileg=True, t1_r=t1, t1_action="exit",
                    contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    ml_pb_r=pb, ml_pb_ticks=0,
                )
                res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
                s = compute_summary(
                    res, commission, contracts=contracts, is_multileg=True,
                    t1_action="exit", contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                )
                if not s or s["n_trades"] == 0:
                    continue
                _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
                _filled = res[res["Filled"] == True]
                _n_f    = len(_filled)
                _t1_pct = round(_filled["ExitReason"].eq("T1_only").sum() / _n_f * 100, 1) if _n_f else 0.0
                _t2_pct = round(_filled["ExitReason"].str.contains("Target", na=False).sum() / _n_f * 100, 1) if _n_f else 0.0
                rows.append({
                    "PB_R":    pb,
                    "T1_R":    t1,
                    "T2_R":    t2,
                    "T1 %":    _t1_pct,
                    "T2 %":    _t2_pct,
                    "Win %":   round(s["win_pct"], 1),
                    "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                    "Net PnL": round(s["net_total"], 0),
                    "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                    "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                    "Exp $":   round(s["exp_dollar"], 0),
                })
    return pd.DataFrame(rows)


def _run_pb_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, commission: float,
    target_r: float, t1_r: float, t2_r: float, t1_action: str,
    tv_e1: float, tv_e2: float, tv_e3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_ticks: int, pb2_ticks: int,
    ratchet_r: float, ratchet_dest: str, ratchet_lock_r: float,
    bars_by_date: dict | None = None,
    max_pb1: float = 1.5, max_pb2: float = 2.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Grid sweep over PB1_R × PB2_R for 3-leg mode (tick offsets and targets held fixed)."""
    _step = 0.25
    pb1_vals = [round(r * _step, 2) for r in range(1, max(1, round(max_pb1 / _step)) + 1)]
    pb2_vals = [round(r * _step, 2) for r in range(2, max(2, round(max_pb2 / _step)) + 1)]
    rows = []
    for pb1 in pb1_vals:
        for pb2 in pb2_vals:
            if pb2 <= pb1:
                continue
            res = simulate_trades(
                signals, ticks_by_date, target_r,
                entry_slip, exit_slip, stop_offset,
                tick_value, e1c, commission,
                bars_by_date=bars_by_date,
                threeleg=True, t1_r=t1_r, t2_r=t2_r, t1_action=t1_action,
                contracts_e1=e1c, contracts_e2=e2c, contracts_e3=e3c,
                pb1_r=pb1, pb1_ticks=pb1_ticks,
                pb2_r=pb2, pb2_ticks=pb2_ticks,
                ratchet_r=0.0,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            total_c = e1c + e2c + e3c
            s = compute_summary(res, commission, contracts=total_c,
                                is_multileg=False)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "PB1": pb1, "PB2": pb2,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


def _run_t1t2_sweep_3leg(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, commission: float,
    t2_r_fixed: float, t1_action: str,
    tv_e1: float, tv_e2: float, tv_e3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_r: float, pb1_ticks: int,
    pb2_r: float, pb2_ticks: int,
    bars_by_date: dict | None = None,
    max_t1: float = 3.0, max_t3: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Sweep T1 (E1 target) × T3 (E3 target) with T2 (E2 target) held fixed."""
    _step   = 0.25
    t1_vals = [round(r * _step, 2) for r in range(1, max(1, round(max_t1 / _step)) + 1)]
    t3_vals = [round(r * _step, 2) for r in range(2, max(2, round(max_t3 / _step)) + 1)]
    rows = []
    for t1 in t1_vals:
        for t3 in t3_vals:
            if t1 >= t2_r_fixed or t2_r_fixed >= t3:
                continue
            res = simulate_trades(
                signals, ticks_by_date, t3,
                entry_slip, exit_slip, stop_offset,
                tick_value, e1c, commission,
                bars_by_date=bars_by_date,
                threeleg=True, t1_r=t1, t2_r=t2_r_fixed, t1_action=t1_action,
                contracts_e1=e1c, contracts_e2=e2c, contracts_e3=e3c,
                pb1_r=pb1_r, pb1_ticks=pb1_ticks,
                pb2_r=pb2_r, pb2_ticks=pb2_ticks,
                ratchet_r=0.0,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            total_c = e1c + e2c + e3c
            s = compute_summary(res, commission, contracts=total_c, is_multileg=False)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "T1":      t1,
                "T3":      t3,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


_SWEEP_GREEN   = "#1a9850"  # heatmap RdYlGn max color
_STOP_MULTS    = [0.25, 0.33, 0.50, 0.66, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]


def _apply_stop_mult(signals: pd.DataFrame, mult: float) -> pd.DataFrame:
    """Return a copy of signals with StopPrice scaled by mult relative to SignalPrice."""
    sigs = signals.copy()
    long_mask  = sigs["Direction"] == "Long"
    short_mask = ~long_mask
    dist_long  = sigs.loc[long_mask,  "SignalPrice"] - sigs.loc[long_mask,  "StopPrice"]
    dist_short = sigs.loc[short_mask, "StopPrice"]   - sigs.loc[short_mask, "SignalPrice"]
    sigs.loc[long_mask,  "StopPrice"] = sigs.loc[long_mask,  "SignalPrice"] - dist_long  * mult
    sigs.loc[short_mask, "StopPrice"] = sigs.loc[short_mask, "SignalPrice"] + dist_short * mult
    return sigs


def _run_stop_mult_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    target_r: float, bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Sweep stop multipliers [0.25 … 1.00] at the current target R."""
    rows = []
    for mult in _STOP_MULTS:
        sigs = _apply_stop_mult(signals, mult)
        res  = simulate_trades(sigs, ticks_by_date, target_r,
                               entry_slip, exit_slip, stop_offset,
                               tick_value, contracts, commission,
                               bars_by_date=bars_by_date,
                               multileg=multileg, t1_r=t1_r,
                               t1_action=t1_action,
                               contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
        s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                            t1_action=t1_action,
                            contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        if not s or s["n_trades"] == 0:
            continue
        _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
        rows.append({
            "Stop Mult": f"{mult:.2f}×",
            "Win %":     round(s["win_pct"], 1),
            "PF":        round(s["pf"], 2) if s["pf"] < 99 else 99.9,
            "Net PnL":   round(s["net_total"], 0),
            "DD $":      round(_dd_abs, 0) if _dd_abs else 0.0,
            "PnL/DD":    round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
            "Exp $":     round(s["exp_dollar"], 0),
        })
    return pd.DataFrame(rows)


def _show_stop_sweep(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                     tick_value, contracts, commission, target_r, bars_by_date=None,
                     multileg: bool = False, t1_r: float = 1.0,
                     t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
                     first_trade_only: bool = False, first_2_filled_only: bool = False):
    _METRIC_COLS = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS  = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}
    with st.expander("🔍 Stop Multiplier Sweep", expanded=False):
        st.caption(
            f"Runs simulation at {len(_STOP_MULTS)} stop sizes "
            f"(0.25×–2.00× of the original signal stop) at the current target R = {target_r:.2f}. "
            "1.00× is the baseline (original stop). Target scales proportionally with the stop."
        )
        if st.button("Run Stop Sweep", key="ba_run_stop_sweep"):
            with st.spinner("Running stop sweep…"):
                stop_df = _run_stop_mult_sweep(
                    signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission, target_r,
                    bars_by_date=bars_by_date, multileg=multileg, t1_r=t1_r,
                    t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                )
            if stop_df.empty:
                st.warning("No results.")
                return
            st.session_state["ba_stop_sweep_df"] = stop_df

        stop_df = st.session_state.get("ba_stop_sweep_df")
        if stop_df is None or stop_df.empty:
            return

        fmt_map = {"Win %": "{:.1f}", "PF": "{:.2f}", "PnL/DD": "{:.2f}"}
        fmt_map.update({"Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"})
        styled = _apply_best_green(stop_df, stop_df.style.format(fmt_map),
                                   _METRIC_COLS, _THRESHOLDS)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        fig = go.Figure()
        fig.add_scatter(x=stop_df["Stop Mult"], y=stop_df["Net PnL"],
                        name="Net PnL ($)", mode="lines+markers",
                        line=dict(color="#26a69a", width=2))
        fig.add_scatter(x=stop_df["Stop Mult"], y=stop_df["PF"],
                        name="Profit Factor", mode="lines+markers",
                        yaxis="y2", line=dict(color="#ff9800", width=2))
        fig.update_layout(
            xaxis_title="Stop Multiplier",
            yaxis=dict(title="Net PnL ($)"),
            yaxis2=dict(title="PF", overlaying="y", side="right"),
            height=300, template="plotly_white",
            legend=dict(x=0.01, y=0.99),
        )
        st.plotly_chart(fig, use_container_width=True)


def _apply_best_green(sweep_df: pd.DataFrame, styled, metric_cols: list[str],
                      thresholds: dict | None = None):
    """Highlight only the single best value per column in heatmap-green.
    threshold dict: {col: min_value_to_qualify} — no highlight if best < threshold."""
    thresholds = thresholds or {}

    def _hl_max(s, thr=0):
        best = s.max()
        if best <= thr:
            return [""] * len(s)
        return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                if v == best else "" for v in s]

    def _hl_min(s):
        best = s.min()
        return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                if v == best else "" for v in s]

    for col in metric_cols:
        if col not in sweep_df.columns:
            continue
        if col == "DD $":
            styled = styled.apply(_hl_min, subset=[col])
        else:
            thr = thresholds.get(col, 0)
            styled = styled.apply(_hl_max, thr=thr, subset=[col])
    return styled


def _show_optimal_r(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission, bars_by_date=None,
                    multileg: bool = False, t1_r: float = 1.0,
                    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
                    threeleg: bool = False,
                    tv_e1: float = 0.0, tv_e2: float = 0.0, tv_e3: float = 0.0,
                    e1c: int = 1, e2c: int = 1, e3c: int = 1,
                    pb1_ticks: int = 0, pb2_ticks: int = 0,
                    t2_r: float = 0.0,
                    ratchet_r: float = 0.0, ratchet_dest: str = "BE", ratchet_lock_r: float = 0.0,
                    first_trade_only: bool = False, first_2_filled_only: bool = False):

    _METRIC_COLS  = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS   = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}

    if threeleg:
        # ── 2D PB1×PB2 grid sweep ─────────────────────────────────────────────
        with st.expander("🔍 PB1×PB2 Sweep", expanded=False):
            st.caption(
                "Sweeps pullback entry levels (as R distance back from E1) with tick offsets held fixed. "
                "Ratchet is disabled during sweep for clean robustness testing."
            )
            _rc1, _rc2 = st.columns(2)
            _max_pb1 = _rc1.number_input(
                "Max PB1 (R back)", min_value=0.25, max_value=3.0,
                value=float(st.session_state.get("ba_sweep_max_pb1", 1.5)),
                step=0.25, format="%.2f", key="ba_sweep_max_pb1",
            )
            _max_pb2 = _rc2.number_input(
                "Max PB2 (R back)", min_value=0.5, max_value=4.0,
                value=float(st.session_state.get("ba_sweep_max_pb2", 2.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_pb2",
            )
            _n_pb1 = max(1, round(_max_pb1 / 0.25))
            _n_pb2 = max(2, round(_max_pb2 / 0.25))
            _n_combos = sum(1 for p1 in range(1, _n_pb1 + 1)
                              for p2 in range(2, _n_pb2 + 1)
                              if p2 > p1)
            st.caption(f"PB1: 0.25–{_max_pb1:.2f}R × PB2: 0.50–{_max_pb2:.2f}R — {_n_combos} combinations")

            if st.button("Run PB1×PB2 Sweep", key="ba_run_pb_sweep"):
                with st.spinner(f"Running PB1×PB2 sweep ({_n_combos} combinations)…"):
                    _pb_df = _run_pb_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                        tick_value, commission,
                        target_r=float(st.session_state.get("ba_target_r_3l", 3.0)),
                        t1_r=t1_r, t2_r=t2_r, t1_action=t1_action,
                        tv_e1=tv_e1, tv_e2=tv_e2, tv_e3=tv_e3,
                        e1c=e1c, e2c=e2c, e3c=e3c,
                        pb1_ticks=pb1_ticks, pb2_ticks=pb2_ticks,
                        ratchet_r=0.0, ratchet_dest="BE", ratchet_lock_r=0.0,
                        bars_by_date=bars_by_date,
                        max_pb1=_max_pb1, max_pb2=_max_pb2,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _pb_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_pb_sweep_df"] = _pb_df

            sweep_df = st.session_state.get("ba_pb_sweep_df")
            if sweep_df is None or sweep_df.empty:
                return

            _metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
            _metric = st.selectbox("Color heatmap by", _metric_opts, key="ba_pb_metric")

            _pivot = sweep_df.pivot(index="PB1", columns="PB2", values=_metric)
            _pb1_labels = [f"{v:.2f}" for v in _pivot.index]
            _pb2_labels = [f"{v:.2f}" for v in _pivot.columns]
            _hover = "PB1: %{y}R back<br>PB2: %{x}R back<br>" + _metric + ": %{z}<extra></extra>"
            _hfig = go.Figure(go.Heatmap(
                x=_pb2_labels, y=_pb1_labels, z=_pivot.values.tolist(),
                colorscale="RdYlGn", hovertemplate=_hover,
                colorbar=dict(title=_metric, thickness=14),
            ))
            _hfig.update_layout(
                xaxis_title="PB2 (R back)", yaxis_title="PB1 (R back)",
                height=400, template="plotly_white",
                margin=dict(l=60, r=20, t=30, b=60),
            )
            st.plotly_chart(_hfig, use_container_width=True)

            st.caption(f"Top 20 combinations by **{_metric}**")
            _ranked = sweep_df.sort_values(_metric, ascending=False).head(20).reset_index(drop=True)
            _ranked.index = _ranked.index + 1
            _fmt = {"PB1": "{:.2f}", "PB2": "{:.2f}", "Win %": "{:.1f}",
                    "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                    "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
            _styled = _apply_best_green(_ranked, _ranked.style.format(_fmt), _METRIC_COLS, _THRESHOLDS)
            st.dataframe(_styled, use_container_width=True)

        # ── T1×T3 sweep for 3-leg (T2 held fixed at current value) ───────────
        with st.expander("🔍 T1×T3 Sweep (3-Leg)", expanded=False):
            _t2_fixed = t2_r if t2_r > 0 else float(st.session_state.get("ba_t2_r_3l", 2.0))
            st.caption(
                f"Sweeps T1 (E1 target) × T3 (E3 target) with T2={_t2_fixed:.2f}R (E2 target) held fixed. "
                "PB levels and ratchet disabled."
            )
            _t3c1, _t3c2 = st.columns(2)
            _max_t1_3l = _t3c1.number_input(
                "Max T1 (R)", min_value=0.25, max_value=5.0,
                value=float(st.session_state.get("ba_sweep_max_t1_3l", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t1_3l",
            )
            _max_t3_3l = _t3c2.number_input(
                "Max T3 (R)", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_t3_3l", 5.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t3_3l",
            )
            _n_t1_3l = max(1, round(_max_t1_3l / 0.25))
            _n_t3_3l = max(2, round(_max_t3_3l / 0.25))
            _n_combos_t = sum(1 for t1i in range(1, _n_t1_3l + 1)
                               for t3i in range(2, _n_t3_3l + 1)
                               if t1i < _t2_fixed / 0.25 and _t2_fixed / 0.25 < t3i)
            st.caption(f"T1: 0.25–{_max_t1_3l:.2f}R × T3: 0.50–{_max_t3_3l:.2f}R — {_n_combos_t} combinations")

            if st.button("Run T1×T3 Sweep", key="ba_run_t1t2_3l"):
                _pb1_cur = float(st.session_state.get("ba_pb1_r_3l", 0.33))
                _pb2_cur = float(st.session_state.get("ba_pb2_r_3l", 0.66))
                with st.spinner(f"Running T1×T3 sweep ({_n_combos_t} combinations)…"):
                    _t1t2_3l_df = _run_t1t2_sweep_3leg(
                        signals, ticks_by_date,
                        entry_slip, exit_slip, stop_offset,
                        tick_value, commission,
                        t2_r_fixed=_t2_fixed, t1_action=t1_action,
                        tv_e1=tv_e1, tv_e2=tv_e2, tv_e3=tv_e3,
                        e1c=e1c, e2c=e2c, e3c=e3c,
                        pb1_r=_pb1_cur, pb1_ticks=pb1_ticks,
                        pb2_r=_pb2_cur, pb2_ticks=pb2_ticks,
                        bars_by_date=bars_by_date,
                        max_t1=_max_t1_3l, max_t3=_max_t3_3l,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _t1t2_3l_df.empty:
                    st.warning("No results.")
                else:
                    st.session_state["ba_t1t2_3l_df"] = _t1t2_3l_df

            _t1t2_3l_res = st.session_state.get("ba_t1t2_3l_df")
            if _t1t2_3l_res is not None and not _t1t2_3l_res.empty:
                _t3_metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _t3_metric = st.selectbox("Color heatmap by", _t3_metric_opts, key="ba_t1t2_3l_metric")

                _pivot_t = _t1t2_3l_res.pivot(index="T1", columns="T3", values=_t3_metric)
                _t1_labels = [f"{v:.2f}" for v in _pivot_t.index]
                _t2_labels = [f"{v:.2f}" for v in _pivot_t.columns]
                _hover_t = "T1: %{y}R<br>T3: %{x}R<br>" + _t3_metric + ": %{z}<extra></extra>"
                _tfig = go.Figure(go.Heatmap(
                    x=_t2_labels, y=_t1_labels, z=_pivot_t.values.tolist(),
                    colorscale="RdYlGn", hovertemplate=_hover_t,
                    colorbar=dict(title=_t3_metric, thickness=14),
                ))
                _tfig.update_layout(
                    xaxis_title="T2 (R)", yaxis_title="T1 (R)",
                    height=400, template="plotly_white",
                    margin=dict(l=60, r=20, t=30, b=60),
                )
                st.plotly_chart(_tfig, use_container_width=True)

                st.caption(f"Top 20 combinations by **{_t3_metric}**")
                _t_ranked = _t1t2_3l_res.sort_values(_t3_metric, ascending=False).head(20).reset_index(drop=True)
                _t_ranked.index = _t_ranked.index + 1
                _t_fmt = {"T1": "{:.2f}", "T3": "{:.2f}", "Win %": "{:.1f}",
                          "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                          "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _t_styled = _apply_best_green(_t_ranked, _t_ranked.style.format(_t_fmt), _METRIC_COLS, _THRESHOLDS)
                st.dataframe(_t_styled, use_container_width=True)

    elif multileg:
        # ── 2D T1×T2 grid sweep ───────────────────────────────────────────────
        with st.expander("🔍 T1×T2 Sweep", expanded=False):
            _rc1, _rc2 = st.columns(2)
            _max_t1 = _rc1.number_input(
                "Max T1 (R)", min_value=0.5, max_value=5.0,
                value=float(st.session_state.get("ba_sweep_max_t1", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t1",
            )
            _max_t2 = _rc2.number_input(
                "Max T2 (R)", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_t2", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t2",
            )
            _n_t1 = max(1, round(_max_t1 / 0.25))
            _n_t2 = max(1, round(_max_t2 / 0.25))
            _n_combos = sum(1 for t1i in range(1, _n_t1 + 1)
                              for t2i in range(2, _n_t2 + 1)
                              if t1i < t2i)
            st.caption(f"T1: 0.25–{_max_t1:.2f} × T2: 0.50–{_max_t2:.2f} — {_n_combos} combinations")

            if st.button("Run T1×T2 Sweep", key="ba_run_sweep"):
                with st.spinner(f"Running T1×T2 sweep ({_n_combos} combinations)…"):
                    _t1t2_df = _run_t1t2_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                        tick_value, contracts, commission,
                        bars_by_date=bars_by_date, t1_action=t1_action,
                        contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                        max_t1=_max_t1, max_t2=_max_t2,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _t1t2_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_t1t2_df"] = _t1t2_df

            sweep_df = st.session_state.get("ba_t1t2_df")
            if sweep_df is not None and not sweep_df.empty:
                _metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _metric = st.selectbox(
                    "Color heatmap by", _metric_opts,
                    key="ba_t1t2_metric",
                )

                # ── Heatmap ───────────────────────────────────────────────────
                _pivot = sweep_df.pivot(index="T1", columns="T2", values=_metric)
                _t1_labels = [f"{v:.2f}" for v in _pivot.index]
                _t2_labels = [f"{v:.2f}" for v in _pivot.columns]

                _hover = "T1: %{y}<br>T2: %{x}<br>" + _metric + ": %{z}<extra></extra>"
                _hfig = go.Figure(go.Heatmap(
                    x=_t2_labels, y=_t1_labels,
                    z=_pivot.values.tolist(),
                    colorscale="RdYlGn",
                    hovertemplate=_hover,
                    colorbar=dict(title=_metric, thickness=14),
                ))
                _hfig.update_layout(
                    xaxis_title="T2 (R)", yaxis_title="T1 (R)",
                    height=420, template="plotly_white",
                    margin=dict(l=60, r=20, t=30, b=60),
                )
                st.plotly_chart(_hfig, use_container_width=True)

                # ── Ranked table ──────────────────────────────────────────────
                st.caption(f"Top 20 combinations by **{_metric}**")
                _ranked = sweep_df.sort_values(_metric, ascending=False).head(20).reset_index(drop=True)
                _ranked.index = _ranked.index + 1

                _fmt = {"T1": "{:.2f}", "T2": "{:.2f}", "Win %": "{:.1f}",
                        "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                        "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _styled = _apply_best_green(
                    _ranked, _ranked.style.format(_fmt), _METRIC_COLS, _THRESHOLDS
                )
                def _hl_rank1_t1t2(s):
                    return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                            if i == s.index[0] else "" for i in s.index]
                for _tc in ("T1", "T2"):
                    if _tc in _ranked.columns:
                        _styled = _styled.apply(_hl_rank1_t1t2, subset=[_tc])
                st.dataframe(_styled, use_container_width=True)

        # ── Scale-In sweep: PB × T1 × T2 ─────────────────────────────────────
        with st.expander("🔍 Scale-In Sweep (PB × T1 × T2)", expanded=False):
            _all_pb = [-0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50]
            _all_t1 = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
            _all_t2 = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
            _pb_lbl = [f"{v:.2f}R" for v in _all_pb]
            _t1_lbl = [f"{v:.2f}R" for v in _all_t1]
            _t2_lbl = [f"{v:.2f}R" for v in _all_t2]

            _sc1, _sc2, _sc3 = st.columns(3)
            with _sc1:
                st.caption("**PB range**")
                _pb_from_sel = st.selectbox("Shallowest", _pb_lbl, index=0,           key="ba_si_pb_from")
                _pb_to_sel   = st.selectbox("Deepest",    _pb_lbl, index=len(_pb_lbl)-1, key="ba_si_pb_to")
            with _sc2:
                st.caption("**T1 range**")
                _t1_from_sel = st.selectbox("Min T1", _t1_lbl, index=0,           key="ba_si_t1_from")
                _t1_to_sel   = st.selectbox("Max T1", _t1_lbl, index=len(_t1_lbl)-1, key="ba_si_t1_to")
            with _sc3:
                st.caption("**T2 range**")
                _t2_from_sel = st.selectbox("Min T2", _t2_lbl, index=0,           key="ba_si_t2_from")
                _t2_to_sel   = st.selectbox("Max T2", _t2_lbl, index=len(_t2_lbl)-1, key="ba_si_t2_to")

            _pb_from_i = _pb_lbl.index(_pb_from_sel)
            _pb_to_i   = _pb_lbl.index(_pb_to_sel)
            _t1_from_i = _t1_lbl.index(_t1_from_sel)
            _t1_to_i   = _t1_lbl.index(_t1_to_sel)
            _t2_from_i = _t2_lbl.index(_t2_from_sel)
            _t2_to_i   = _t2_lbl.index(_t2_to_sel)

            _sweep_pb = _all_pb[min(_pb_from_i, _pb_to_i) : max(_pb_from_i, _pb_to_i) + 1]
            _sweep_t1 = _all_t1[min(_t1_from_i, _t1_to_i) : max(_t1_from_i, _t1_to_i) + 1]
            _sweep_t2 = _all_t2[min(_t2_from_i, _t2_to_i) : max(_t2_from_i, _t2_to_i) + 1]
            _si_n = len(_sweep_pb) * len(_sweep_t1) * len(_sweep_t2)
            st.caption(f"PB: {len(_sweep_pb)} values · T1: {len(_sweep_t1)} values · T2: {len(_sweep_t2)} values — **{_si_n} combinations** (T1 auto-capped at run time — see below)")

            with st.expander("ℹ️ How the T1 ceiling works", expanded=False):
                st.markdown("""
**Problem:** If T1 is set very high (e.g. 9R or 10R), it can never be reached before
the pullback fills — so the T1-only exit path disappears entirely. The sweep would
label those rows as "optimal" simply because they are equivalent to having no T1 at
all (every trade becomes a scale-in attempt). That is a degenerate result, not a
genuine optimum.

**Solution — data-driven T1 ceiling:**
When you click *Run Scale-In Sweep*, the app first runs a single-leg simulation with
a target of 999R (effectively infinite) so that the trade stays open until the stop
or end-of-day. This gives the **unconstrained MFE** (Maximum Favorable Excursion)
for every signal — i.e. how far price actually ran from entry before stopping out or
hitting EOD, with no artificial T1 cap.

The **95th percentile** of that MFE distribution (in R units) becomes the T1 ceiling.
Any T1 value above that ceiling would produce a T1-only exit rate of ~0 % across
all signals — meaning the T1 parameter has no effect and the sweep result is
meaningless for those rows.

T1 values above the ceiling are removed from the sweep before it runs.
The ceiling is shown next to the results table after each run.
""")

            if st.button("Run Scale-In Sweep", key="ba_run_si_sweep"):
                # ── Compute data-driven T1 ceiling before sweeping ──────────────
                # Run a single-leg sim with target=999R so T1 is never constrained;
                # 95th pct of MFE_R gives the highest T1 that could ever trigger.
                with st.spinner("Computing T1 ceiling from data…"):
                    _bl_res  = simulate_trades(
                        signals, ticks_by_date, 999.0,
                        entry_slip, exit_slip, stop_offset,
                        tick_value, contracts_t1, commission,
                        bars_by_date=bars_by_date, multileg=False,
                    )
                    _bl_res  = _apply_day_trade_filters(_bl_res, first_trade_only, first_2_filled_only)
                    _mfe_ser = _bl_res[_bl_res["Filled"] == True]["MFE_R"]
                    _t1_cap  = float(round(_mfe_ser.quantile(0.95) * 4) / 4) if not _mfe_ser.empty else 10.0
                    st.session_state["ba_si_t1_cap"] = _t1_cap
                _sweep_t1_capped = [v for v in _sweep_t1 if v <= _t1_cap] or [_sweep_t1[0]]
                _si_n_actual = len(_sweep_pb) * len(_sweep_t1_capped) * len(_sweep_t2)
                with st.spinner(f"Running scale-in sweep ({_si_n_actual} combinations, T1 ≤ {_t1_cap:.2f}R)…"):
                    _si_df = _run_ml_scalein_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                        tick_value, contracts, commission,
                        contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                        bars_by_date=bars_by_date,
                        pb_vals=_sweep_pb, t1_vals=_sweep_t1_capped, t2_vals=_sweep_t2,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _si_df.empty:
                    st.warning("No scale-in results.")
                else:
                    st.session_state["ba_si_sweep_df"] = _si_df

            _si_res = st.session_state.get("ba_si_sweep_df")
            if _si_res is not None and "T1_R" not in _si_res.columns:
                # stale result from old 2-param sweep — discard it
                st.session_state.pop("ba_si_sweep_df", None)
                _si_res = None
            if _si_res is not None and not _si_res.empty:
                _si_metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _si_c1, _si_c2 = st.columns(2)
                _si_metric  = _si_c1.selectbox("Color heatmap by", _si_metric_opts, key="ba_si_metric")
                _si_t1_vals = sorted(_si_res["T1_R"].unique())
                _si_t1_lbls = [f"{v:.2f}R" for v in _si_t1_vals]
                _si_t1_sel  = _si_c2.selectbox("T1 slice (heatmap)", _si_t1_lbls, key="ba_si_t1_slice")
                _si_t1_val  = _si_t1_vals[_si_t1_lbls.index(_si_t1_sel)]

                _si_slice = _si_res[_si_res["T1_R"] == _si_t1_val]
                if not _si_slice.empty:
                    _si_pivot  = _si_slice.pivot(index="PB_R", columns="T2_R", values=_si_metric)
                    _pb_lbls_h = [f"{v:.2f}" for v in _si_pivot.index]
                    _t2_lbls_h = [f"{v:.2f}" for v in _si_pivot.columns]
                    _si_hover  = f"T1={_si_t1_val:.2f}R<br>PB: %{{y}}R<br>T2: %{{x}}R<br>{_si_metric}: %{{z}}<extra></extra>"
                    _si_fig = go.Figure(go.Heatmap(
                        x=_t2_lbls_h, y=_pb_lbls_h,
                        z=_si_pivot.values.tolist(),
                        colorscale="RdYlGn",
                        hovertemplate=_si_hover,
                        colorbar=dict(title=_si_metric, thickness=14),
                    ))
                    _si_fig.update_layout(
                        title=f"PB × T2  (T1 = {_si_t1_val:.2f}R)",
                        xaxis_title="T2 (R from blended entry)",
                        yaxis_title="E2 Pullback (R from entry)",
                        height=380, template="plotly_white",
                        margin=dict(l=80, r=20, t=40, b=60),
                    )
                    st.plotly_chart(_si_fig, use_container_width=True)

                _t1_cap_shown = st.session_state.get("ba_si_t1_cap")
                if _t1_cap_shown:
                    st.info(
                        f"**T1 ceiling applied: {_t1_cap_shown:.2f}R** — "
                        f"computed as the 95th percentile of unconstrained MFE across all filled signals "
                        f"(single-leg sim, target = 999R). "
                        f"T1 values above {_t1_cap_shown:.2f}R would produce a ~0% T1-only rate and were excluded from the sweep.",
                        icon="📐",
                    )
                st.caption(f"Top 20 combinations (all T1) by **{_si_metric}**")
                _si_ranked = _si_res.sort_values(_si_metric, ascending=False).head(20).reset_index(drop=True)
                _si_ranked.index = _si_ranked.index + 1
                _si_fmt = {"PB_R": "{:.2f}", "T1_R": "{:.2f}", "T2_R": "{:.2f}",
                           "T1 %": "{:.1f}", "T2 %": "{:.1f}", "Win %": "{:.1f}",
                           "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                           "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _si_styled = _apply_best_green(
                    _si_ranked, _si_ranked.style.format(_si_fmt), _METRIC_COLS, _THRESHOLDS
                )
                def _hl_rank1_si(s):
                    return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                            if i == s.index[0] else "" for i in s.index]
                for _sc in ("PB_R", "T1_R", "T2_R"):
                    if _sc in _si_ranked.columns:
                        _si_styled = _si_styled.apply(_hl_rank1_si, subset=[_sc])
                st.dataframe(_si_styled, use_container_width=True)

    else:
        # ── 1D R sweep (single-leg) ───────────────────────────────────────────
        with st.expander("🔍 Optimal R Sweep", expanded=False):
            _max_r = st.number_input(
                "Max R", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_r", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_r",
            )
            _n_r = max(1, round(_max_r / 0.25)) - 1  # steps from 0.50
            st.caption(f"R: 0.50–{_max_r:.2f} in 0.25 steps — {_n_r} values")

            if st.button("Run R Sweep", key="ba_run_sweep"):
                with st.spinner(f"Running sweep ({_n_r} values)…"):
                    sweep_df = _run_r_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip,
                        stop_offset, tick_value, contracts, commission,
                        bars_by_date=bars_by_date,
                        multileg=False, t1_r=t1_r, t1_action=t1_action,
                        contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                        max_r=_max_r,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if sweep_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_sweep_df"] = sweep_df

            sweep_df = st.session_state.get("ba_sweep_df")
            if sweep_df is None or sweep_df.empty:
                return

            fmt_map = {"R": "{:.2f}", "Win %": "{:.1f}", "PF": "{:.2f}", "PnL/DD": "{:.2f}"}
            fmt_map.update({"Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"})
            styled = _apply_best_green(
                sweep_df, sweep_df.style.format(fmt_map), _METRIC_COLS, _THRESHOLDS
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

            fig = go.Figure()
            fig.add_scatter(x=sweep_df["R"], y=sweep_df["Net PnL"],
                            name="Net PnL ($)", mode="lines+markers",
                            line=dict(color="#26a69a", width=2))
            fig.add_scatter(x=sweep_df["R"], y=sweep_df["PF"],
                            name="Profit Factor", mode="lines+markers",
                            yaxis="y2", line=dict(color="#ff9800", width=2))
            fig.update_layout(
                xaxis_title="Target R",
                yaxis=dict(title="Net PnL ($)"),
                yaxis2=dict(title="PF", overlaying="y", side="right"),
                height=320, template="plotly_white",
                legend=dict(x=0.01, y=0.99),
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Unfilled signals table ────────────────────────────────────────────────────

_FILTER_LABELS = {
    "no_fill":        "Price never crossed signal level",
    "no_next_bar":    "No ticks after signal bar close",
    "no_tick_data":   "No tick data for this date",
    "zero_risk":      "Stop distance is zero",
    "holiday":        "NYSE holiday",
    "dow":            "Day-of-week excluded",
    "event":          "Economic event window",
    "first_bars":     "Within excluded opening bars",
    "last_bars":      "Within excluded closing window",
    "signal_type":    "Signal type excluded",
    "direction":      "Direction excluded",
    "date_range":     "Outside selected date range",
    "first_trade_day":"Non-first trade of day",
    "manual_override":"Manual fill override ✓",
}

_EXECUTION_STATUSES = {"no_fill", "no_next_bar", "no_tick_data", "zero_risk"}


def _on_first_trade_change():
    if st.session_state.get("ba_first_trade"):
        st.session_state["ba_first_2_filled"] = False

def _on_first_2_change():
    if st.session_state.get("ba_first_2_filled"):
        st.session_state["ba_first_trade"] = False


def _missed_by_ticks(sig_row, ticks_by_date: dict):
    """For a no_fill signal, how many ticks did price miss the signal level by?"""
    day_ticks = ticks_by_date.get(sig_row["Date"])
    if day_ticks is None:
        return None
    after = day_ticks[day_ticks["DateTime"] > sig_row["DateTime"]]
    if after.empty:
        return None
    sp = sig_row["SignalPrice"]
    prices = after["Price"]
    if sig_row["Direction"] == "Long":
        closest = prices.max()
        return None if closest >= sp else int(round((sp - closest) / TICK_SIZE))
    else:
        closest = prices.min()
        return None if closest <= sp else int(round((closest - sp) / TICK_SIZE))


_SETUP_COLORS = ["#ffa726", "#ab47bc", "#29b6f6", "#66bb6a", "#ec407a", "#ef5350"]


def _show_monthly_breakdown(results: pd.DataFrame, commission: float):
    filled = results[results["Filled"]].copy()
    if filled.empty:
        return

    filled = filled.sort_values(["Date", "EntryTime"]).reset_index(drop=True)
    filled["Month"] = pd.to_datetime(filled["Date"]).dt.to_period("M")
    signal_types = sorted(filled["SignalType"].unique())

    # ── Shared stats helper ───────────────────────────────────────────────────
    def _group_stats(g, setup_pcts: bool = False) -> pd.Series:
        n       = len(g)
        wins    = g[g["ExitReason"].str.contains("Target", na=False) | (g["ExitReason"] == "T1+BE")]
        stops   = g[g["ExitReason"] == "Stop"]
        pos_pnl = g.loc[g["GrossPnL"] > 0, "GrossPnL"].sum()
        neg_pnl = g.loc[g["GrossPnL"] < 0, "GrossPnL"].sum()
        pf      = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else (float("inf") if pos_pnl > 0 else 0)
        row = {
            "Trades":  n,
            "Win%":    round(len(wins) / n * 100, 1) if n else 0.0,
            "PF":      round(min(pf, 99.9), 2),
            "Net PnL": round(g["NetPnL"].sum(), 0),
            "Avg R":   round(g["R_achieved"].mean(), 2),
            "MAE R":   round(g["MAE_R"].mean(), 2),
            "MFE R":   round(g["MFE_R"].mean(), 2),
            "Best":    round(wins["NetPnL"].max(), 0) if len(wins) else 0.0,
            "Worst":   round(stops["NetPnL"].min(), 0) if len(stops) else 0.0,
        }
        if setup_pcts:
            for stype in signal_types:
                row[f"{stype}%"] = round(int((g["SignalType"] == stype).sum()) / n * 100, 1) if n else 0.0
        return pd.Series(row)

    # ── Per-month ─────────────────────────────────────────────────────────────
    monthly = (
        filled.groupby("Month", sort=True)
        .apply(lambda g: _group_stats(g, setup_pcts=True))
        .reset_index()
    )
    monthly["Month"] = monthly["Month"].astype(str)

    # ── Per-setup ─────────────────────────────────────────────────────────────
    setup_df = (
        filled.groupby("SignalType", sort=True)
        .apply(lambda g: _group_stats(g, setup_pcts=False))
        .reset_index()
    )

    # ── Equity / DD / trend ───────────────────────────────────────────────────
    equity     = filled["NetPnL"].cumsum().values
    peak       = pd.Series(equity).cummax().values
    dd_vals    = equity - peak
    trade_nums = list(range(1, len(filled) + 1))
    tn_arr     = np.array(trade_nums, dtype=float)
    coeffs     = np.polyfit(tn_arr, equity, 1)
    trend_y    = np.polyval(coeffs, tn_arr)

    stype_pct_cols = [f"{s}%" for s in signal_types]

    def _fmt(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["Net PnL"] = df["Net PnL"].apply(lambda v: f"${v:+,.0f}")
        d["Best"]    = df["Best"].apply(lambda v: f"${v:+,.0f}" if v != 0 else "—")
        d["Worst"]   = df["Worst"].apply(lambda v: f"${v:+,.0f}" if v != 0 else "—")
        d["Win%"]    = df["Win%"].apply(lambda v: f"{v:.1f}%")
        d["PF"]      = df["PF"].apply(lambda v: f"{v:.2f}")
        d["Avg R"]   = df["Avg R"].apply(lambda v: f"{v:.2f}")
        d["MAE R"]   = df["MAE R"].apply(lambda v: f"{v:.2f}")
        d["MFE R"]   = df["MFE R"].apply(lambda v: f"{v:.2f}")
        return d

    base_cols = ["Trades", "Win%", "PF", "Net PnL", "Avg R", "MAE R", "MFE R", "Best", "Worst"]

    # ── Monthly breakdown expander ────────────────────────────────────────────
    with st.expander("📅 Monthly Breakdown", expanded=False):
        disp = _fmt(monthly)
        for col in stype_pct_cols:
            if col in monthly.columns:
                disp[col] = monthly[col].apply(lambda v: f"{v:.1f}%")
        st.dataframe(
            disp[["Month"] + base_cols + stype_pct_cols],
            use_container_width=True, hide_index=True,
        )

        chart_l, chart_r = st.columns([3, 2])

        with chart_l:
            fig_eq = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                row_heights=[0.65, 0.35], vertical_spacing=0.04,
                subplot_titles=("Equity Curve", "Drawdown ($)"),
            )
            fig_eq.add_trace(go.Scatter(
                x=trade_nums, y=equity.tolist(),
                mode="lines", name="Equity",
                line=dict(color="#26a69a", width=2),
                fill="tozeroy", fillcolor="rgba(38,166,154,0.12)",
                hovertemplate="Trade %{x}<br>Equity: $%{y:,.0f}<extra></extra>",
            ), row=1, col=1)
            fig_eq.add_trace(go.Scatter(
                x=[trade_nums[0], trade_nums[-1]],
                y=[float(trend_y[0]), float(trend_y[-1])],
                mode="lines", name="Trend",
                line=dict(color="rgba(255,167,38,0.85)", width=1.5, dash="dash"),
                hoverinfo="skip",
            ), row=1, col=1)
            fig_eq.add_trace(go.Bar(
                x=trade_nums, y=dd_vals.tolist(),
                name="DD", marker_color="rgba(239,83,80,0.65)",
                hovertemplate="Trade %{x}<br>DD: $%{y:,.0f}<extra></extra>",
            ), row=2, col=1)
            fig_eq.update_layout(
                height=400, showlegend=False, template="plotly_white",
                margin=dict(l=55, r=15, t=40, b=40),
                hovermode="x unified",
            )
            fig_eq.update_yaxes(tickprefix="$", row=1, col=1)
            fig_eq.update_yaxes(tickprefix="$", row=2, col=1)
            fig_eq.update_xaxes(title_text="Trade #", row=2, col=1)
            st.plotly_chart(fig_eq, use_container_width=True)

        with chart_r:
            bar_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in monthly["Net PnL"]]
            fig_cc = go.Figure()
            fig_cc.add_trace(go.Bar(
                x=monthly["Month"], y=monthly["Net PnL"],
                name="Net PnL", marker_color=bar_colors, yaxis="y",
                hovertemplate="%{x}<br>Net PnL: $%{y:+,.0f}<extra></extra>",
            ))
            for i, stype in enumerate(signal_types):
                col = f"{stype}%"
                if col not in monthly.columns:
                    continue
                fig_cc.add_trace(go.Scatter(
                    x=monthly["Month"], y=monthly[col],
                    name=stype, mode="lines+markers",
                    line=dict(color=_SETUP_COLORS[i % len(_SETUP_COLORS)], width=2),
                    marker=dict(size=7), yaxis="y2",
                    hovertemplate=f"%{{x}}<br>{stype}%%: %{{y:.1f}}%%<extra></extra>",
                ))
            setup_label = "/".join(signal_types) + "% vs Net PnL" if signal_types else "Setup% vs Net PnL"
            fig_cc.update_layout(
                height=400, template="plotly_white",
                title=dict(text=setup_label, font=dict(size=13)),
                margin=dict(l=55, r=65, t=45, b=60),
                legend=dict(orientation="h", y=1.10, x=0),
                yaxis=dict(title="Net PnL ($)", tickprefix="$"),
                yaxis2=dict(title="Setup %", overlaying="y", side="right",
                            range=[0, 100], ticksuffix="%"),
                xaxis=dict(tickangle=-45),
                hovermode="x unified",
            )
            st.plotly_chart(fig_cc, use_container_width=True)

    # ── Setup analysis expander ───────────────────────────────────────────────
    with st.expander("📊 Setup Analysis", expanded=False):
        sdisp = _fmt(setup_df)
        st.dataframe(
            sdisp[["SignalType"] + base_cols],
            use_container_width=True, hide_index=True,
        )


def _show_unfilled_table(results: pd.DataFrame, ticks_by_date: dict):
    st.markdown("---")

    # ── Signals that passed filters but didn't execute ────────────────────────
    exec_failed = results[results["FilterStatus"].isin(_EXECUTION_STATUSES)].copy()

    with st.expander(f"Execution failures — {len(exec_failed)} signals", expanded=False):
        if exec_failed.empty:
            st.success("All filter-passing signals were filled.")
        else:
            exec_failed["Reason"] = exec_failed["FilterStatus"].map(_FILTER_LABELS)
            exec_failed["Missed by (ticks)"] = exec_failed.apply(
                lambda r: _missed_by_ticks(r, ticks_by_date)
                          if r["FilterStatus"] == "no_fill" else None,
                axis=1,
            )
            disp = pd.DataFrame({
                "Date":      exec_failed["Date"].astype(str),
                "Bar":       exec_failed["BarNum"].astype(int),
                "Dir":       exec_failed["Direction"],
                "Signal Px": exec_failed["SignalPrice"].apply(lambda v: f"{v:.2f}"),
                "Stop Px":   exec_failed["StopPrice"].apply(lambda v: f"{v:.2f}"),
                "Reason":    exec_failed["Reason"],
                "Missed by": exec_failed["Missed by (ticks)"].apply(
                    lambda v: f"{v} tks" if pd.notna(v) else "—"
                ),
            })
            st.dataframe(disp, use_container_width=True, hide_index=True)

        # ── Manual fill override form ─────────────────────────────────────────
        st.markdown("**Manual Fill Override**")
        overrides = st.session_state.get("ba_manual_overrides", {})

        fillable = results[results["FilterStatus"].isin({"no_fill", "no_next_bar"})].copy()
        if not fillable.empty:
            ov_cols = st.columns([2, 2, 2, 1])
            sig_opts = {
                f"#{int(r['SignalNum'])} — {r['Date']} Bar {int(r['BarNum'])} {r['Direction']} @ {r['SignalPrice']:.2f}": int(r["SignalNum"])
                for _, r in fillable.iterrows()
            }
            sel_label = ov_cols[0].selectbox("Signal", list(sig_opts.keys()),
                                              key="ov_sig_sel", label_visibility="collapsed")
            sel_num   = sig_opts[sel_label]
            sel_sig   = fillable[fillable["SignalNum"] == sel_num].iloc[0]
            fill_px   = ov_cols[1].number_input("Fill Price", value=float(sel_sig["SignalPrice"]),
                                                 step=0.25, format="%.2f", key="ov_fill_px",
                                                 label_visibility="collapsed")
            fill_bar  = ov_cols[2].number_input("Entry Bar #", value=min(int(sel_sig["BarNum"]) + 1, 81),
                                                 min_value=1, max_value=81, step=1,
                                                 key="ov_fill_bar", label_visibility="collapsed")
            if ov_cols[3].button("Add", use_container_width=True):
                overrides[sel_num] = {"fill_price": fill_px, "fill_bar": int(fill_bar)}
                st.session_state["ba_manual_overrides"] = overrides
                st.rerun()
        else:
            st.caption("No fillable signals to override.")

        # Active overrides
        if overrides:
            st.caption("Active overrides:")
            for sig_num, ov in list(overrides.items()):
                r1, r2 = st.columns([6, 1])
                r1.caption(f"Signal #{sig_num} — fill @ {ov['fill_price']:.2f}  bar {ov['fill_bar']}")
                if r2.button("✕", key=f"rm_ov_{sig_num}"):
                    del overrides[sig_num]
                    st.session_state["ba_manual_overrides"] = overrides
                    st.rerun()

    # ── Signals filtered by user settings ────────────────────────────────────
    filtered = results[~results["FilterStatus"].isin(_EXECUTION_STATUSES | {"ok", "manual_override"})].copy()
    with st.expander(f"Filtered by settings — {len(filtered)} signals", expanded=False):
        if filtered.empty:
            st.info("No signals filtered by current settings.")
        else:
            filtered["Reason"] = filtered["FilterStatus"].map(_FILTER_LABELS).fillna(filtered["FilterStatus"])
            disp = pd.DataFrame({
                "Date":      filtered["Date"].astype(str),
                "Bar":       filtered["BarNum"].astype(int),
                "Dir":       filtered["Direction"],
                "Signal Px": filtered["SignalPrice"].apply(lambda v: f"{v:.2f}"),
                "Reason":    filtered["Reason"],
            })
            st.dataframe(disp, use_container_width=True, hide_index=True)


# ── Mismatch analysis ─────────────────────────────────────────────────────────

def _show_mismatch_analysis(results: pd.DataFrame, sc_bars: pd.DataFrame, nt_bars: pd.DataFrame):
    from validation import build_comparison

    comp = build_comparison(sc_bars, nt_bars)
    # Index comparison by bar open DateTime for fast join
    comp_idx = comp.set_index("DateTime")[["OHLC_match", "ΔOpen", "ΔHigh", "ΔLow", "ΔClose"]].copy()

    filled = results[results["Filled"] == True].copy()
    if filled.empty:
        st.info("No filled trades to analyse.")
        return

    # Signal bar open = signal fire time (bar close) − 5 min
    filled["_SigBarDT"] = filled["DateTime"] - pd.Timedelta(minutes=5)
    filled = filled.join(comp_idx, on="_SigBarDT", how="left")

    # Impact: does the mismatch help or hurt the trade direction?
    # Δ = NT − SC  →  ΔHigh > 0 means NT showed higher high than SC (SC had less upside)
    # LONG favored by:  ΔHigh ≤ 0 (SC high ≥ NT high)  AND  ΔLow ≤ 0 (SC low ≥ NT low)
    # SHORT favored by: ΔHigh ≥ 0 (SC high ≤ NT high)  AND  ΔLow ≥ 0 (SC low ≤ NT low)
    def _impact(row):
        if pd.isna(row.get("ΔHigh")):
            return "No data"
        dh, dl = row["ΔHigh"], row["ΔLow"]
        net = -(dh + dl) if row["Direction"] == "Long" else (dh + dl)
        if net > 0:
            return "Favorable"
        elif net < 0:
            return "Unfavorable"
        return "Neutral"

    filled["Impact"] = filled.apply(_impact, axis=1)

    n_total    = len(filled)
    mism_mask  = filled["OHLC_match"] == False
    n_mismatch = int(mism_mask.sum())

    filled["_Won"] = filled["NetPnL"] > 0
    wr_matched  = filled.loc[~mism_mask, "_Won"].mean()
    wr_mismatch = filled.loc[mism_mask,  "_Won"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Signals on Mismatch Bars", n_mismatch)
    c2.metric("% of Filled Signals",
              f"{n_mismatch / n_total * 100:.1f}%" if n_total else "—")
    c3.metric("Win Rate — Matched",
              f"{wr_matched  * 100:.1f}%" if not pd.isna(wr_matched)  else "—")
    c4.metric("Win Rate — Mismatched",
              f"{wr_mismatch * 100:.1f}%" if not pd.isna(wr_mismatch) else "—")
    delta_wr = (wr_mismatch - wr_matched) if not (pd.isna(wr_mismatch) or pd.isna(wr_matched)) else None
    c5.metric("Win Rate Δ",
              f"{delta_wr * 100:+.1f}%" if delta_wr is not None else "—",
              delta_color="normal" if delta_wr is None else ("normal" if delta_wr >= 0 else "inverse"))

    if n_mismatch == 0:
        st.success("No filled signals fell on mismatched bars.")
        return

    mismatched = filled[mism_mask].copy()

    # Breakdown: favorable vs unfavorable
    impact_counts = mismatched["Impact"].value_counts()
    b1, b2, b3 = st.columns(3)
    b1.metric("Favorable",   int(impact_counts.get("Favorable",   0)), delta_color="off")
    b2.metric("Unfavorable", int(impact_counts.get("Unfavorable", 0)), delta_color="off")
    b3.metric("Neutral",     int(impact_counts.get("Neutral",     0)), delta_color="off")

    IMPACT_STYLE = {
        "Favorable":   "color:#26a69a; font-weight:bold",
        "Unfavorable": "color:#ef5350; font-weight:bold",
        "Neutral":     "color:#888",
        "No data":     "color:#555",
    }

    with st.expander(f"Mismatched signals — detail ({n_mismatch})", expanded=False):
        disp = pd.DataFrame()
        disp["Date"]      = mismatched["Date"].astype(str)
        disp["Bar"]       = mismatched["BarNum"].astype(int)
        disp["Dir"]       = mismatched["Direction"]
        disp["Sig Px"]    = mismatched["SignalPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        disp["Entry Px"]  = mismatched["EntryPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        disp["Exit"]      = mismatched["ExitReason"].replace("", "—")
        disp["Net $"]     = mismatched["NetPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        disp["R"]         = mismatched["R_achieved"].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
        disp["ΔOpen"]     = mismatched["ΔOpen"].round(0).astype("Int64")
        disp["ΔHigh"]     = mismatched["ΔHigh"].round(0).astype("Int64")
        disp["ΔLow"]      = mismatched["ΔLow"].round(0).astype("Int64")
        disp["ΔClose"]    = mismatched["ΔClose"].round(0).astype("Int64")
        disp["Impact"]    = mismatched["Impact"].values

        def _style_impact(s):
            return [IMPACT_STYLE.get(v, "") for v in s]

        def _style_delta(s):
            out = []
            for v in s:
                if pd.isna(v) or v == 0:
                    out.append("color:#888")
                elif v > 0:
                    out.append("color:#26a69a")
                else:
                    out.append("color:#ef5350")
            return out

        styled = (
            disp.style
            .apply(_style_impact, subset=["Impact"])
            .apply(_style_delta,  subset=["ΔOpen", "ΔHigh", "ΔLow", "ΔClose"])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Main tab ──────────────────────────────────────────────────────────────────

def show_bar_analysis(sc_file: str = "", contract: str = "ES", nt_file: str = ""):
    signals_raw = st.session_state.get("ba_signals")
    if signals_raw is None:
        st.info("Upload a signals file in the **📊 MC Signals** panel above to begin.")
        return

    # ── Load data — source determined by bar_source selector in app.py ──────────
    from pathlib import Path
    uploaded_bars  = st.session_state.get("uploaded_sc_bars")
    uploaded_ticks = st.session_state.get("uploaded_sc_ticks")
    uploaded_ohlc  = st.session_state.get("uploaded_ohlc_bars")
    _sc_on_disk    = bool(sc_file and Path(sc_file).exists())
    _bar_source    = st.session_state.get("bar_source", "none")

    if _bar_source == "sc_upload" and uploaded_bars is not None:
        bars = uploaded_bars
    elif _bar_source == "ohlc_upload" and uploaded_ohlc is not None:
        bars = uploaded_ohlc
    elif _bar_source == "sc_disk" and _sc_on_disk:
        bars        = load_sc_bars(sc_file)
    elif uploaded_ohlc is not None:
        bars        = uploaded_ohlc
        _bar_source = "ohlc_upload"
    else:
        st.error("No bar data available. Upload a tick file or OHLC bar_export in the 📁 Upload Data panel.")
        return

    # Tick source hierarchy: uploaded SC ticks → SC disk file (only if bar_source=sc_disk) → empty
    if uploaded_ticks is not None:
        ticks        = uploaded_ticks
        _tick_source = "upload"
    elif _sc_on_disk and _bar_source == "sc_disk":
        ticks        = load_sc_ticks(sc_file)
        _tick_source = "disk"
    else:
        ticks        = pd.DataFrame(columns=["DateTime", "Price", "Volume"])
        _tick_source = "none"

    _bar_sim_mode  = _tick_source == "none"
    _has_1s_bars   = st.session_state.get("data_sc_1s") is not None
    if _bar_sim_mode and not _has_1s_bars:
        st.warning(
            "No tick data — running **bar-level simulation** (5-min OHLC H/L checks). "
            "Fill accuracy is lower than tick-level. Conservative assumption: when both "
            "stop and target are reachable within the same bar, stop is filled first.",
            icon="⚠️",
        )
    elif _bar_sim_mode and _has_1s_bars:
        st.caption("📊 Simulation mode: 1s OHLCV bar-level (near-tick accuracy)")
    if _bar_source == "ohlc_upload":
        st.caption("📊 Bar data: uploaded OHLC bar_export (no SC tick file on disk)")

    # NT bars for mismatch analysis (uploaded OHLC wins over disk file)
    _nt_bars_for_mismatch = uploaded_ohlc
    if _nt_bars_for_mismatch is None and nt_file and Path(nt_file).exists():
        from data_loader import load_nt_bars
        _nt_bars_for_mismatch = load_nt_bars(nt_file)
    nt_bars = _nt_bars_for_mismatch

    # Tick groupby (empty dict when no ticks → bar-level sim handles via bars_by_date)
    _up_key = st.session_state.get("uploaded_sc_key", "")
    tbd_key = (f"ba_ticks_by_date__up_{_up_key}"
               if _tick_source == "upload"
               else f"ba_ticks_by_date_{sc_file}")
    if tbd_key not in st.session_state:
        st.session_state[tbd_key] = (
            {d: grp.reset_index(drop=True) for d, grp in ticks.groupby(ticks["DateTime"].dt.date)}
            if not ticks.empty else {}
        )
    ticks_by_date = st.session_state[tbd_key]

    # Bar groupby for simulation — use 1s bars when available (near-tick accuracy)
    _sim_src = st.session_state.get("data_sc_1s") if _has_1s_bars else None
    _sim_df  = _sim_src if _sim_src is not None else bars
    bars_by_date_sim = {
        d: grp.reset_index(drop=True)
        for d, grp in _sim_df.groupby(_sim_df["DateTime"].dt.date)
    }

    # Expose to Portfolio tab via session state
    st.session_state["pf_ticks_by_date"] = ticks_by_date
    st.session_state["pf_bars_by_date"]  = bars_by_date_sim

    # Attach signal-bar close to each signal (bar open time matches signal DateTime)
    _sb_close_map = bars.set_index("DateTime")["Close"]
    signals_raw["SBClose"] = signals_raw["DateTime"].map(_sb_close_map)

    bars["Date"] = bars["DateTime"].dt.date
    bar_dates    = sorted(bars["Date"].unique())
    sig_min      = signals_raw["Date"].min()
    sig_max      = signals_raw["Date"].max()
    data_min     = bars["Date"].min()
    data_max     = bars["Date"].max()

    # ── Detect data change (contract switch OR new upload) — reset stale date state ──
    _active_key = f"{sc_file}|{st.session_state.get('uploaded_sc_key', '')}|{st.session_state.get('uploaded_ohlc_key', '')}"
    if st.session_state.get("ba_active_data_key") != _active_key:
        for k in ("ba_date_from", "ba_date_to", "ba_chart_idx", "ba_initialized"):
            st.session_state.pop(k, None)
        st.session_state["ba_active_data_key"] = _active_key

    # ── Initialize defaults ───────────────────────────────────────────────────
    if "ba_initialized" not in st.session_state:
        for k, v in _load_ba_defaults().items():
            st.session_state.setdefault(k, v)
        st.session_state["ba_initialized"] = True

    # ── Date range ────────────────────────────────────────────────────────────
    dc1, dc2 = st.columns(2)
    # Clamp defaults to [data_min, data_max] — handles signals from a different year than bars
    _from_default = min(max(sig_min, data_min), data_max)
    _to_default   = max(min(sig_max, data_max), data_min)
    date_from = dc1.date_input("From", value=_from_default,
                                min_value=data_min, max_value=data_max, key="ba_date_from")
    date_to   = dc2.date_input("To",   value=_to_default,
                                min_value=data_min, max_value=data_max, key="ba_date_to")

    # ── Filters expander ──────────────────────────────────────────────────────
    with st.expander("⚙️ Filters", expanded=False):
        st.markdown("**Session Filters**")
        sf1, sf2, sf3 = st.columns(3)
        excl_holidays = sf1.checkbox("Exclude NYSE holidays", key="ba_excl_holidays",
                                      value=st.session_state.get("ba_excl_holidays", True))
        st.markdown("")  # spacer

        st.markdown("**Day of Week**")
        dw1, dw2, dw3, dw4, dw5 = st.columns(5)
        incl_mon = dw1.checkbox("Mon", key="ba_mon", value=st.session_state.get("ba_mon", True))
        incl_tue = dw2.checkbox("Tue", key="ba_tue", value=st.session_state.get("ba_tue", True))
        incl_wed = dw3.checkbox("Wed", key="ba_wed", value=st.session_state.get("ba_wed", True))
        incl_thu = dw4.checkbox("Thu", key="ba_thu", value=st.session_state.get("ba_thu", True))
        incl_fri = dw5.checkbox("Fri", key="ba_fri", value=st.session_state.get("ba_fri", True))

        st.markdown("**Session Boundaries**")
        sb1, sb2 = st.columns(2)
        excl_first_n  = sb1.slider("Exclude first N bars",   0, 12,
                                    st.session_state.get("ba_excl_first_n", 0), 1,
                                    key="ba_excl_first_n")
        excl_last_min = sb2.slider("Exclude last N minutes", 0, 90,
                                    st.session_state.get("ba_excl_last_min", 0), 5,
                                    key="ba_excl_last_min")

        st.divider()
        st.markdown("**Economic Events**")
        if not fred_key_configured():
            st.info("FOMC built-in. Add FRED_API_KEY to .streamlit/secrets.toml for NFP/CPI.")
        ea, eb, ec = st.columns(3)
        use_fomc = ea.checkbox("FOMC", key="ba_fomc", value=st.session_state.get("ba_fomc", False))
        use_nfp  = eb.checkbox("NFP",  key="ba_nfp",  value=st.session_state.get("ba_nfp",  False),
                                disabled=not fred_key_configured())
        use_cpi  = ec.checkbox("CPI",  key="ba_cpi",  value=st.session_state.get("ba_cpi",  False),
                                disabled=not fred_key_configured())
        event_types = tuple(e for e, on in [("FOMC", use_fomc), ("NFP", use_nfp), ("CPI", use_cpi)] if on)

        ef1, ef2 = st.columns([1, 2])
        _efm_default = st.session_state.get("ba_event_mode", "Skip full day")
        event_filter_mode = ef1.radio(
            "Filter mode", ["Skip full day", "Window ±N minutes"],
            index=["Skip full day", "Window ±N minutes"].index(_efm_default),
            key="ba_event_mode",
        )
        event_window = 30
        if event_filter_mode == "Window ±N minutes":
            event_window = ef2.slider("Minutes before/after", 15, 180,
                                       st.session_state.get("ba_event_window", 30), 15,
                                       key="ba_event_window")

    # ── Signals ───────────────────────────────────────────────────────────────
    with st.expander("📶 Signals", expanded=False):
        _cc_cols = st.columns(5)
        incl_cc1 = _cc_cols[0].checkbox("CC1", key="ba_incl_cc1",
                                         value=st.session_state.get("ba_incl_cc1", True))
        incl_cc2 = _cc_cols[1].checkbox("CC2", key="ba_incl_cc2",
                                         value=st.session_state.get("ba_incl_cc2", True))
        incl_cc3 = _cc_cols[2].checkbox("CC3", key="ba_incl_cc3",
                                         value=st.session_state.get("ba_incl_cc3", True))
        incl_cc4 = _cc_cols[3].checkbox("CC4", key="ba_incl_cc4",
                                         value=st.session_state.get("ba_incl_cc4", True))
        incl_cc5 = _cc_cols[4].checkbox("CC5", key="ba_incl_cc5",
                                         value=st.session_state.get("ba_incl_cc5", True))
        _sf_cols = st.columns([2, 2, 3])
        first_trade_only = _sf_cols[0].checkbox("First trade of day only", key="ba_first_trade",
                                                 value=st.session_state.get("ba_first_trade", False),
                                                 on_change=_on_first_trade_change)
        first_2_filled_only = _sf_cols[1].checkbox("First 2 of day", key="ba_first_2_filled",
                                                    value=st.session_state.get("ba_first_2_filled", False),
                                                    on_change=_on_first_2_change)
        _dir_opts = ["Both", "Long", "Short"]
        direction_filter = _sf_cols[2].radio(
            "Direction", _dir_opts, horizontal=True, key="ba_direction_filter",
            index=_dir_opts.index(st.session_state.get("ba_direction_filter", "Both")),
        )

    # ── Trading Parameters expander ───────────────────────────────────────────
    with st.expander("⚙️ Trading Parameters", expanded=False):
        # 3-Leg hidden until tick data is available.
        _mode_opts = ["Single Leg", "2-Leg"]
        _saved_mode = st.session_state.get("ba_trade_mode", "Single Leg")
        if _saved_mode not in _mode_opts:
            _saved_mode = "Single Leg"
        _trade_mode = st.radio(
            "Trade Mode", _mode_opts,
            index=_mode_opts.index(_saved_mode),
            horizontal=True, key="ba_trade_mode_radio",
            label_visibility="collapsed",
        )
        st.session_state["ba_trade_mode"] = _trade_mode
        _is_sl = (_trade_mode == "Single Leg")
        _is_ml = (_trade_mode == "2-Leg")
        _is_3l = False

        _col_sl, _col_ml, _col_3l = st.columns(3)
        _ml_invalid = False

        # -- Single Leg --
        with _col_sl:
            if _is_sl:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_sl",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_sl",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )
                # BE Stop and Stop Ratchet modes hidden — require tick data for
                # accurate bar-level simulation (dynamic stop movement creates
                # intrabar sequence ambiguity).
                _sl_be = False
                st.session_state["ba_sl_mode"] = "AIAO"
                st.number_input(
                    "Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_sl",
                        st.session_state.get("ba_contracts", 1))),
                    key="ba_contracts_sl",
                )
                st.number_input(
                    "Target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_target_r_sl",
                          st.session_state.get("ba_target_r", 2.0))),
                    step=0.25, format="%.2f", key="ba_target_r_sl",
                )
                st.number_input(
                    "Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_sl",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_sl",
                )
                st.number_input(
                    "Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_sl",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_sl",
                )
                st.number_input(
                    "Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_sl",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_sl",
                )
                _def_comm_sl = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_sl", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input(
                    "Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_sl", _def_comm_sl)),
                    step=0.5, format="%.2f", key="ba_commission_sl",
                )
                _sl_c    = int(st.session_state.get("ba_contracts_sl", 1))
                _sl_comm = float(st.session_state.get("ba_commission_sl", _def_comm_sl))
                st.caption(f"{_sl_c}c × ${_sl_comm:.2f} = ${_sl_c * _sl_comm:.2f}/trade")
                if False:  # Stop Ratchet — hidden until tick data available
                    _sl_rdest = st.selectbox("Move stop to",
                        ["BE (entry)", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_sl")
                    if _sl_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_sl", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_sl")

        # -- 2-Leg --
        with _col_ml:
            if _is_ml:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_ml",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_ml",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )
                _r_opts  = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
                _r_lbls  = [f"{v:.2f}R" for v in _r_opts]

                st.caption("**Leg 1 (E1)**")
                contracts_t1 = st.number_input(
                    "E1 Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_t1", 1)),
                    key="ba_contracts_t1",
                )
                _saved_t1_lbl = st.session_state.get("ba_t1_r_sel", "1.00R")
                _t1_idx    = _r_lbls.index(_saved_t1_lbl) if _saved_t1_lbl in _r_lbls else 2
                _t1_sel    = st.selectbox(
                    "T1 (E1 target, R from entry)", _r_lbls, index=_t1_idx,
                    key="ba_t1_r_sel",
                    help="If price hits T1 before PB fills → trade over, E1 profits.",
                )
                t1_r      = _r_opts[_r_lbls.index(_t1_sel)]
                t1_action = "exit"  # scale-in model always exits E1 at T1

                st.caption("**Leg 2 (E2 scale-in)**")
                contracts_t2 = st.number_input(
                    "E2 Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_t2", 1)),
                    key="ba_contracts_t2",
                )
                _pb_vals = [0.0, -0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50, -2.0]
                _pb_lbls = ["None (immediate)", "-0.25R", "-0.33R", "-0.50R",
                            "-0.66R", "-0.75R", "-1.0R", "-1.25R", "-1.50R", "-2.0R"]
                _saved_pb = float(st.session_state.get("ba_ml_pb_r", -0.50))
                _pb_idx   = _pb_vals.index(_saved_pb) if _saved_pb in _pb_vals else 3
                _pb_sel   = st.selectbox(
                    "E2 Pullback (R from entry)", _pb_lbls, index=_pb_idx,
                    key="ba_ml_pb_sel",
                    help="How far price must retrace from E1 entry before E2 fills. "
                         "-0.5R = half-R below E1 entry (for longs).",
                )
                ml_pb_r_v = _pb_vals[_pb_lbls.index(_pb_sel)]

                _saved_t2_lbl = st.session_state.get("ba_t2_r_sel", "2.00R")
                _t2_idx    = _r_lbls.index(_saved_t2_lbl) if _saved_t2_lbl in _r_lbls else 4
                _t2_sel    = st.selectbox(
                    "T2 (R from blended entry)", _r_lbls, index=_t2_idx,
                    key="ba_t2_r_sel",
                    help="Target for combined E1+E2 position. Measured from blended avg entry "
                         "using original stop as risk.",
                )
                target_r_ml = _r_opts[_r_lbls.index(_t2_sel)]

                st.caption("**Execution**")
                st.number_input(
                    "Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_ml",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_ml",
                )
                st.number_input(
                    "Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_ml",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_ml",
                )
                st.number_input(
                    "Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_ml",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_ml",
                )
                _def_comm_ml = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_ml", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input(
                    "Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_ml", _def_comm_ml)),
                    step=0.5, format="%.2f", key="ba_commission_ml",
                )

                _ml_c    = contracts_t1 + contracts_t2
                _ml_comm = float(st.session_state.get("ba_commission_ml", _def_comm_ml))
                st.caption(f"{_ml_c}c × ${_ml_comm:.2f} = ${_ml_c * _ml_comm:.2f}/trade")
                st.caption("**Stop Ratchet**")
                _ml_ratchet = st.checkbox("Enable", value=bool(st.session_state.get("ba_ratchet_ml", False)), key="ba_ratchet_ml")
                if _ml_ratchet:
                    st.number_input("Trigger (R from entry)", 0.25, 10.0,
                        float(st.session_state.get("ba_ratchet_r_ml", 1.0)),
                        step=0.25, format="%.2f", key="ba_ratchet_r_ml")
                    _ml_rdest = st.selectbox("Move stop to",
                        ["BE (entry)", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_ml")
                    if _ml_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_ml", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_ml")

        # -- 3-Leg --
        with _col_3l:
            if _is_3l:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_3l",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_3l",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )

                # ── E1 ────────────────────────────────────────────────────────
                st.markdown("**E1 — Initial entry at signal**")
                e1c_3l = st.number_input("E1 Contracts", 1, 100,
                    int(st.session_state.get("ba_e1c_3l", 1)), key="ba_e1c_3l")
                t1_r_3l = st.number_input("T1 — E1 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_t1_r_3l", 1.0)),
                    step=0.25, format="%.2f", key="ba_t1_r_3l")
                _t1_lbl_3l = st.radio("At T1", ["Exit E1", "BE stop only"],
                    index=0 if st.session_state.get("ba_t1_action_3l", "exit") == "exit" else 1,
                    key="ba_t1_action_3l_radio", horizontal=True)
                t1_action_3l = "exit" if _t1_lbl_3l == "Exit E1" else "be_only"

                st.divider()

                # ── E2 ────────────────────────────────────────────────────────
                st.markdown("**E2 — Pullback entry 1**")
                e2c_3l = st.number_input("E2 Contracts (0 = disabled)", 0, 100,
                    int(st.session_state.get("ba_e2c_3l", 1)), key="ba_e2c_3l")
                _pb1c1, _pb1c2 = st.columns(2)
                _pb1c1.number_input("PB1 (R back)", 0.01, 4.0,
                    float(st.session_state.get("ba_pb1_r_3l", 0.33)),
                    step=0.01, format="%.2f", key="ba_pb1_r_3l",
                    help="How far back from E1 entry (in R) to place the PB1 limit order")
                _pb1c2.number_input("PB1 tick offset", -20, 20,
                    int(st.session_state.get("ba_pb1_ticks_3l", 0)), key="ba_pb1_ticks_3l",
                    help="+= shallower (closer to entry), –= deeper")
                t2_r_3l = st.number_input("T2 — E2 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_t2_r_3l", 2.0)),
                    step=0.25, format="%.2f", key="ba_t2_r_3l")

                st.divider()

                # ── E3 ────────────────────────────────────────────────────────
                st.markdown("**E3 — Pullback entry 2**")
                e3c_3l = st.number_input("E3 Contracts (0 = disabled)", 0, 100,
                    int(st.session_state.get("ba_e3c_3l", 1)), key="ba_e3c_3l")
                _pb2c1, _pb2c2 = st.columns(2)
                _pb2c1.number_input("PB2 (R back)", 0.01, 5.0,
                    float(st.session_state.get("ba_pb2_r_3l", 0.66)),
                    step=0.01, format="%.2f", key="ba_pb2_r_3l",
                    help="Must be deeper than PB1")
                _pb2c2.number_input("PB2 tick offset", -20, 20,
                    int(st.session_state.get("ba_pb2_ticks_3l", 0)), key="ba_pb2_ticks_3l",
                    help="+= shallower, –= deeper")
                target_r_3l = st.number_input("T3 — E3 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_target_r_3l", 3.0)),
                    step=0.25, format="%.2f", key="ba_target_r_3l")

                # Validation
                _pb1_r_v = float(st.session_state.get("ba_pb1_r_3l", 0.33))
                _pb2_r_v = float(st.session_state.get("ba_pb2_r_3l", 0.66))
                _t2_r_v  = float(st.session_state.get("ba_t2_r_3l", 2.0))
                if _pb2_r_v <= _pb1_r_v:
                    st.warning(f"PB2 ({_pb2_r_v:.2f}R) must be > PB1 ({_pb1_r_v:.2f}R).")
                if not (t1_r_3l < _t2_r_v < target_r_3l):
                    st.warning(f"Targets must satisfy T1 ({t1_r_3l}R) < T2 ({_t2_r_v}R) < T3 ({target_r_3l}R).")

                st.divider()

                # ── Execution ─────────────────────────────────────────────────
                st.markdown("**Execution**")
                st.number_input("Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_3l",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_3l")
                st.number_input("Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_3l",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_3l")
                st.number_input("Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_3l",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_3l")
                _def_comm_3l = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_3l", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input("Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_3l", _def_comm_3l)),
                    step=0.5, format="%.2f", key="ba_commission_3l")
                _3l_c_tot = e1c_3l + e2c_3l + e3c_3l
                st.caption(f"E1:{e1c_3l} · E2:{e2c_3l} · E3:{e3c_3l} "
                           f"× ${float(st.session_state.get('ba_commission_3l', _def_comm_3l)):.2f} "
                           f"= ${_3l_c_tot * float(st.session_state.get('ba_commission_3l', _def_comm_3l)):.2f} max/trade")

                st.divider()

                # ── Stop Ratchet ──────────────────────────────────────────────
                st.markdown("**Stop Ratchet**")
                _3l_ratchet = st.checkbox("Enable", value=bool(st.session_state.get("ba_ratchet_3l", False)), key="ba_ratchet_3l")
                if _3l_ratchet:
                    st.number_input("Trigger (R from blended entry)", 0.25, 10.0,
                        float(st.session_state.get("ba_ratchet_r_3l", 1.0)),
                        step=0.25, format="%.2f", key="ba_ratchet_r_3l")
                    _3l_rdest = st.selectbox("Move stop to",
                        ["BE (blended)", "E1 entry", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_3l")
                    if _3l_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_3l", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_3l")

        # ── Derive active parameters ──────────────────────────────────────────
        _sl_be_deriv  = _is_sl and st.session_state.get("ba_sl_mode", "AIAO") == "BE Stop"
        _3l_pb_ok  = float(st.session_state.get("ba_pb2_r_3l", 0.66)) > float(st.session_state.get("ba_pb1_r_3l", 0.33))
        _3l_tgt_ok = (float(st.session_state.get("ba_t1_r_3l", 1.0))
                      < float(st.session_state.get("ba_t2_r_3l", 2.0))
                      < float(st.session_state.get("ba_target_r_3l", 3.0)))
        _3l_valid  = _is_3l and _3l_pb_ok and _3l_tgt_ok

        # Ratchet params (resolved per active mode)
        def _resolve_ratchet(prefix):
            if not st.session_state.get(f"ba_ratchet_{prefix}", False):
                return 0.0, "BE", 0.0
            r_r   = float(st.session_state.get(f"ba_ratchet_r_{prefix}", 1.0))
            dest_raw = st.session_state.get(f"ba_ratchet_dest_{prefix}", "BE (entry)")
            if dest_raw == "Lock-in R":
                dest = "Lock-in"
                lock = float(st.session_state.get(f"ba_ratchet_lock_r_{prefix}", 0.5))
            elif dest_raw == "E1 entry":
                dest, lock = "E1", 0.0
            else:
                dest, lock = "BE", 0.0
            return r_r, dest, lock

        ml_pb_r_v = 0.0  # default; overridden in 2-leg block below

        if _is_3l and _3l_valid:
            use_threeleg = True
            use_multileg = False
            instrument  = st.session_state.get("ba_instrument_3l", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            target_r    = float(st.session_state.get("ba_target_r_3l", 3.0))
            t1_r        = float(st.session_state.get("ba_t1_r_3l", 1.0))
            t2_r_val    = float(st.session_state.get("ba_t2_r_3l", 2.0))
            t1_action   = t1_action_3l  # defined in _col_3l block
            entry_slip  = float(st.session_state.get("ba_entry_slip_3l", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_3l", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_3l", 1))
            commission  = float(st.session_state.get("ba_commission_3l", 4.0))
            contracts   = e1c_3l
            contracts_t1 = e1c_3l; contracts_t2 = e2c_3l + e3c_3l
            pb1_r_val   = float(st.session_state.get("ba_pb1_r_3l", 0.33))
            pb2_r_val   = float(st.session_state.get("ba_pb2_r_3l", 0.66))
            pb1_ticks_v = int(st.session_state.get("ba_pb1_ticks_3l", 0))
            pb2_ticks_v = int(st.session_state.get("ba_pb2_ticks_3l", 0))
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("3l")
        elif _is_ml and not _ml_invalid:
            use_threeleg = False
            use_multileg = True
            instrument  = st.session_state.get("ba_instrument_ml", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            # T2: read from selectbox label → float
            _t2_r_opts  = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
            _t2_r_lbls  = [f"{v:.2f}R" for v in _t2_r_opts]
            _t2_sel_ss  = st.session_state.get("ba_t2_r_sel", "2.00R")
            target_r    = _t2_r_opts[_t2_r_lbls.index(_t2_sel_ss)] if _t2_sel_ss in _t2_r_lbls else 2.0
            entry_slip  = float(st.session_state.get("ba_entry_slip_ml", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_ml", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_ml", 1))
            commission  = float(st.session_state.get("ba_commission_ml", 4.0))
            contracts   = 1
            # PB level: read from selectbox label → float
            _pb_vals_ss = [0.0, -0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50, -2.0]
            _pb_lbls_ss = ["None (immediate)", "-0.25R", "-0.33R", "-0.50R",
                           "-0.66R", "-0.75R", "-1.0R", "-1.25R", "-1.50R", "-2.0R"]
            _pb_sel_ss  = st.session_state.get("ba_ml_pb_sel", "-0.50R")
            ml_pb_r_v   = _pb_vals_ss[_pb_lbls_ss.index(_pb_sel_ss)] if _pb_sel_ss in _pb_lbls_ss else -0.50
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("ml")
            # t1_r, t1_action, contracts_t1, contracts_t2 defined in _col_ml block
        elif _sl_be_deriv:
            use_threeleg = False
            use_multileg = True
            instrument   = st.session_state.get("ba_instrument_sl", "ES")
            tick_value   = INSTRUMENTS[instrument]["tick_value"]
            target_r     = float(st.session_state.get("ba_target_r_sl", 2.0))
            t1_r         = float(st.session_state.get("ba_t1_r_sl", 1.0))
            t1_action    = "be_only"
            contracts_t1 = 0
            contracts_t2 = int(st.session_state.get("ba_contracts_sl", 1))
            entry_slip   = float(st.session_state.get("ba_entry_slip_sl", 0.0))
            exit_slip    = float(st.session_state.get("ba_exit_slip_sl", 0.0))
            stop_offset  = int(st.session_state.get("ba_stop_offset_sl", 1))
            commission   = float(st.session_state.get("ba_commission_sl", 4.0))
            contracts    = 1
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("sl")
        else:
            use_threeleg = False
            use_multileg = False
            instrument  = st.session_state.get("ba_instrument_sl", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            target_r    = float(st.session_state.get("ba_target_r_sl", 2.0))
            entry_slip  = float(st.session_state.get("ba_entry_slip_sl", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_sl", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_sl", 1))
            commission  = float(st.session_state.get("ba_commission_sl", 4.0))
            contracts   = int(st.session_state.get("ba_contracts_sl", 1))
            t1_r        = 1.0; t1_action = "exit"
            contracts_t1 = 0;  contracts_t2 = 0
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("sl")

        # Ensure 3-leg locals always exist (used by sweep calls even in other modes)
        if not _is_3l:
            e1c_3l = e2c_3l = e3c_3l = 1
            pb1_r_val = 0.33; pb2_r_val = 0.66
            pb1_ticks_v = pb2_ticks_v = 0
            t1_action_3l = "exit"
            target_r_3l = 3.0; t1_r_3l = 1.0; t2_r_val = 2.0; _t2_r_v = 2.0

        st.divider()
        if st.button("💾 Save as Default", key="ba_save_defaults"):
            _save_ba_defaults({
                "ba_incl_cc1": incl_cc1, "ba_incl_cc2": incl_cc2,
                "ba_incl_cc3": incl_cc3, "ba_incl_cc4": incl_cc4, "ba_incl_cc5": incl_cc5,
                "ba_first_trade": first_trade_only,
                "ba_first_2_filled": first_2_filled_only,
                "ba_direction_filter": direction_filter,
                "ba_excl_holidays": excl_holidays,
                "ba_mon": incl_mon, "ba_tue": incl_tue, "ba_wed": incl_wed,
                "ba_thu": incl_thu, "ba_fri": incl_fri,
                "ba_excl_first_n": excl_first_n, "ba_excl_last_min": excl_last_min,
                "ba_fomc": use_fomc, "ba_nfp": use_nfp, "ba_cpi": use_cpi,
                "ba_event_mode": event_filter_mode, "ba_event_window": event_window,
                "ba_trade_mode": st.session_state.get("ba_trade_mode", "Single Leg"),
                # Single-leg
                "ba_instrument_sl": st.session_state.get("ba_instrument_sl", "ES"),
                "ba_sl_mode": st.session_state.get("ba_sl_mode", "AIAO"),
                "ba_contracts_sl": int(st.session_state.get("ba_contracts_sl", 1)),
                "ba_t1_r_sl": float(st.session_state.get("ba_t1_r_sl", 1.0)),
                "ba_target_r_sl": float(st.session_state.get("ba_target_r_sl", 2.0)),
                "ba_entry_slip_sl": float(st.session_state.get("ba_entry_slip_sl", 0.0)),
                "ba_exit_slip_sl": float(st.session_state.get("ba_exit_slip_sl", 0.0)),
                "ba_stop_offset_sl": int(st.session_state.get("ba_stop_offset_sl", 1)),
                "ba_commission_sl": float(st.session_state.get("ba_commission_sl", 4.0)),
                "ba_ratchet_sl": bool(st.session_state.get("ba_ratchet_sl", False)),
                "ba_ratchet_r_sl": float(st.session_state.get("ba_ratchet_r_sl", 1.0)),
                "ba_ratchet_dest_sl": st.session_state.get("ba_ratchet_dest_sl", "BE (entry)"),
                "ba_ratchet_lock_r_sl": float(st.session_state.get("ba_ratchet_lock_r_sl", 0.5)),
                # 2-leg
                "ba_instrument_ml": st.session_state.get("ba_instrument_ml", "ES"),
                "ba_contracts_t1": int(st.session_state.get("ba_contracts_t1", 1)),
                "ba_t1_r": float(st.session_state.get("ba_t1_r", 1.0)),
                "ba_t1_action": t1_action,
                "ba_contracts_t2": int(st.session_state.get("ba_contracts_t2", 1)),
                "ba_target_r_ml": float(st.session_state.get("ba_target_r_ml", 2.0)),
                "ba_entry_slip_ml": float(st.session_state.get("ba_entry_slip_ml", 0.0)),
                "ba_exit_slip_ml": float(st.session_state.get("ba_exit_slip_ml", 0.0)),
                "ba_stop_offset_ml": int(st.session_state.get("ba_stop_offset_ml", 1)),
                "ba_commission_ml": float(st.session_state.get("ba_commission_ml", 4.0)),
                "ba_ratchet_ml": bool(st.session_state.get("ba_ratchet_ml", False)),
                "ba_ratchet_r_ml": float(st.session_state.get("ba_ratchet_r_ml", 1.0)),
                "ba_ratchet_dest_ml": st.session_state.get("ba_ratchet_dest_ml", "BE (entry)"),
                "ba_ratchet_lock_r_ml": float(st.session_state.get("ba_ratchet_lock_r_ml", 0.5)),
                # 3-leg
                "ba_instrument_3l": st.session_state.get("ba_instrument_3l", "ES"),
                "ba_e1c_3l": int(st.session_state.get("ba_e1c_3l", 1)),
                "ba_e2c_3l": int(st.session_state.get("ba_e2c_3l", 1)),
                "ba_e3c_3l": int(st.session_state.get("ba_e3c_3l", 1)),
                "ba_pb1_r_3l": float(st.session_state.get("ba_pb1_r_3l", 0.5)),
                "ba_pb1_ticks_3l": int(st.session_state.get("ba_pb1_ticks_3l", 0)),
                "ba_pb2_r_3l": float(st.session_state.get("ba_pb2_r_3l", 1.0)),
                "ba_pb2_ticks_3l": int(st.session_state.get("ba_pb2_ticks_3l", 0)),
                "ba_t1_r_3l": float(st.session_state.get("ba_t1_r_3l", 1.0)),
                "ba_t1_action_3l": t1_action_3l,
                "ba_target_r_3l": float(st.session_state.get("ba_target_r_3l", 2.0)),
                "ba_entry_slip_3l": float(st.session_state.get("ba_entry_slip_3l", 0.0)),
                "ba_exit_slip_3l": float(st.session_state.get("ba_exit_slip_3l", 0.0)),
                "ba_stop_offset_3l": int(st.session_state.get("ba_stop_offset_3l", 1)),
                "ba_commission_3l": float(st.session_state.get("ba_commission_3l", 4.0)),
                "ba_ratchet_3l": bool(st.session_state.get("ba_ratchet_3l", False)),
                "ba_ratchet_r_3l": float(st.session_state.get("ba_ratchet_r_3l", 1.0)),
                "ba_ratchet_dest_3l": st.session_state.get("ba_ratchet_dest_3l", "BE (blended)"),
                "ba_ratchet_lock_r_3l": float(st.session_state.get("ba_ratchet_lock_r_3l", 0.5)),
            })
            st.success("Defaults saved.", icon="✅")

    # ── Apply filters & simulate ──────────────────────────────────────────────
    filtered_signals = apply_signal_filters(
        signals_raw, date_from, date_to, excl_holidays,
        [incl_mon, incl_tue, incl_wed, incl_thu, incl_fri],
        excl_first_n, excl_last_min,
        event_types, event_filter_mode, event_window,
        incl_cc1, incl_cc2, incl_cc3, incl_cc4, incl_cc5,
        direction_filter,
    )

    results = simulate_trades(
        filtered_signals, ticks_by_date, target_r,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        overrides=st.session_state.get("ba_manual_overrides"),
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        ratchet_r=ratchet_r_v, ratchet_dest=ratchet_dest_v, ratchet_lock_r=ratchet_lock_r_v,
        ml_pb_r=ml_pb_r_v,
        threeleg=use_threeleg,
        contracts_e1=e1c_3l, contracts_e2=e2c_3l, contracts_e3=e3c_3l,
        pb1_r=pb1_r_val, pb1_ticks=pb1_ticks_v,
        pb2_r=pb2_r_val, pb2_ticks=pb2_ticks_v,
        t2_r=t2_r_val,
    )

    # First trade of day — only the first *filled* trade per day counts
    if first_trade_only and not results.empty:
        _filled_mask = results["Filled"] == True
        _filled_sorted = results[_filled_mask].sort_values(["Date", "SignalNum"])
        _keep_idx = _filled_sorted.groupby("Date").head(1).index
        _beyond_idx = results[_filled_mask & ~results.index.isin(_keep_idx)].index
        results = results.drop(_beyond_idx).reset_index(drop=True)

    # First 2 of day — only the first 2 *filled* trades per day count
    if first_2_filled_only and not results.empty:
        _filled_mask = results["Filled"] == True
        _filled_sorted = results[_filled_mask].sort_values(["Date", "SignalNum"])
        _keep_idx = _filled_sorted.groupby("Date").head(2).index
        _beyond_idx = results[_filled_mask & ~results.index.isin(_keep_idx)].index
        results = results.drop(_beyond_idx).reset_index(drop=True)

    _summary_contracts = e1c_3l + e2c_3l + e3c_3l if use_threeleg else contracts
    summary = compute_summary(results, commission,
                              contracts=_summary_contracts,
                              is_multileg=(use_multileg or use_threeleg),
                              t1_action=t1_action,
                              contracts_t1=contracts_t1, contracts_t2=contracts_t2)

    # ── Summary — pre-compute shared derived values ───────────────────────────
    if summary:
        _pf_str    = f"{summary['pf']:.2f}" if summary['pf'] < 99 else "∞"
        _wl_str    = f"{summary['wl_ratio']:.2f}" if summary['wl_ratio'] < 99 else "∞"
        _slip_usd  = summary.get("slippage_total", 0.0)
        if use_multileg:
            _slip_tks = int(round(_slip_usd / tick_value)) if tick_value > 0 else 0
        else:
            _slip_tks = int((entry_slip + exit_slip) * summary["n_trades"] * contracts)
        _slip_str      = f"{_slip_tks} tks  /  ${_slip_usd:.0f}"
        # Actual commission = gross − net (slippage already embedded in gross prices)
        _actual_comm   = summary["gross_total"] - summary["net_total"]
        _total_cost    = _slip_usd + _actual_comm
        _dd_abs        = abs(summary["max_dd"]) if summary["max_dd"] != 0 else None
        _pnl_dd        = summary["net_total"] / _dd_abs if _dd_abs else None
        _ci_lo         = summary.get("exp_r_ci_lo", np.nan)
        _ci_hi         = summary.get("exp_r_ci_hi", np.nan)
        _ci_known      = not (np.isnan(_ci_lo) or np.isnan(_ci_hi))
        _exp_r_help    = (f"95 % CI  [{_ci_lo:+.2f}, {_ci_hi:+.2f}]") if _ci_known else None

    # ── PDF export ───────────────────────────────────────────────────────────
    st.markdown("""
<style>
@media print {
    header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
    [data-testid="stSidebar"],[data-testid="stStatusWidget"],footer,.stButton,
    [data-testid="stFileUploadDropzone"] { display: none !important; }
    details[data-testid="stExpander"] { display: block !important; }
    details[data-testid="stExpander"] > div,
    details[data-testid="stExpander"] > section { display: block !important; }
    .block-container { max-width: 100% !important; padding: 0.5rem !important; }
    .js-plotly-plot, .plotly, .plot-container { height: 580px !important; min-height: 580px !important; }
    .js-plotly-plot .svg-container { height: 580px !important; }
    @page { size: landscape; margin: 1.2cm; }
}
</style>""", unsafe_allow_html=True)
    _pdf_col = st.columns([10, 2])[1]
    if _pdf_col.button("📄 Export PDF", key="ba_pdf_btn", use_container_width=True,
                       help="Opens browser print dialog — choose 'Save as PDF', check Downloads."):
        import streamlit.components.v1 as _cmp
        _pn = st.session_state.get("_ba_pdf_n", 0) + 1
        st.session_state["_ba_pdf_n"] = _pn
        _cmp.html(
            f"""<script>
(function(){{
    var w = window.parent;
    // Print the page exactly as it currently looks — no expander changes.
    // The Daily Chart (already expanded) gets relayout to ~full page height.
    var _plot = null;
    var _orig = 520;
    function findChart() {{
        var found = null;
        w.document.querySelectorAll('details').forEach(function(d) {{
            if (!d.open) return;
            var s = d.querySelector('summary');
            if (s && s.textContent.indexOf('Daily Chart') >= 0) {{
                found = d.querySelector('.js-plotly-plot');
            }}
        }});
        return found;
    }}
    function bp() {{ _plot = findChart(); if (_plot && w.Plotly) {{ _orig = _plot.clientHeight || 520; w.Plotly.relayout(_plot, {{height: 680}}); }} }}
    function ap() {{ if (_plot && w.Plotly) w.Plotly.relayout(_plot, {{height: _orig}}); }}
    w.matchMedia('print').addEventListener('change', function(e) {{ if (e.matches) bp(); else ap(); }});
    w.addEventListener('beforeprint', bp);
    w.addEventListener('afterprint',  ap);
    setTimeout(function(){{ w.print(); }}, 150);
}})(); // {_pn}
</script>""",
            height=0,
        )

    # ── Quick View (expanded by default) ─────────────────────────────────────
    with st.expander("📋 Quick View", expanded=True):
        if summary:
            r1 = st.columns(6)
            r1[0].metric("Net PnL",   f"${summary['net_total']:,.0f}")
            r1[1].metric("Win %",     f"{summary['win_pct']:.1f}%",
                         help=f"W{summary['n_wins']} / L{summary['n_stop']} / S{summary['n_sess']}")
            r1[2].metric("Exp R",     f"{summary['exp_r']:+.2f}", help=_exp_r_help)
            r1[3].metric("PnL/DD",    f"{_pnl_dd:.2f}" if _pnl_dd is not None else "—")
            # SQN is unreliable for multi-leg (high R variance by design) — show PF instead
            if use_multileg or use_threeleg:
                r1[4].metric("PF",    _pf_str)
            else:
                r1[4].metric("SQN",   f"{summary['sqn']:+.2f}")
            r1[5].metric("Max DD",    f"${summary['max_dd']:,.0f}")

            r2 = st.columns(6)
            r2[0].metric("Trades",    f"{summary['n_trades']}")
            r2[1].metric("Avg Win",   f"${summary['avg_win']:+.0f}")
            r2[2].metric("Avg Loss",  f"${summary['avg_loss']:+.0f}")
            r2[3].metric("Median W",  f"${summary['median_win']:+.0f}")
            r2[4].metric("Median L",  f"${summary['median_loss']:+.0f}")
            r2[5].metric("Days",      f"{summary['trading_days']}")
        else:
            st.info("No filled trades in the selected range.")

    # ── Detail (collapsed) ────────────────────────────────────────────────────
    with st.expander("📊 Detail", expanded=False):
        if summary:
            r1 = st.columns(6)
            r1[0].metric("Signals",       f"{summary['n_total']}")
            r1[1].metric("Filtered Out",  f"{summary['n_filtered']}")
            r1[2].metric("Gross PnL",     f"${summary['gross_total']:,.0f}")
            r1[3].metric("Profit Factor", _pf_str)
            r1[4].metric("W/L Ratio",     _wl_str)
            r1[5].metric("Exp $",         f"${summary['exp_dollar']:+.0f}")

            r2 = st.columns(6)
            r2[0].metric("Slippage",      _slip_str)
            r2[1].metric("Commission",    f"${_actual_comm:.0f}")
            r2[2].metric("Total Cost",    f"${_total_cost:.0f}")
            r2[3].metric("Max Risk $",    f"${summary['max_risk_dollar']:,.0f}")
            r2[4].metric("Avg Risk $",    f"${summary['avg_risk_dollar']:,.0f}")
            r2[5].metric("Std R",         f"{summary['r_std']:.3f}")

            r3 = st.columns(6)
            r3[0].metric("Avg MAE",       f"{summary['avg_mae_pts']:.2f} pts")
            r3[1].metric("Avg MFE",       f"{summary['avg_mfe_pts']:.2f} pts")
            r3[2].metric("MAE R",         f"{summary['avg_mae_R']:.2f}")
            r3[3].metric("MFE R",         f"{summary['avg_mfe_R']:.2f}")
            r3[4].metric("Largest Win",   f"${summary['largest_win']:+.0f}")
            r3[5].metric("Largest Loss",  f"${summary['largest_loss']:+.0f}")
        else:
            st.info("No filled trades in the selected range.")

    # ── Edge Analysis ─────────────────────────────────────────────────────────
    with st.expander("📊 Edge Analysis", expanded=False):
        if summary and not results.empty:
            _ea_filled = results[results["Filled"] == True].copy()
            _ea_wins   = _ea_filled[
                _ea_filled["ExitReason"].str.contains("Target", na=False) |
                _ea_filled["ExitReason"].isin(["T1+BE", "T1_only"])
            ]
            _ea_losses = _ea_filled[_ea_filled["ExitReason"].isin(["Stop", "E1E2+Stop"])]

            # ── R-multiple histogram ──────────────────────────────────────────
            _r_vals = _ea_filled["R_achieved"].dropna()
            if not _r_vals.empty:
                _exp_r  = float(_r_vals.mean())
                _r_pos  = _r_vals[_r_vals >= 0]
                _r_neg  = _r_vals[_r_vals < 0]
                _fig_r  = go.Figure()
                _bin_sz = 0.1
                if not _r_pos.empty:
                    _fig_r.add_trace(go.Histogram(
                        x=_r_pos, name="Positive R", xbins=dict(size=_bin_sz),
                        marker_color="rgba(46,204,113,0.75)", marker_line_width=0,
                    ))
                if not _r_neg.empty:
                    _fig_r.add_trace(go.Histogram(
                        x=_r_neg, name="Negative R", xbins=dict(size=_bin_sz),
                        marker_color="rgba(231,76,60,0.75)", marker_line_width=0,
                    ))
                _ci_lo_ea = summary.get("exp_r_ci_lo", np.nan)
                _ci_hi_ea = summary.get("exp_r_ci_hi", np.nan)
                if not (np.isnan(_ci_lo_ea) or np.isnan(_ci_hi_ea)):
                    _fig_r.add_vrect(x0=_ci_lo_ea, x1=_ci_hi_ea,
                                     fillcolor="rgba(243,156,18,0.25)", line_width=0)
                    _fig_r.add_annotation(
                        x=_ci_lo_ea, y=1, yref="paper", xanchor="right",
                        text=f"95% CI [{_ci_lo_ea:+.2f}, {_ci_hi_ea:+.2f}]",
                        showarrow=False, font=dict(color="#f39c12", size=11),
                        bgcolor="rgba(0,0,0,0.4)",
                    )
                _fig_r.add_vline(x=0, line_color="rgba(255,255,255,0.4)", line_dash="dot")
                _fig_r.add_vline(x=_exp_r, line_color="#f39c12", line_dash="dash",
                                 annotation_text=f"Exp R {_exp_r:+.2f}",
                                 annotation_position="top left")
                _fig_r.update_layout(
                    barmode="overlay", height=300, margin=dict(l=40, r=20, t=30, b=40),
                    legend=dict(orientation="h", y=1.08),
                    xaxis_title="R multiple (E1 basis)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_r, use_container_width=True)

            # ── MAE / MFE by outcome ──────────────────────────────────────────
            _mae_col = "MAE_R"
            _mfe_col = "MFE_R"
            _col_l, _col_r = st.columns(2)

            with _col_l:
                st.caption("**MAE R — how far price moved against you** (winners blue, losers red)")
                _mae_w = _ea_wins[_mae_col].dropna()
                _mae_l = _ea_losses[_mae_col].dropna()
                _fig_mae = go.Figure()
                if not _mae_w.empty:
                    _fig_mae.add_trace(go.Histogram(
                        x=_mae_w, name="Winners", xbins=dict(size=0.05),
                        marker_color="rgba(52,152,219,0.7)", marker_line_width=0,
                    ))
                if not _mae_l.empty:
                    _fig_mae.add_trace(go.Histogram(
                        x=_mae_l, name="Losers", xbins=dict(size=0.05),
                        marker_color="rgba(231,76,60,0.7)", marker_line_width=0,
                    ))
                _fig_mae.update_layout(
                    barmode="overlay", height=260, margin=dict(l=40, r=10, t=20, b=40),
                    legend=dict(orientation="h", y=1.1),
                    xaxis_title="MAE (R)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_mae, use_container_width=True)

            with _col_r:
                st.caption("**MFE R — best price reached before exit** (winners blue, losers red)")
                _mfe_w = _ea_wins[_mfe_col].dropna()
                _mfe_l = _ea_losses[_mfe_col].dropna()
                _fig_mfe = go.Figure()
                if not _mfe_w.empty:
                    _fig_mfe.add_trace(go.Histogram(
                        x=_mfe_w, name="Winners", xbins=dict(size=0.05),
                        marker_color="rgba(52,152,219,0.7)", marker_line_width=0,
                    ))
                if not _mfe_l.empty:
                    _fig_mfe.add_trace(go.Histogram(
                        x=_mfe_l, name="Losers", xbins=dict(size=0.05),
                        marker_color="rgba(231,76,60,0.7)", marker_line_width=0,
                    ))
                _fig_mfe.update_layout(
                    barmode="overlay", height=260, margin=dict(l=10, r=10, t=20, b=40),
                    legend=dict(orientation="h", y=1.1),
                    xaxis_title="MFE (R)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_mfe, use_container_width=True)

            # ── Drawdown events table ─────────────────────────────────────────
            st.markdown("**Drawdown periods**")
            _dd_sorted  = _ea_filled.sort_values(["Date", "EntryTime"]).reset_index(drop=True)
            _dd_pnl     = _dd_sorted["NetPnL"].values
            _dd_dates   = _dd_sorted["Date"].values
            _n_dd       = len(_dd_pnl)
            _dd_equity  = np.zeros(_n_dd + 1)
            for _i in range(_n_dd):
                _dd_equity[_i + 1] = _dd_equity[_i] + _dd_pnl[_i]

            _dd_events = []
            _pk        = 0.0
            _pk_date   = None
            _in_dd     = False
            _tr_val    = 0.0
            _tr_date   = None

            for _i in range(1, _n_dd + 1):
                _v = _dd_equity[_i]
                _d = _dd_dates[_i - 1]
                if _v >= _pk:
                    if _in_dd:
                        _dd_events.append({
                            "Start":    str(_pk_date),
                            "Trough":   str(_tr_date),
                            "Recovery": str(_d),
                            "DD $":     f"${_tr_val - _pk:,.0f}",
                            "Days":     (pd.Timestamp(_d) - pd.Timestamp(_pk_date)).days,
                        })
                        _in_dd = False
                    _pk      = _v
                    _pk_date = _d
                else:
                    if not _in_dd:
                        _in_dd   = True
                        _tr_val  = _v
                        _tr_date = _d
                    elif _v < _tr_val:
                        _tr_val  = _v
                        _tr_date = _d

            if _in_dd:
                _dd_events.append({
                    "Start":    str(_pk_date),
                    "Trough":   str(_tr_date),
                    "Recovery": "—",
                    "DD $":     f"${_tr_val - _pk:,.0f}",
                    "Days":     (pd.Timestamp(_dd_dates[-1]) - pd.Timestamp(_pk_date)).days,
                })

            if _dd_events:
                _dd_df = pd.DataFrame(_dd_events).sort_values("DD $")
                st.dataframe(_dd_df, use_container_width=True, hide_index=True)
            else:
                st.success("No drawdown periods — equity curve is monotonically increasing.")
        else:
            st.info("Run a simulation first.")

    # ── Ratchet bar-ambiguity diagnostic (AIAO+ratchet mode only) ────────────
    _is_aiao_ratchet = (not use_multileg and not use_threeleg and ratchet_r_v > 0)
    if _is_aiao_ratchet:
        with st.expander("🔬 Ratchet BE-Stop Diagnostic", expanded=False):
            st.caption(
                "Finds AIAO trades that stopped at ~BE after ratchet fired, "
                "then re-simulates each as BE Stop to show what the outcome "
                "would have been. Isolates the bar-level intrabar ambiguity."
            )
            if st.button("Run Diagnostic", key="ba_run_ratchet_diag"):
                with st.spinner("Re-simulating…"):
                    diag_df = diagnose_ratchet_bar_ambiguities(
                        results,
                        ticks_by_date,
                        bars_by_date_sim,
                        ratchet_r=ratchet_r_v,
                        target_r=target_r,
                        tick_value=tick_value,
                        entry_slip=entry_slip,
                        exit_slip=exit_slip,
                        stop_offset=stop_offset,
                        commission=commission,
                        contracts=contracts,
                    )
                st.session_state["ba_diag_df"] = diag_df

            diag_df = st.session_state.get("ba_diag_df")
            if diag_df is not None and not diag_df.empty:
                n_amb   = int(diag_df["Ambiguous_Bar"].sum())
                n_total_be = len(diag_df)
                delta_sum  = diag_df["PnL_Delta"].sum()
                amb_delta  = diag_df.loc[diag_df["Ambiguous_Bar"], "PnL_Delta"].sum() if n_amb else 0

                mc = st.columns(4)
                mc[0].metric("BE-stop trades found",   n_total_be)
                mc[1].metric("Confirmed ambiguous bars", n_amb)
                mc[2].metric("Total PnL delta (all)",  f"${delta_sum:+,.0f}")
                mc[3].metric("PnL delta (ambiguous bars only)", f"${amb_delta:+,.0f}")

                show_all = st.checkbox("Show all BE-stop trades (uncheck = ambiguous only)",
                                       value=False, key="ba_diag_all")
                display_df = (diag_df if show_all else diag_df[diag_df["Ambiguous_Bar"]]).copy()
                # Convert bool to readable label before display
                display_df["Ambiguous_Bar"] = display_df["Ambiguous_Bar"].map(
                    {True: "YES — same bar", False: "no"}
                )
                # Colour-code BEStop_Exit column
                def _be_color(v):
                    if isinstance(v, str):
                        if "Target" in v:  return "color:#26a69a;font-weight:bold"
                        if v == "T1+BE":   return "color:#ff9800"
                    return ""
                st.dataframe(
                    display_df.style.format({
                        "Entry": "{:.2f}", "Stop": "{:.2f}", "T1_Level": "{:.2f}",
                        "Bar_Hi": "{:.2f}", "Bar_Lo": "{:.2f}",
                        "AIAO_Px": "{:.2f}", "AIAO_Net": "${:,.0f}",
                        "BEStop_Px": "{:.2f}", "BEStop_Net": "${:,.0f}",
                        "PnL_Delta": "${:+,.0f}",
                    }).map(
                        lambda v: "background-color:#1a3a1a" if v == "YES — same bar" else "",
                        subset=["Ambiguous_Bar"]
                    ).map(_be_color, subset=["BEStop_Exit"]),
                    use_container_width=True,
                )
                st.caption(
                    "**Ambiguous_Bar = YES** — the exit bar's Hi crossed T1_Level AND its Lo "
                    "crossed Entry on the same bar. AIAO stopped out; BE Stop let it live.  "
                    "**BEStop_Exit: T1+Target** (green) = real money left on table. "
                    "**T1+BE** (orange) = same exit price, only classification differs.  "
                    f"Sum across all {n_total_be} trades: **${delta_sum:+,.0f}**."
                )
            elif diag_df is not None:
                st.success("No ratchet-triggered BE stops found in this result set.")

    # ── Same-Bar Conflict diagnostic ─────────────────────────────────────────
    _sbc_df = results[results["SameBarConflict"] == True].copy() \
        if "SameBarConflict" in results.columns else pd.DataFrame()
    with st.expander(
        f"⚠️ Same-Bar Conflicts  ({len(_sbc_df)} trades)" if not _sbc_df.empty
        else "⚠️ Same-Bar Conflicts  (none found)",
        expanded=not _sbc_df.empty,
    ):
        if _sbc_df.empty:
            st.success(
                "No same-bar conflicts found: no trade's stop AND target "
                "were both reachable in the same bar."
            )
        else:
            st.caption(
                "These trades had both their **stop AND target reachable in the same bar**. "
                "The conservative bar rule applied: stop wins. "
                "The outcome may have been different with tick-level data."
            )
            _ts = TICK_SIZE
            # Derive $ per tick per trade from existing GrossPnL / GrossPnLPts
            # Works for single-leg; for 2-leg it gives blended TV (good enough for direction).
            _sbc_df["_tv"] = _sbc_df.apply(
                lambda r: r["GrossPnL"] / (r["GrossPnLPts"] / _ts)
                if abs(r.get("GrossPnLPts", 0)) > 1e-6 else np.nan,
                axis=1,
            )
            # For single-leg, hypothetical: target wins instead of stop
            # Delta = (Target - ActualStop) * sign(direction) / ts * tv
            def _if_target_won(r):
                tv = r["_tv"]
                if np.isnan(tv):
                    return np.nan
                if r["Direction"] == "Long":
                    delta_pts = r["Target"] - r["ActualStop"]
                else:
                    delta_pts = r["ActualStop"] - r["Target"]
                return r["NetPnL"] + delta_pts / _ts * tv

            _sbc_df["IfTargetWon"] = _sbc_df.apply(_if_target_won, axis=1)
            _sbc_df["PnL_Delta"]   = _sbc_df["IfTargetWon"] - _sbc_df["NetPnL"]
            total_delta = _sbc_df["PnL_Delta"].sum()

            _mc = st.columns(3)
            _mc[0].metric("Trades affected", len(_sbc_df))
            _mc[1].metric("PnL delta if targets won", f"${total_delta:+,.0f}")
            _mc[2].metric("Avg delta / trade", f"${total_delta / len(_sbc_df):+,.0f}")

            _disp = _sbc_df[[
                "Date", "Direction", "EntryPrice", "ActualStop", "Target",
                "ExitReason", "NetPnL", "IfTargetWon", "PnL_Delta",
            ]].rename(columns={
                "Direction": "Dir", "EntryPrice": "Entry",
                "ActualStop": "Stop", "ExitReason": "ExitResult",
                "IfTargetWon": "IfTgtWon_Net",
            }).copy()

            st.dataframe(
                _disp.style.format({
                    "Entry": "{:.2f}", "Stop": "{:.2f}", "Target": "{:.2f}",
                    "NetPnL": "${:,.0f}", "IfTgtWon_Net": "${:,.0f}",
                    "PnL_Delta": "${:+,.0f}",
                }).map(
                    lambda v: "color:#ef5350" if isinstance(v, (int, float)) and v < 0 else
                              "color:#26a69a" if isinstance(v, (int, float)) and v > 0 else "",
                    subset=["PnL_Delta"],
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "**IfTgtWon_Net** — hypothetical net P&L if the target had been reached "
                "before the stop (tick-level outcome unknown). "
                "For 2-Leg Phase-2 BE conflicts the delta is computed as if T2 had won over BE stop."
            )

    # ── Optimal R / PB sweep ─────────────────────────────────────────────────
    _show_optimal_r(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        threeleg=use_threeleg,
        tv_e1=tick_value * e1c_3l, tv_e2=tick_value * e2c_3l, tv_e3=tick_value * e3c_3l,
        e1c=e1c_3l, e2c=e2c_3l, e3c=e3c_3l,
        pb1_ticks=pb1_ticks_v, pb2_ticks=pb2_ticks_v,
        t2_r=t2_r_val,
        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
    )

    # ── Stop multiplier sweep ─────────────────────────────────────────────────
    _show_stop_sweep(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        target_r=target_r,
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
    )

    # ── Monthly breakdown ──────────────────────────────────────────────────────
    _show_monthly_breakdown(results, commission)

    # ── Unfilled signals ──────────────────────────────────────────────────────
    _show_unfilled_table(results, ticks_by_date)

    # ── Per-day chart ─────────────────────────────────────────────────────────
    in_range   = results[(results["Date"] >= date_from) & (results["Date"] <= date_to)]
    filled_all = in_range[in_range["Filled"]]

    with st.expander("📈 Daily Chart", expanded=True):
        _trade_filter = st.radio(
            "Show dates with:", ["All signals", "Winners only", "Losers only"],
            horizontal=True, key="ba_trade_filter",
        )

        if _trade_filter == "Winners only":
            _win_dates   = set(filled_all.loc[filled_all["ExitReason"] == "Target", "Date"])
            signal_dates = sorted(d for d in in_range["Date"].unique() if d in _win_dates)
        elif _trade_filter == "Losers only":
            _loss_dates  = set(filled_all.loc[filled_all["ExitReason"] == "Stop", "Date"])
            signal_dates = sorted(d for d in in_range["Date"].unique() if d in _loss_dates)
        else:
            signal_dates = sorted(in_range["Date"].unique())

        if not signal_dates:
            label = "winners" if _trade_filter == "Winners only" else "losers"
            st.info(f"No dates with {label} in the selected range.")
            return

        if st.session_state.get("_last_trade_filter") != _trade_filter:
            st.session_state["ba_chart_idx"] = len(signal_dates) - 1
            st.session_state["_last_trade_filter"] = _trade_filter

        if "ba_chart_idx" not in st.session_state:
            st.session_state["ba_chart_idx"] = len(signal_dates) - 1
        st.session_state["ba_chart_idx"] = min(st.session_state["ba_chart_idx"], len(signal_dates) - 1)

        cc1, cc2, cc3 = st.columns([1, 1, 14])
        if cc1.button("‹", key="ba_prev"):
            st.session_state["ba_chart_idx"] = max(0, st.session_state["ba_chart_idx"] - 1)
        if cc2.button("›", key="ba_next"):
            st.session_state["ba_chart_idx"] = min(len(signal_dates) - 1, st.session_state["ba_chart_idx"] + 1)

        selected_date = cc3.selectbox(
            "Date", options=signal_dates,
            index=st.session_state["ba_chart_idx"],
            format_func=lambda d: pd.Timestamp(d).strftime("%A %b %d, %Y"),
        )
        st.session_state["ba_chart_idx"] = list(signal_dates).index(selected_date)

        day_bars    = bars[bars["Date"] == selected_date].drop(columns="Date").reset_index(drop=True)
        day_results = results[results["Date"] == selected_date]

        if len(day_bars) < 81:
            first_bar_time = day_bars.iloc[0]["DateTime"].strftime("%H:%M") if not day_bars.empty else "?"
            st.warning(f"Incomplete data: {len(day_bars)} bars, starts {first_bar_time} (not 08:30). "
                       "Bar numbers reflect position from 08:30.")

        ctrl_l, ctrl_r = st.columns(2)
        show_bar_nums = ctrl_l.checkbox("Show bar numbers", value=False, key="ba_show_bar_nums")
        show_hover    = ctrl_r.checkbox("Show hover labels", value=True, key="ba_show_hover")

        if not day_bars.empty:
            fig = make_analysis_chart(
                day_bars, day_results,
                pd.Timestamp(selected_date).strftime("%B %d, %Y"),
                show_bar_nums=show_bar_nums,
                excl_first_n=excl_first_n,
                excl_last_min=excl_last_min,
                contract=contract,
                show_hover=show_hover,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No bar data for this date.")

    # ── Signal table for selected day ─────────────────────────────────────────
    with st.expander(f"Signal Table — {pd.Timestamp(selected_date).strftime('%b %d, %Y')}"
                     f"  ({len(day_results)} signals)", expanded=False):
        _show_signal_table(day_results.reset_index(drop=True), key_suffix="_day")

    # ── Full-range signal table ───────────────────────────────────────────────
    with st.expander(f"All Signals — full range  ({len(results)} signals)", expanded=False):
        _show_signal_table(results.reset_index(drop=True), key_suffix="_all")

    # ── Bar data mismatch analysis ────────────────────────────────────────────
    if nt_bars is not None and not nt_bars.empty:
        st.markdown("---")
        with st.expander("🔍 Bar Data Mismatch Analysis", expanded=False):
            _show_mismatch_analysis(results, bars, nt_bars)
