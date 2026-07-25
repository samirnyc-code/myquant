"""mc_regime_filter_study.py — do the 2E regime engine's FILTERS help the MC book?

Filters-only ablation (user call 2026-07-25): keep the frozen MC "Stack v2" exec
(structural-R stop, 3R target, ratchet-to-BE at +1R, EOD flat) and bolt on the
second-entry engine's context filters as pure skip rules:

  * REGIME GATE  — the fast-flip tick-driven phase machine (regime_label_engine):
                   keep a Long only in BULL, a Short only in BEAR (skip NEUTRAL
                   and counter-trend). Regime is read as of the signal bar close
                   (causal). Cache: data/regime/mc_signal_day_regime.parquet.
  * GAP GATE     — skip the whole day if |RTH gap| > 0.54% (the 2E constant).

Trades are scored ONCE by the shared sim engine (same call as the app / the
baseline-of-record) and then subset per cell — sims score independently, so
post-sim subsetting == pre-sim filtering. Everything below is causal.

Cells (all Long+Short, frozen exec):
  A all_mc                 no filter (baseline of record sanity)
  B stackv2                F1 counter-IB + F2 prior-trend + F3 late  (the frozen book)
  C stackv2 + gap
  D stackv2 + regime
  E stackv2 + gap + regime
  F (F2+F3) + regime       regime REPLACES the crude F1 counter-IB gate
  G (F2+F3) + regime + gap
  H all_mc + regime        raw directional regime lift, no stack

Saves the per-cell scoreboard + the labeled filled trades (dated).
"""
from __future__ import annotations

