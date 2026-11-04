"""Reconstruct skew-matched condor shadow pairs for a PAST day (2026-11-03).

skew_condor_shadow.py was never scheduled/running before today, so there is
no real IB modelGreeks.delta recorded for any prior day -- the chain tape
(data/options_tape/chain_<date>.parquet) only has ts_et/spot/expiry/strike/
right/bid/ask, no greeks. This script approximates the same "match the
call's delta to the put's delta" idea OFFLINE using Black-Scholes delta
solved from the archived bid/ask mid (same bsm_price/implied_vol pattern as
td_gex_calibrate.py), rate=0, T = seconds-to-16:00 ET close / seconds-per-
year. That is a DIFFERENT delta source than the live script's IB tick
(2026-11-01 decision was explicitly "IB's own tick, NOT a model") -- flagged
here, not hidden: this is the only way to get a delta for a day nobody
recorded one, and is strictly a backward-looking estimate for comparison,
never used for any live decision.

Writes the same shadow_<date>.json schema skew_condor_shadow.py writes, with
pairs tagged "reconstructed": true, "live": false, "method": "bsm_offline"
so the dashboard tab (skew_shadow_html() in options_dashboard.py) renders it
identically to a live/shadow day.

Usage:
  .venv/Scripts/python.exe scripts/skew_condor_reconstruct.py 2026-11-02
"""
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
OUTDIR = SIM / "skew_condor_shadow"
OUTDIR.mkdir(parents=True, exist_ok=True)
TAPE = ROOT / "data" / "options_tape"
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
WING = 25
STRIKE_STEP = 5
SEARCH_RANGE = 60
CLOSE_HHMM_ET = (16, 0)   # SPXW 0DTE cash settlement
EXIT_HHMM_CT = (14, 45)   # matches skew_condor_shadow.py's TIME_STOP


def bsm_price(S, K, T, sigma, right):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if right == "C" else (K - S))
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right == "C":
        return S * norm.cdf(d1) - K * norm.cdf(d2)
    return K * norm.cdf(-d2) - S * norm.cdf(-d1)


def bsm_delta(S, K, T, sigma, right):
    if T <= 0 or sigma <= 0:
        return 1.0 if (right == "C") == (S > K) else 0.0
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if right == "C" else norm.cdf(d1) - 1.0


def implied_vol(price, S, K, T, right):
    if price is None or price <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (S - K) if right == "C" else (K - S))
    if price <= intrinsic + 1e-6:
        return None
    try:
        return brentq(lambda s: bsm_price(S, K, T, s, right) - price, 1e-3, 5.0, maxiter=100)
    except (ValueError, RuntimeError):
        return None


def ct_to_et(date_str, hhmmss):
    h, m, *s = hhmmss.split(":")
    sec = int(float(s[0])) if s else 0
    d = datetime.strptime(date_str, "%Y-%m-%d")
    dt_ct = d.replace(hour=int(h), minute=int(m), second=sec, tzinfo=CT)
    return dt_ct.astimezone(ET)


def load_chain(date_compact):
    f = TAPE / f"chain_{date_compact}.parquet"
    if f.exists():
        df = pd.read_parquet(f)
    else:
        f_csv = SIM / f"chain_{date_compact}.csv"
        if not f_csv.exists():
            raise FileNotFoundError(
                f"no archived chain for {date_compact}: {f} or {f_csv}")
        df = pd.read_csv(f_csv)  # current recorder writes here, options_tape/ is stale
    df["ts_et"] = pd.to_datetime(df["ts_et"]).dt.tz_localize(ET)
    return df


def nearest_snapshot(df, target_et):
    ts = df["ts_et"].drop_duplicates()
    idx = (ts - target_et).abs().idxmin()
    snap_t = df.loc[idx, "ts_et"]
    return df[df["ts_et"] == snap_t], snap_t


def mid_quote(snap, strike, right):
    row = snap[(snap["strike"] == strike) & (snap["right"] == right)]
    if row.empty:
        return None, None, None
    bid, ask = float(row.iloc[0]["bid"]), float(row.iloc[0]["ask"])
    if math.isnan(bid) or math.isnan(ask) or bid <= 0 or ask <= 0 or ask < bid:
        return None, None, None
    return (bid + ask) / 2, bid, ask


def worthless_price(snap, strike, right, side):
    """Same lookup as mid_quote but for EXIT pricing only: a strike with no
    row / NaN / zero quote this late in the day (0DTE, far OTM) means no one
    is bidding on it -- economically that leg expires worthless, not
    'unknown'. Returns 0.0 in that case instead of None so the exit calc can
    still complete (matches reality: you don't pay anything to close a
    worthless short, you receive nothing selling a worthless long)."""
    row = snap[(snap["strike"] == strike) & (snap["right"] == right)]
    if row.empty:
        return 0.0
    v = float(row.iloc[0][side])
    return 0.0 if (math.isnan(v) or v <= 0) else v


def t_years(snap_et, close_et):
    secs = max((close_et - snap_et).total_seconds(), 1.0)
    return secs / (365.0 * 86400.0)


def delta_at(snap, spot, strike, right, T):
    mid, bid, ask = mid_quote(snap, strike, right)
    if mid is None:
        return None, None, None, None
    iv = implied_vol(mid, spot, strike, T, right)
    if iv is None:
        return None, None, bid, ask
    return bsm_delta(spot, strike, T, iv, right), iv, bid, ask


