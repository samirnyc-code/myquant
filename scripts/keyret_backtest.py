"""Standalone backtest of the ZLO's OWN Key Retracement signal on ES.

Tests whether the LizardTrader Key Retracement signal (LongKeyRetSig /
ShortKeyRetSig) has a tradeable edge INDEPENDENT of our MC signals — run through
the real tick engine with realistic execution (entry_slip=1, exit_slip=0,
commission $4.36), not just forward bar returns.

Entry  : market, first tick after the signal bar close (entry_model='market').
Stop   : the doc's retracement-stop formula —
           Long  → min(Low[T], Low[T-1]) − offset
           Short → max(High[T], High[T-1]) + offset
         (offset applied by the engine via stop_offset, matching MC).
Target : R-multiple of |entry − stop|. Swept over 1.0 / 1.5 / 2.0.

Signals restricted to RTH grid (the engine's tick coverage). All in-sample —
this is a first viability test, not an OOS validation.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                    # noqa: E402
import simulation_engine as sim   # noqa: E402
from data_loader import TICK_SIZE  # noqa: E402

_ZLO  = _ROOT / "saved_signals" / "ba_zlo_overlay.parquet"
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT  = _ROOT / "docs" / "living" / "keyret_backtest.csv"

STOP_OFFSET = 1          # ticks beyond the swing, applied by engine
TARGETS = [1.0, 1.5, 2.0]
BASE = dict(entry_slip=1, exit_slip=0, stop_offset=STOP_OFFSET,
            tick_value=12.5, contracts=1, commission=4.36)


def log(m): print(f"[keyret] {m}", flush=True)


def build_keyret_signals(z: pd.DataFrame, bar_grid: set) -> pd.DataFrame:
    """Convert ZLO KeyRet flags into engine-ready signals with doc-defined stops."""
    z = z.sort_values("DateTime").reset_index(drop=True)
    z["DateTime"] = pd.to_datetime(z["DateTime"])
    # prior-bar extremes (Low[1] / High[1]) over the continuous series
    z["prevLow"] = z["Low"].shift(1)
    z["prevHigh"] = z["High"].shift(1)

    is_long = z["LongKeyRetSig"] == 1
    is_short = z["ShortKeyRetSig"] == 1
    sig = z[is_long | is_short].copy()

    # RTH grid only (engine tick coverage) + drop the first-bar NaN
    sig = sig[sig["DateTime"].isin(bar_grid)].dropna(subset=["prevLow", "prevHigh"])

    long_mask = sig["LongKeyRetSig"] == 1
    swing_low = np.minimum(sig["Low"], sig["prevLow"])
    swing_high = np.maximum(sig["High"], sig["prevHigh"])

    out = pd.DataFrame({
        "SignalNum": np.arange(1, len(sig) + 1),
        "SignalType": "KeyRet",
        "Direction": np.where(long_mask, "Long", "Short"),
        "DateTime": sig["DateTime"].values,
        "BarNum": 0,
        "SignalPrice": sig["Close"].values,                 # signal bar close
        "StopPrice": np.where(long_mask, swing_low, swing_high),
    })
    out["Date"] = pd.to_datetime(out["DateTime"]).dt.normalize()
    return out.reset_index(drop=True)


def run(signals: pd.DataFrame, ticks: dict, target_r: float) -> dict:
    res = sim.simulate_trades(signals, ticks, target_r=target_r, **BASE)
    s = sim.compute_summary(res, BASE["commission"])
    if not s:
        return {}
    return dict(
        target_r=target_r, trades=s["n_trades"],
        win_pct=round(s["win_pct"], 1), net=round(s["net_total"], 0),
        exp=round(s["exp_dollar"], 1), exp_r=round(s["exp_r"], 4),
        pf=round(s["pf"], 2), avg_win=round(s["avg_win"], 0),
        avg_loss=round(s["avg_loss"], 0), maxdd=round(s["max_dd"], 0),
        pnl_dd=round(s["pnl_dd"], 2) if not np.isnan(s.get("pnl_dd", np.nan)) else 0,
        sqn=round(s["sqn"], 2), sharpe=round(s["sharpe"], 2))


def main():
    log("Loading…")
    z = pd.read_parquet(_ZLO)
    bars = pd.read_parquet(_BARS)
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    bar_grid = set(bars["DateTime"])

    signals = build_keyret_signals(z, bar_grid)
    n_long = (signals["Direction"] == "Long").sum()
    n_short = (signals["Direction"] == "Short").sum()
    log(f"KeyRet signals: {len(signals)} ({n_long} long / {n_short} short), "
        f"{signals['Date'].nunique()} days")

    dates = sorted(signals["Date"].unique())
    log(f"Loading ticks for {len(dates)} days…")
    ticks = {}
    for d in dates:
        t = massive.load_continuous_ticks(pd.Timestamp(d).date())
        if not t.empty:
            ticks[d] = t
    log(f"  {len(ticks)} days of ticks loaded.")

    rows = []
    for tr in TARGETS:
        log(f"Simulating target {tr}R…")
        r = run(signals, ticks, tr)
        if r:
            rows.append(r)
            log(f"  -> {r['trades']}t win={r['win_pct']}% net=${r['net']:,.0f} "
                f"exp=${r['exp']} PF={r['pf']} maxDD=${r['maxdd']:,.0f} "
                f"PnL/DD={r['pnl_dd']} SQN={r['sqn']}")

    df = pd.DataFrame(rows)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_OUT, index=False)
    pd.set_option("display.width", 200)
    print("\n" + "=" * 90)
    print("ZLO KEY RETRACEMENT — STANDALONE BACKTEST (RTH, real ticks, costs)")
    print("=" * 90)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    log(f"\nSaved to {_OUT}")


if __name__ == "__main__":
    main()