import sys
from datetime import date
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
_GAP_PCT = 0.54  # 2E gap-skip constant
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
        _log(f"{label:26s} n=0")
        return dict(cell=label, n=0)
    net_r = (filled["NetPnL"] / filled["RiskDollar"]).to_numpy()
    net = float(filled["NetPnL"].sum())
    wr = float((filled["NetPnL"] > 0).mean()) * 100
    gains = filled.loc[filled["NetPnL"] > 0, "NetPnL"].sum()
    losses = filled.loc[filled["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(gains / abs(losses)) if losses else float("inf")
    lo, hi = _boot_ci(net_r)
    yr = pd.to_datetime(filled["Date"]).dt.year
    by = filled.groupby(yr)["NetPnL"].sum()
    pos = int((by > 0).sum())
    _log(f"{label:26s} n={len(filled):5d}  netR={net_r.mean():+.3f} "
         f"[{lo:+.3f},{hi:+.3f}]  WR={wr:4.1f}%  PF={pf:4.2f}  "
         f"${net:+9,.0f}  yrs+{pos}/{len(by)}")
    return dict(cell=label, n=int(len(filled)), netR=float(net_r.mean()),
                ci_lo=lo, ci_hi=hi, wr=wr, pf=pf, net=net,
                yrs_pos=pos, yrs=int(len(by)))


def _day_gap(bars):
    """Per-date RTH gap % = (first-bar Open - prior-day last-bar Close)/prior close."""
    by = {d: g.sort_values("DateTime") for d, g in bars.groupby(bars["DateTime"].dt.date)}
    dates = sorted(by)
    rows = []
    prev_close = None
    for d in dates:
        g = by[d]
        op = float(g["Open"].iloc[0])
        gap = np.nan if prev_close is None else (op - prev_close) / prev_close * 100.0
        rows.append((d, gap))
        prev_close = float(g["Close"].iloc[-1])
    return pd.DataFrame(rows, columns=["_d", "gap_pct"])


def main():
    sig = parse_signals(_SIG_TXT.read_text()).reset_index(drop=True)
    sig["MYID"] = np.arange(len(sig))
    _log(f"{len(sig)} MC signals ({sig['Date'].min()} -> {sig['Date'].max()})")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # ---- gap per day ----
    gap = _day_gap(bars)
    sig["_d"] = pd.to_datetime(sig["Date"]).dt.date
    sig = sig.merge(gap, on="_d", how="left")

    # ---- stack v2 pass/skip ----
    st = compute_stack_columns(sig, bars)
    sig["stack_pass"] = st["stack_pass"].to_numpy()
    sig["stack_skip"] = st["stack_skip"].to_numpy()

    # ---- regime as of the signal bar close (causal, from cache) ----
    if not _REGIME.exists():
        _log(f"MISSING {_REGIME} — run scripts/mc_regime_label_cache.py first.")
        sys.exit(1)
    reg = pd.read_parquet(_REGIME)
    reg["bar_close"] = pd.to_datetime(reg["bar_close"]).astype("datetime64[ns]")
    reg["_d"] = pd.to_datetime(reg["Date"]).dt.date
    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).astype("datetime64[ns]")
    sig_sorted = sig.sort_values("DateTime")
    parts = []
    for d, sg in sig_sorted.groupby("_d"):
        rg = reg[reg["_d"] == d].sort_values("bar_close")
        if rg.empty:
            sg = sg.assign(regime="__none__")
        else:
            sg = pd.merge_asof(sg.sort_values("DateTime"), rg[["bar_close", "regime"]],
                               left_on="DateTime", right_on="bar_close",
                               direction="backward")
            sg["regime"] = sg["regime"].fillna("neutral")
        parts.append(sg)
    sig = pd.concat(parts, ignore_index=True).sort_values("MYID").reset_index(drop=True)

    reg_cov = (sig["regime"] != "__none__").mean() * 100
    _log(f"regime coverage: {reg_cov:.1f}% of signals  |  "
         f"regime mix: {sig['regime'].value_counts(normalize=True).round(3).to_dict()}")
    _log(f"gap-skip days: |gap|>{_GAP_PCT}% -> "
         f"{(sig['gap_pct'].abs() > _GAP_PCT).mean() * 100:.1f}% of signals\n")

    # ---- sim ONCE, frozen exec ----
    dates = sorted(sig["_d"].unique())
    _log(f"loading ticks for {len(dates)} days & scoring (frozen exec 3R/BE@1R/EOD)…")
    ticks_by_date = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    raw = simulate_trades(
        signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
        target_r=3.0, ratchet_r=1.0, ratchet_dest="BE",
        entry_slip=1.0, exit_slip=1.0, stop_offset=1,
        tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
        commission=_COMM, pb_round="nearest")
    f = raw[raw["Filled"] == True].copy()  # noqa: E712
    # carry the per-signal filter fields onto the filled frame
    meta = sig.set_index("MYID")[["Direction", "gap_pct", "stack_pass",
                                  "stack_skip", "regime"]]
    for c in ["gap_pct", "stack_pass", "stack_skip", "regime"]:
        f[c] = f["MYID"].map(meta[c])
    _log(f"filled {len(f)}/{len(raw)} signals\n")

    is_long = f["Direction"].astype(str).str.upper().str.startswith("L")
    with_trend = ((is_long & (f["regime"] == "bull")) |
                  (~is_long & (f["regime"] == "bear")))
    # looser: keep unless the signal is COUNTER to an established trend
    not_counter = ~((is_long & (f["regime"] == "bear")) |
                    (~is_long & (f["regime"] == "bull")))
    gap_ok = ~(f["gap_pct"].abs() > _GAP_PCT)
    stack = f["stack_pass"].astype(bool)
    # (F2+F3) only = stack pass OR the only reason it failed was ib_counter
    f2f3 = stack | (f["stack_skip"] == "ib_counter")

    _log("=" * 92)
    _log("CELL SCOREBOARD  (frozen MC exec: 3R target, ratchet BE @+1R, EOD flat, "
         "$4.36 RT, 1 ES)")
    _log("=" * 92)
    results = []
    results.append(_score(f, "A all_mc"))
    results.append(_score(f[stack], "B stackv2 (frozen book)"))
    results.append(_score(f[stack & gap_ok], "C stackv2+gap"))
    results.append(_score(f[stack & with_trend], "D stackv2+regime"))
    results.append(_score(f[stack & gap_ok & with_trend], "E stackv2+gap+regime"))
    results.append(_score(f[f2f3 & with_trend], "F (F2+F3)+regime [F1 swap]"))
    results.append(_score(f[f2f3 & with_trend & gap_ok], "G (F2+F3)+regime+gap"))
    results.append(_score(f[with_trend], "H all_mc+regime(wt)"))
    _log("  -- looser 'not-counter-trend' gate (keeps NEUTRAL) --")
    results.append(_score(f[stack & not_counter], "I stackv2+notcounter"))
    results.append(_score(f[f2f3 & not_counter], "J (F2+F3)+notcounter [F1 swap]"))
    results.append(_score(f[stack & not_counter & gap_ok], "K stackv2+notcounter+gap"))

    _log("\n--- direction split (baseline B vs regime-swap F) ---")
    _score(f[stack & is_long], "  B Longs")
    _score(f[stack & ~is_long], "  B Shorts")
    _score(f[f2f3 & with_trend & is_long], "  F Longs(bull)")
    _score(f[f2f3 & with_trend & ~is_long], "  F Shorts(bear)")

    out = pd.DataFrame([r for r in results if r])
    scb = _ROOT / "data" / "regime" / f"mc_regime_filter_scoreboard_{_STAMP}.csv"
    out.to_csv(scb, index=False)
    fl = _ROOT / "data" / "regime" / f"mc_regime_filter_trades_{_STAMP}.parquet"
    f.to_parquet(fl)
    _log(f"\nWROTE {scb.name} + {fl.name}")


if __name__ == "__main__":
    main()