def find_skew_matched_strike(snap, spot, T, target_abs_delta, center_strike):
    """Only consider strikes where the WING (k+WING) also has a live quote in
    this snapshot -- the chain recorder's strike band is narrower right after
    the open than later in the day (2026-11-02 09:31 ET: max recorded call
    strike 7715, vs 7745 by 10:06 ET), so a delta-best strike with no
    tradeable wing partner is not a real candidate."""
    best = None
    for k in range(int(center_strike) - SEARCH_RANGE, int(center_strike) + SEARCH_RANGE + 1, STRIKE_STEP):
        delta, iv, bid, ask = delta_at(snap, spot, k, "C", T)
        if delta is None:
            continue
        if mid_quote(snap, k + WING, "C")[0] is None:
            continue
        diff = abs(abs(delta) - target_abs_delta)
        if best is None or diff < best[0]:
            best = (diff, k, delta, bid, ask)
    if best is None:
        return None, None, None, None
    _, k, delta, bid, ask = best
    return k, delta, bid, ask


PAIRS = {"eod": ("eodic_p", "eodic_c"), "open": ("openic_p", "openic_c")}


def reconstruct(date_str):
    date_compact = date_str.replace("-", "")
    plan_path = SIM / f"gameplan_{date_compact}.json"
    if not plan_path.exists():
        print(f"no gameplan for {date_str}")
        return
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    df = load_chain(date_compact)
    close_et = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=CLOSE_HHMM_ET[0], minute=CLOSE_HHMM_ET[1], tzinfo=ET)
    exit_et = ct_to_et(date_str, f"{EXIT_HHMM_CT[0]:02d}:{EXIT_HHMM_CT[1]:02d}:00")

    book_path = OUTDIR / f"shadow_{date_str}.json"
    book = {"date": date_str, "pairs": {}}

    for anchor, (put_setup, call_setup) in PAIRS.items():
        put_trig = next((t for t in plan["triggers"] if t.get("setup") == put_setup), None)
        call_trig = next((t for t in plan["triggers"] if t.get("setup") == call_setup), None)
        if not put_trig or not put_trig.get("fired") or not put_trig.get("filled_legs"):
            print(f"  {anchor}: real put never fired on {date_str}, skipping")
            continue
        real_call_short = (call_trig or {}).get("structure", {}).get("short")
        if real_call_short is None:
            print(f"  {anchor}: no real call strike on {date_str}, skipping")
            continue
        put_short = next(l["strike"] for l in put_trig["filled_legs"] if l["side"] == "sell")

        fire_et = ct_to_et(date_str, put_trig["fill"]["at"])
        snap_entry, snap_entry_t = nearest_snapshot(df, fire_et)
        spot_entry = float(snap_entry.iloc[0]["spot"])
        T_entry = t_years(snap_entry_t, close_et)

        put_delta, put_iv, put_bid, put_ask = delta_at(snap_entry, spot_entry, put_short, "P", T_entry)
        if put_delta is None:
            print(f"  {anchor}: no reconstructable put delta at {snap_entry_t}, skipping")
            continue
        target = abs(put_delta)
        matched_k, matched_delta, call_bid, call_ask = find_skew_matched_strike(
            snap_entry, spot_entry, T_entry, target, real_call_short)
        if matched_k is None:
            print(f"  {anchor}: no call-delta match found, skipping")
            continue
        long_bid, long_ask = mid_quote(snap_entry, matched_k + WING, "C")[1:]
        if call_bid is None or long_ask is None:
            print(f"  {anchor}: missing leg quote at entry snapshot, skipping")
            continue
        credit = round(call_bid - long_ask, 2)   # sell short @bid, buy long @ask -- same convention as live script

        # exit: nearest snapshot to 14:45 CT, close the same vertical (buy back short @ask, sell long @bid).
        # Missing/zero quote this late = treated as worthless (0.0), not unknown -- see worthless_price().
        snap_exit, snap_exit_t = nearest_snapshot(df, exit_et)
        short_exit_ask = worthless_price(snap_exit, matched_k, "C", "ask")
        long_exit_bid = worthless_price(snap_exit, matched_k + WING, "C", "bid")
        debit = round(short_exit_ask - long_exit_bid, 2)

        rec = {
            "entered": True, "entered_at": snap_entry_t.astimezone(CT).strftime("%H:%M:%S"),
            "live": False, "reconstructed": True, "method": "bsm_offline",
            "put_short": put_short, "put_delta": round(put_delta, 4),
            "real_call_short": real_call_short,
            "real_call_credit": (call_trig or {}).get("fill", {}).get("net"),
            "skew_call_short": matched_k, "skew_call_delta": round(matched_delta, 4),
            "skew_call_long": matched_k + WING, "skew_call_credit": credit,
            "exited": debit is not None, "exit_debit_est": debit,
        }
        if debit is not None:
            rec["pnl_shadow"] = round((credit - debit) * 100, 2)
        book["pairs"][anchor] = rec
        print(f"  [reconstructed] {anchor}: put {put_short}P delta {put_delta:.3f} -> "
              f"call {matched_k}C delta {matched_delta:.3f} (real call was {real_call_short}C) | "
              f"credit {credit} debit {debit} P&L {rec.get('pnl_shadow')}")

    book_path.write_text(json.dumps(book, indent=2), encoding="utf-8")
    print(f"wrote {book_path}")


if __name__ == "__main__":
    reconstruct(sys.argv[1])
