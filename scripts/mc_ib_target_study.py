"""IB-edge-as-target study on the UNFILTERED MC book (improvement lever ①).

Two questions:
  A) How much do wider FLAT targets help the raw book? (target sweep 1..5R + 3R+BE)
  B) Does routing each trade to its OPPOSITE IB edge (the natural rotation target)
     beat the best flat target?

IB = high/low of the first 60 min (12 x 5M bars) of the RTH session (auction_features
convention). For a Long the rotation target is IB_High; for a Short, IB_Low. Trades
whose entry is already beyond that edge (edge behind price) have no forward IB target
and fall back to a flat default.

Method note: absolute per-signal targets aren't native to simulate_trades (target is a
scalar R per run), so the IB-edge book is APPROXIMATED by a fine flat-R grid — each
trade takes the outcome from the grid run whose target_r is closest to its IB-edge
R-distance (snapped, clamped to the grid). Faithful to the engine; grid-quantised.
Net R = NetPnL/RiskDollar (after $4.36 comm) — the tradeable metric.
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

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_COMM = 4.36
_IB_BARS = 12
_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
_FALLBACK_R = 2.0  # edge-behind trades


def _log(m): print(m, flush=True)


def _boot_ci(x, iters=5000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(x)
    m = np.array([rng.choice(x, n, replace=True).mean() for _ in range(iters)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def _line(filled, label):
    nr = (filled["NetPnL"] / filled["RiskDollar"]).to_numpy()
    net = float(filled["NetPnL"].sum())
    wr = float((filled["NetPnL"] > 0).mean()) * 100
    g = filled.loc[filled["NetPnL"] > 0, "NetPnL"].sum()
    l = filled.loc[filled["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(g / abs(l)) if l else float("inf")
    lo, hi = _boot_ci(nr)
    by = filled.groupby(pd.to_datetime(filled["Date"]).dt.year)["NetPnL"].sum()
    _log(f"{label:22s} n={len(filled):5d}  netR={nr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  "
         f"WR={wr:.0f}%  PF={pf:.2f}  ${net:+,.0f}  yrs+{int((by>0).sum())}/{len(by)}")
    return dict(net=net, netR=float(nr.mean()), pf=pf)


def main():
    sig = parse_signals(_SIG_TXT.read_text())
    _log(f"{len(sig)} MC signals {sig['Date'].min()}→{sig['Date'].max()}")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars["_d"] = bars["DateTime"].dt.date
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby("_d")}

    # IB high/low per day (first 12 RTH bars)
    ib = {}
    for d, g in bars_by_date.items():
        h = g.iloc[:_IB_BARS]
        ib[d] = (float(h["High"].max()), float(h["Low"].min()))

    dates = sorted(sig["Date"].unique())
    _log(f"Loading ticks for {len(dates)} days…")
    ticks_by_date = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    _log(f"ticks: {len(ticks_by_date)}/{len(dates)} days\n")

    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1,
              tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
              commission=_COMM, pb_round="nearest")

    # ── grid runs (reuse cached ticks) ──
    runs = {}
    for tr in _GRID:
        raw = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                              bars_by_date=bars_by_date, target_r=tr, ratchet_r=0.0, **bp)
        runs[tr] = raw[raw["Filled"] == True].copy()  # noqa: E712

    _log("=" * 96)
    _log("A) UNFILTERED FLAT-TARGET SWEEP (net R after comm)")
    _log("=" * 96)
    for tr in _GRID:
        _line(runs[tr], f"flat {tr:g}R")
    # 3R + BE-after-1R (the S53 stack winner) on the raw book
    raw_be = simulate_trades(signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
                             target_r=3.0, ratchet_r=1.0, ratchet_dest="BE", **bp)
    _line(raw_be[raw_be["Filled"] == True].copy(), "3R + BE@1R")  # noqa: E712

    # ── B) IB-edge target ──
    base = runs[1.0][["SignalNum", "Direction", "FillPrice", "RiskPts", "Date"]].copy()
    base = base.merge(sig[["SignalNum"]], on="SignalNum", how="left")
    base["IB_High"] = base["Date"].map(lambda d: ib.get(d, (np.nan, np.nan))[0])
    base["IB_Low"] = base["Date"].map(lambda d: ib.get(d, (np.nan, np.nan))[1])
    is_long = base["Direction"] == "Long"
    edge = np.where(is_long, base["IB_High"], base["IB_Low"])
    fwd = np.where(is_long, edge - base["FillPrice"], base["FillPrice"] - edge)  # dist ahead (pts)
    base["ib_target_r"] = fwd / base["RiskPts"]
    base["reachable"] = base["ib_target_r"] > 0

    _log("\n" + "=" * 96)
    _log("B) IB-EDGE (opposite) AS TARGET")
    _log("=" * 96)
    reach = base["reachable"].mean() * 100
    q = base.loc[base["reachable"], "ib_target_r"].quantile([.25, .5, .75])
    _log(f"forward-reachable IB edge: {reach:.0f}% of trades | ib_target_r quartiles "
         f"(reachable): {q[.25]:.2f} / {q[.5]:.2f} / {q[.75]:.2f}R "
         f"| edge-behind (fallback {_FALLBACK_R:g}R): {100-reach:.0f}%")

    # route each signal to nearest grid target (clamp), edge-behind -> fallback
    grid = np.array(_GRID)
    def _route_r(r):
        if not np.isfinite(r) or r <= 0:
            return _FALLBACK_R
        return float(grid[np.argmin(np.abs(grid - min(max(r, grid[0]), grid[-1])))])
    base["route_r"] = base["ib_target_r"].map(_route_r)

    rows = []
    for tr, grp in base.groupby("route_r"):
        r = runs[tr].set_index("SignalNum")
        sel = r.loc[r.index.intersection(grp["SignalNum"])]
        rows.append(sel)
    ib_book = pd.concat(rows).reset_index()
    _line(ib_book, "IB-edge target (routed)")

    # for reference: same routing but reachable-only (drop edge-behind entirely)
    ib_reach = ib_book.merge(base[["SignalNum", "reachable"]], on="SignalNum")
    _line(ib_reach[ib_reach["reachable"]].copy(), "  IB-edge (reachable only)")
    _log("")


if __name__ == "__main__":
    main()
