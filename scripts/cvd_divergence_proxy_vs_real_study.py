"""cvd_divergence_proxy_vs_real_study.py — compares CVDDivergenceOscillator.cs (bar-OHLC
proxy delta) against CVDRealDivergence.cs (real tick-classified delta) on identical
1000-tick ES 12-26 bars, replicating BOTH indicators' exact math in Python.

Built 2026-10-28: user called the proxy version "garbage," asked for a real-L1 version
(built as nt8/indicators/CVDRealDivergence.cs) "and then run a study that compares the 2."

DATA SOURCES (hard rule: tickdata.py is the ONLY tick source — see its own header):
  - Ticks:  tickdata.load_eth() per day, ETH session (matches the live chart being an
            overnight/ETH-hours chart per today's trade logs, e.g. 02:53/05:15 CT entries).
  - Real delta: data/bid_ask/bid_ask_vol_buckets.csv — the SAME 1-second (ask_vol,bid_vol)
            buckets CVDRealDivergence.cs itself reads for historical backfill. NOT
            reclassified from raw ticks (tickdata.py's trove has no bid/ask columns) —
            using the identical source the live indicator uses is the only way this
            study is actually faithful to what the indicator will show.

WINDOW: intersection of bucket coverage (2026-09-16 to 2026-10-28) and ETH tick trove
coverage (through 2026-10-27, auto-expands nightly, today not yet in) = 2026-09-16
through 2026-10-27, 29 trading days.

BAR CONSTRUCTION: 1000-tick bars (matches the live NT8 chart's own bar type, confirmed
from the indicator list screenshot earlier this session), reset per calendar day (NT8
tick bars reset at the session boundary). "Tick" = one print/row, NOT cumulative volume
— standard NT8/most-platform tick-bar semantics.

ALGORITHMS REPLICATED EXACTLY (same constants as both .cs files' SetDefaults defaults):
  Proxy delta: buying = Volume*(Close-Low)/range, selling = Volume*(High-Close)/range,
               delta = buying - selling   (CVDDivergenceOscillator.cs OnBarUpdate)
  Real delta:  sum of (ask_vol - bid_vol) over buckets whose timestamp falls in
               (prevBar.Time, thisBar.Time]   (CVDRealDivergence.cs AdvanceDeltaBuckets)
  Hist:        rolling SUM over CvdPeriod=21 bars, Periodic mode (both indicators' default)
  Divergence:  fractal pivot (DivergenceFractalPeriods=2 bars each side), filtered by
               Close vs EMA(Close, TrendEmaPeriod=50), MaxPivotGapBars=30 — bearish =
               higher price high + lower Hist high; bullish = lower price low + higher
               Hist low. (Both .cs files' OnBarUpdate divergence block.)

OUTPUT: dated CSV of every divergence event from both methods + a printed summary
(counts, agreement rate, forward-return quality) — this script IS the record, no
inline-only run.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tickdata  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUCKET_PATH = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
OUT_DIR = ROOT / "data" / "cvd_divergence_study"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TICKS_PER_BAR = 1000
CVD_PERIOD = 21
FRACTAL_N = 2
TREND_EMA_PERIOD = 50
MAX_PIVOT_GAP_BARS = 30
FWD_BARS = (5, 10, 20)   # forward-return horizons checked after each divergence pivot


def load_buckets() -> pd.DataFrame:
    df = pd.read_csv(BUCKET_PATH, usecols=["date", "timestamp", "ask_vol", "bid_vol"],
                      parse_dates=["timestamp"], dtype={"date": str},
                      on_bad_lines="skip")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def build_tick_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    """1000-tick OHLCV bars, reset per calendar day. ticks must be sorted by DateTime
    within each day (tickdata's troves already are, chronological per-day)."""
    ticks = ticks.copy()
    ticks["Day"] = ticks["DateTime"].dt.date
    bars = []
    for day, grp in ticks.groupby("Day", sort=True):
        grp = grp.reset_index(drop=True)
        n_bars = len(grp) // TICKS_PER_BAR
        for i in range(n_bars):
            chunk = grp.iloc[i * TICKS_PER_BAR:(i + 1) * TICKS_PER_BAR]
            bars.append({
                "Day": day,
                "Time": chunk["DateTime"].iloc[-1],
                "Open": chunk["Price"].iloc[0],
                "High": chunk["Price"].max(),
                "Low": chunk["Price"].min(),
                "Close": chunk["Price"].iloc[-1],
                "Volume": chunk["Volume"].sum(),
            })
    return pd.DataFrame(bars).reset_index(drop=True)


def proxy_delta(bars: pd.DataFrame) -> np.ndarray:
    rng = bars["High"] - bars["Low"]
    buying = np.where(rng > 0, bars["Volume"] * (bars["Close"] - bars["Low"]) / rng.replace(0, np.nan), 0.0)
    selling = np.where(rng > 0, bars["Volume"] * (bars["High"] - bars["Close"]) / rng.replace(0, np.nan), 0.0)
    return np.nan_to_num(np.array(buying) - np.array(selling))


def real_delta(bars: pd.DataFrame, buckets: pd.DataFrame) -> np.ndarray:
    """Walks the bucket cursor forward exactly like CVDRealDivergence.cs's
    AdvanceDeltaBuckets: for each bar, consume every unconsumed bucket with
    timestamp <= bar close time, summing (ask_vol-bid_vol) into that bar's delta."""
    out = np.zeros(len(bars))
    ts = buckets["timestamp"].values
    av = buckets["ask_vol"].values
    bv = buckets["bid_vol"].values
    cursor = 0
    n_buckets = len(buckets)
    bar_times = bars["Time"].values
    for i, bar_close in enumerate(bar_times):
        s = 0.0
        while cursor < n_buckets and ts[cursor] <= bar_close:
            s += av[cursor] - bv[cursor]
            cursor += 1
        out[i] = s
    return out


def rolling_sum_hist(delta: np.ndarray, period: int) -> np.ndarray:
    s = pd.Series(delta)
    return s.rolling(period, min_periods=1).sum().to_numpy()


def ema(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).ewm(span=period, adjust=False).mean().to_numpy()


def is_pivot_high(high: np.ndarray, idx: int, n: int) -> bool:
    c = high[idx]
    for k in range(1, n + 1):
        if idx - k < 0 or high[idx - k] > c:
            return False
    for k in range(1, n + 1):
        if idx + k >= len(high) or high[idx + k] >= c:
            return False
    return True


def is_pivot_low(low: np.ndarray, idx: int, n: int) -> bool:
    c = low[idx]
    for k in range(1, n + 1):
        if idx - k < 0 or low[idx - k] < c:
            return False
    for k in range(1, n + 1):
        if idx + k >= len(low) or low[idx + k] <= c:
            return False
    return True


def find_divergences(bars: pd.DataFrame, hist: np.ndarray, label: str) -> pd.DataFrame:
    high = bars["High"].to_numpy()
    low = bars["Low"].to_numpy()
    close = bars["Close"].to_numpy()
    close_ema = ema(close, TREND_EMA_PERIOD)
    n = FRACTAL_N

    events = []
    h_last_bar = h_prev_bar = -1
    h_last_price = h_prev_price = h_last_hist = h_prev_hist = np.nan
    l_last_bar = l_prev_bar = -1
    l_last_price = l_prev_price = l_last_hist = l_prev_hist = np.nan

    for cur in range(2 * n, len(bars)):
        pivot_bar = cur - n
        if is_pivot_high(high, pivot_bar, n) and close[pivot_bar] > close_ema[cur]:
            price = high[pivot_bar]; hv = hist[pivot_bar]
            h_prev_bar, h_prev_price, h_prev_hist = h_last_bar, h_last_price, h_last_hist
            h_last_bar, h_last_price, h_last_hist = pivot_bar, price, hv
            if (h_prev_bar >= 0 and (h_last_bar - h_prev_bar) < MAX_PIVOT_GAP_BARS
                    and h_last_hist > 0 and h_prev_hist > 0
                    and h_last_price > h_prev_price and h_last_hist < h_prev_hist):
                events.append({"method": label, "bearish": True, "barA": h_prev_bar, "barB": h_last_bar,
                                "priceA": h_prev_price, "priceB": h_last_price,
                                "histA": h_prev_hist, "histB": h_last_hist})
        if is_pivot_low(low, pivot_bar, n) and close[pivot_bar] < close_ema[cur]:
            price = low[pivot_bar]; hv = hist[pivot_bar]
            l_prev_bar, l_prev_price, l_prev_hist = l_last_bar, l_last_price, l_last_hist
            l_last_bar, l_last_price, l_last_hist = pivot_bar, price, hv
            if (l_prev_bar >= 0 and (l_last_bar - l_prev_bar) < MAX_PIVOT_GAP_BARS
                    and l_last_hist < 0 and l_prev_hist < 0
                    and l_last_price < l_prev_price and l_last_hist > l_prev_hist):
                events.append({"method": label, "bearish": False, "barA": l_prev_bar, "barB": l_last_bar,
                                "priceA": l_prev_price, "priceB": l_last_price,
                                "histA": l_prev_hist, "histB": l_last_hist})
    return pd.DataFrame(events)


def add_forward_returns(events: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    close = bars["Close"].to_numpy()
    for h in FWD_BARS:
        col = []
        for _, row in events.iterrows():
            b = int(row["barB"])
            if b + h < len(close):
                ret = close[b + h] - close[b]
                col.append(-ret if row["bearish"] else ret)   # signed in the direction the divergence implies (reversal)
            else:
                col.append(np.nan)
        events[f"fwd_ret_{h}b_favorable"] = col
    return events


def match_agreement(real_ev: pd.DataFrame, proxy_ev: pd.DataFrame, bar_tol: int = 3) -> int:
    """Counts real-method events that have a same-direction proxy event within
    bar_tol bars of the same pivot (barB) — a simple overlap/agreement measure."""
    if real_ev.empty or proxy_ev.empty:
        return 0
    matched = 0
    proxy_b = proxy_ev[["barB", "bearish"]].to_numpy()
    for _, r in real_ev.iterrows():
        hits = np.where((proxy_b[:, 1] == r["bearish"]) & (np.abs(proxy_b[:, 0] - r["barB"]) <= bar_tol))[0]
        if len(hits) > 0:
            matched += 1
    return matched


def main():
    days = [d for d in tickdata.available("eth") if "2026-09-16" <= d <= "2026-10-27"]
    print(f"Loading {len(days)} ETH days ({days[0]} to {days[-1]})...")
    ticks = tickdata.load_range(days[0], days[-1], eth=True)
    print(f"  {len(ticks):,} ticks loaded")

    bars = build_tick_bars(ticks)
    print(f"Built {len(bars):,} x {TICKS_PER_BAR}-tick bars")

    buckets = load_buckets()
    print(f"Loaded {len(buckets):,} bid/ask buckets ({buckets['timestamp'].min()} to {buckets['timestamp'].max()})")

    bars["proxy_delta"] = proxy_delta(bars)
    bars["real_delta"] = real_delta(bars, buckets)
    bars["proxy_hist"] = rolling_sum_hist(bars["proxy_delta"].to_numpy(), CVD_PERIOD)
    bars["real_hist"] = rolling_sum_hist(bars["real_delta"].to_numpy(), CVD_PERIOD)

    proxy_ev = find_divergences(bars, bars["proxy_hist"].to_numpy(), "proxy")
    real_ev = find_divergences(bars, bars["real_hist"].to_numpy(), "real")

    proxy_ev = add_forward_returns(proxy_ev, bars) if not proxy_ev.empty else proxy_ev
    real_ev = add_forward_returns(real_ev, bars) if not real_ev.empty else real_ev

    all_ev = pd.concat([proxy_ev, real_ev], ignore_index=True)
    for col in ["barA", "barB"]:
        if not all_ev.empty:
            all_ev[col + "_time"] = all_ev[col].map(lambda i: bars["Time"].iloc[int(i)] if pd.notna(i) else pd.NaT)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"cvd_div_proxy_vs_real_{stamp}.csv"
    all_ev.to_csv(out_path, index=False)

    agree = match_agreement(real_ev, proxy_ev, bar_tol=3)

    print("\n" + "=" * 70)
    print(f"Period: {days[0]} to {days[-1]} ({len(days)} days), {len(bars):,} bars @ {TICKS_PER_BAR}-tick")
    print(f"PROXY divergences: {len(proxy_ev)}  (bearish {int((proxy_ev['bearish']).sum()) if not proxy_ev.empty else 0}"
          f" / bullish {int((~proxy_ev['bearish']).sum()) if not proxy_ev.empty else 0})")
    print(f"REAL   divergences: {len(real_ev)}  (bearish {int((real_ev['bearish']).sum()) if not real_ev.empty else 0}"
          f" / bullish {int((~real_ev['bearish']).sum()) if not real_ev.empty else 0})")
    print(f"REAL events with a same-direction PROXY event within 3 bars: {agree} / {len(real_ev)}"
          f" ({100*agree/len(real_ev):.1f}%)" if len(real_ev) else "n/a (no real events)")
    print()
    print(f"{'method':<8}{'n':>6}" + "".join(f"{'fwd'+str(h)+'b_avg':>14}" for h in FWD_BARS))
    for label, ev in (("proxy", proxy_ev), ("real", real_ev)):
        if ev.empty:
            print(f"{label:<8}{0:>6}")
            continue
        row = f"{label:<8}{len(ev):>6}"
        for h in FWD_BARS:
            row += f"{ev[f'fwd_ret_{h}b_favorable'].mean():>14.3f}"
        print(row)
    print("=" * 70)
    print(f"\nFull event list saved: {out_path}")


if __name__ == "__main__":
    main()
