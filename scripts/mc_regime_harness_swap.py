"""mc_regime_harness_swap.py — drop the MC/CC trigger into the FULL 2E exec.

The filters-only pass (mc_regime_filter_study.py) ruled out the 2E engine's
ENTRY-side gates on the MC book. The only untested lever is the 2E EXIT side, so
this swaps the frozen MC exec (structural-R stop, 3R target, BE ratchet) for the
2E harness exec and keeps the MC/CC signal as the only MC-specific piece:

  2E EXEC:  * vol stop = 0.30 x ADR10 from entry, snapped to tick, floor 8t,
              NEVER moved (no ratchet).
            * NO target — hold to session close (EOD flat) or the stop.
  2E GATES (optional cells): regime with-trend + |RTH gap|<=0.54%.

Question (user framing): does the CC breakout trigger, inside the identical 2E
harness, beat/complement the 2E second-entry trigger (its own book: PF 1.44,
~$66-94k/5yr, green every year)?

Vol stop is anchored at SignalPrice (fill is unknown pre-sim; small slip drift).
ADR10 = 10-session mean of RTH daily range (high.max-low.min), shifted 1 (causal).
Trades scored once by the shared engine, then subset per cell. All causal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive  # noqa: E402
from bar_analysis import parse_signals  # noqa: E402
from simulation_engine import simulate_trades, INSTRUMENTS  # noqa: E402
from stack_filter import compute_stack_columns  # noqa: E402

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_REGIME = _ROOT / "data" / "regime" / "mc_signal_day_regime.parquet"
_COMM = 4.36
_GAP_PCT = 0.54
_ADR_MULT = 0.30
_STOP_FLOOR_TICKS = 8
_TICK = 0.25
_STAMP = "20260725"


def _log(m):
    sys.stdout.buffer.write((str(m) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def _boot_ci(x, iters=5000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    means = np.array([rng.choice(x, n, replace=True).mean() for _ in range(iters)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _score(filled, label):
    if filled.empty:
        _log(f"{label:30s} n=0")
        return dict(cell=label, n=0)
    net_r = (filled["NetPnL"] / filled["RiskDollar"]).to_numpy()
    net = float(filled["NetPnL"].sum())
    per = net / len(filled)
    wr = float((filled["NetPnL"] > 0).mean()) * 100
    gains = filled.loc[filled["NetPnL"] > 0, "NetPnL"].sum()
    losses = filled.loc[filled["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(gains / abs(losses)) if losses else float("inf")
    lo, hi = _boot_ci(net_r)
    yr = pd.to_datetime(filled["Date"]).dt.year
    by = filled.groupby(yr)["NetPnL"].sum()
    pos = int((by > 0).sum())
    _log(f"{label:30s} n={len(filled):5d}  netR={net_r.mean():+.3f} "
         f"[{lo:+.3f},{hi:+.3f}]  WR={wr:4.1f}%  PF={pf:4.2f}  "
         f"${net:+9,.0f}  ${per:+6.0f}/tr  yrs+{pos}/{len(by)}")
    return dict(cell=label, n=int(len(filled)), netR=float(net_r.mean()),
                ci_lo=lo, ci_hi=hi, wr=wr, pf=pf, net=net, per_tr=per,
                yrs_pos=pos, yrs=int(len(by)))


def _adr10(bars):
    day = bars["DateTime"].dt.date
    rng = bars.groupby(day).apply(lambda g: g["High"].max() - g["Low"].min())
    adr = rng.rolling(10, min_periods=5).mean().shift(1)
    return adr  # index = date


def main():
    sig = parse_signals(_SIG_TXT.read_text()).reset_index(drop=True)
    sig["MYID"] = np.arange(len(sig))
    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).astype("datetime64[ns]")
    sig["_d"] = pd.to_datetime(sig["Date"]).dt.date
    _log(f"{len(sig)} MC signals")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # ---- gap ----
    by = {d: g.sort_values("DateTime") for d, g in bars.groupby(bars["DateTime"].dt.date)}
    dts = sorted(by)
    gap_map, prev_close = {}, None
    for d in dts:
        op = float(by[d]["Open"].iloc[0])
        gap_map[d] = np.nan if prev_close is None else (op - prev_close) / prev_close * 100.0
        prev_close = float(by[d]["Close"].iloc[-1])
    sig["gap_pct"] = sig["_d"].map(gap_map)

    # ---- ADR10 vol stop (override the signal stop) ----
    adr = _adr10(bars)
    sig["adr10"] = sig["_d"].map(adr.to_dict())
    vol = (_ADR_MULT * sig["adr10"] / _TICK).round() * _TICK
    vol = vol.clip(lower=_STOP_FLOOR_TICKS * _TICK)
    is_long = sig["Direction"].astype(str).str.upper().str.startswith("L")
    sig["volstop_pts"] = vol
    sig["StopPrice"] = np.where(is_long, sig["SignalPrice"] - vol,
                                sig["SignalPrice"] + vol)
    n0 = len(sig)
    sig = sig[sig["volstop_pts"].notna()].reset_index(drop=True)
    _log(f"vol stop: {_ADR_MULT}xADR10 floor {_STOP_FLOOR_TICKS}t  "
         f"median={sig['volstop_pts'].median():.2f}pt  "
         f"(ADR10 median {sig['adr10'].median():.1f}pt); "
         f"dropped {n0 - len(sig)} early no-ADR signals")

    # ---- stack pass ----
    st = compute_stack_columns(sig, bars)
    sig["stack_pass"] = st["stack_pass"].to_numpy()

    # ---- regime as of signal close ----
    reg = pd.read_parquet(_REGIME)
    reg["bar_close"] = pd.to_datetime(reg["bar_close"]).astype("datetime64[ns]")
    reg["_d"] = pd.to_datetime(reg["Date"]).dt.date
    parts = []
    for d, sg in sig.sort_values("DateTime").groupby("_d"):
        rg = reg[reg["_d"] == d].sort_values("bar_close")
        if rg.empty:
            sg = sg.assign(regime="neutral")
        else:
            sg = pd.merge_asof(sg.sort_values("DateTime"), rg[["bar_close", "regime"]],
                               left_on="DateTime", right_on="bar_close",
                               direction="backward")
            sg["regime"] = sg["regime"].fillna("neutral")
        parts.append(sg)
    sig = pd.concat(parts, ignore_index=True).sort_values("MYID").reset_index(drop=True)

    # ---- sim ONCE: 2E exec (no target => hold to close, no ratchet) ----
    dates = sorted(sig["_d"].unique())
    _log(f"scoring {len(sig)} signals through 2E exec (vol stop, hold-to-close)…")
    ticks_by_date = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    raw = simulate_trades(
        signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
        target_r=1000.0, ratchet_r=0.0,           # no target, never moved -> hold-to-close/stop
        entry_slip=1.0, exit_slip=1.0, stop_offset=1,
        tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
        commission=_COMM, pb_round="nearest")
    f = raw[raw["Filled"] == True].copy()  # noqa: E712
    meta = sig.set_index("MYID")[["Direction", "gap_pct", "stack_pass", "regime"]]
    for c in ["gap_pct", "stack_pass", "regime"]:
        f[c] = f["MYID"].map(meta[c])
    # confirm hold-to-close is dominant exit
    _log(f"filled {len(f)}/{len(raw)}  exit-reason mix: "
         f"{f['ExitReason'].value_counts(normalize=True).round(2).to_dict()}\n")

    il = f["Direction"].astype(str).str.upper().str.startswith("L")
    wt = (il & (f["regime"] == "bull")) | (~il & (f["regime"] == "bear"))
    gap_ok = ~(f["gap_pct"].abs() > _GAP_PCT)
    stack = f["stack_pass"].astype(bool)

    _log("=" * 100)
    _log("2E-EXEC ON THE MC/CC TRIGGER  (0.30xADR vol stop, hold-to-close, $4.36 RT, 1 ES)")
    _log("2E second-entry book for reference: PF 1.44, ~$66-94k/5yr, green every year")
    _log("=" * 100)
    res = []
    res.append(_score(f, "1 all MC + 2E exec"))
    res.append(_score(f[stack], "2 + stackv2 filters"))
    res.append(_score(f[wt], "3 + regime (with-trend)"))
    res.append(_score(f[wt & gap_ok], "4 + regime + gap  [full 2E gating]"))
    res.append(_score(f[stack & wt & gap_ok], "5 + stackv2 + regime + gap"))
    _log("\n--- direction split of the full-2E-gating cell (4) ---")
    _score(f[wt & gap_ok & il], "  4 Longs(bull)")
    _score(f[wt & gap_ok & ~il], "  4 Shorts(bear)")

    out = pd.DataFrame([r for r in res if r])
    scb = _ROOT / "data" / "regime" / f"mc_regime_harness_swap_scoreboard_{_STAMP}.csv"
    out.to_csv(scb, index=False)
    f.to_parquet(_ROOT / "data" / "regime" / f"mc_regime_harness_swap_trades_{_STAMP}.parquet")
    _log(f"\nWROTE {scb.name} + trades parquet")


if __name__ == "__main__":
    main()
