"""Causal first-hour proxy for the extension/trend day — full 5.5yr MC book @3R (S55).

The 80-day MQ study showed the hold-to-close edge lives ENTIRELY on extension day
types (+0.28R) and LOSES on balance days (-0.31R) — but `day_type` is an END-OF-DAY
label (lookahead). Question: can a CAUSAL, first-hour-knowable proxy recover that split
on the full sample?

Proxies (all knowable by ~IB close / at entry):
  P1  IB width / ADR  (Dalton: narrow base -> gets upset -> extension). Terciles.
      Restricted to entries AFTER the IB completes (BarNum > 12) so it's causal.
  P2  IB broken at entry (real-time extension in progress) vs not — per signal.
  P3  IB broken AND aligned with trade direction (trading with the extension).
Oracle for comparison: EOD `day_type` (extension vs balance) on the SAME full sample.

@3R, realistic exec, net R after $4.36 comm. EOD = neither Target nor Stop.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

import massive
from bar_analysis import parse_signals
from simulation_engine import simulate_trades, INSTRUMENTS
from auction_features import build_session_features
from stack_filter import _ib_break_state

SIG = ROOT / "data" / "signals" / ("MyMicroChannel Signal Export - ES SEP26 - 5 Minute "
                                   "from 02.07.2026 - 1850 Days.txt")
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
EXT = {"Trend", "Double Distribution", "Normal Variation"}
BAL = {"Normal", "Nontrend"}
RNG = np.random.default_rng(42)


def _ci(x, it=4000):
    x = np.asarray(x, float)
    if len(x) < 5: return (np.nan, np.nan)
    m = [RNG.choice(x, len(x)).mean() for _ in range(it)]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def _tl(f, lbl):
    if len(f) < 10:
        print(f"  {lbl:30s} n={len(f):5d}  (thin)"); return
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    er = f["ExitReason"].astype(str)
    eod = ~(er.str.contains("Target") | er.isin(["T1+BE", "T1_only", "Stop", "E1E2+Stop"]))
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    lo, hi = _ci(nr)
    by = f.groupby(pd.to_datetime(f["Date"]).dt.year)["NetPnL"].sum()
    print(f"  {lbl:30s} n={len(f):5d}  netR={nr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  "
          f"PF={g/abs(l) if l else 9.99:.2f}  ${f.NetPnL.sum():+,.0f}  yrs+{int((by>0).sum())}/{len(by)}  "
          f"EOD {eod.mean()*100:.0f}%(${f.loc[eod,'NetPnL'].sum():+,.0f})")


def main():
    sig = parse_signals(SIG.read_text())
    bars = pd.read_parquet(BARS).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"]); bars["_d"] = bars["DateTime"].dt.date

    # per-session features (causal: ADR = prior rolling range)
    feat = build_session_features(bars)
    feat["Date"] = pd.to_datetime(feat["Date"]).dt.date
    feat["ibw_adr"] = feat["IB_width"] / feat["ADR"]
    # causal width terciles
    q1, q2 = feat["ibw_adr"].quantile([1/3, 2/3])
    feat["ibw_band"] = np.where(feat["ibw_adr"] <= q1, "narrow",
                        np.where(feat["ibw_adr"] >= q2, "wide", "mid"))
    feat["ext_day"] = feat["day_type"].isin(EXT)

    # per-signal real-time IB break state at entry
    sig = sig.reset_index(drop=True)
    sig["ib_state"] = _ib_break_state(sig, bars).values     # up/down/both/none at signal time
    is_long = sig["Direction"].astype(str).str.upper().str.startswith("L")
    sig["broken"] = sig["ib_state"].isin(["up", "down", "both"])
    sig["aligned"] = ((is_long & sig["ib_state"].isin(["up", "both"])) |
                      (~is_long & sig["ib_state"].isin(["down", "both"])))

    dates = sorted(sig["Date"].unique())
    print(f"{len(sig)} signals, loading ticks for {len(dates)} days…")
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: g.reset_index(drop=True) for dd, g in bars.groupby("_d")}
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1, tick_value=INSTRUMENTS["ES"]["tick_value"],
              contracts=1, commission=4.36, pb_round="nearest")
    raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd, target_r=3.0, ratchet_r=0.0, **bp)
    tr = raw[raw["Filled"] == True].copy()

    # attach per-signal + per-day features via map (no merge column collisions)
    tr["BarNum"] = tr["SignalNum"].map(dict(zip(sig["SignalNum"], sig["BarNum"])))
    tr["broken"] = tr["SignalNum"].map(dict(zip(sig["SignalNum"], sig["broken"])))
    tr["aligned"] = tr["SignalNum"].map(dict(zip(sig["SignalNum"], sig["aligned"])))
    for col in ("ibw_band", "ext_day", "day_type"):
        tr[col] = tr["Date"].map(dict(zip(feat["Date"], feat[col])))
    cache = ROOT / "data" / "signals" / "_mc_trendday_3R.parquet"
    tr.to_parquet(cache)
    print(f"cached {len(tr)} trades -> {cache.name}   cols ok: "
          f"{all(c in tr for c in ['BarNum','broken','aligned','ext_day'])}")

    print("\n" + "=" * 96)
    print(f"ORACLE (lookahead, full sample) — EOD day_type   n={len(tr)}")
    print("=" * 96)
    _tl(tr, "ALL @3R")
    _tl(tr[tr["ext_day"] == True], "EXTENSION day types")
    _tl(tr[(tr["ext_day"] == False) & (tr["day_type"] != "Neutral")], "BALANCE day types")
    _tl(tr[tr["day_type"] == "Neutral"], "Neutral days")

    print("\n" + "=" * 96)
    print("P1 CAUSAL — IB width / ADR tercile  (post-IB entries, BarNum>12)")
    print("=" * 96)
    post = tr[tr["BarNum"] > 12]
    print(f"  (post-IB entries: {len(post)}/{len(tr)})   width terciles q1={q1:.2f} q2={q2:.2f}")
    for b in ("narrow", "mid", "wide"):
        _tl(post[post["ibw_band"] == b], f"IBwidth {b}")

    print("\n" + "=" * 96)
    print("P2/P3 CAUSAL — IB break state at entry (real-time extension in progress)")
    print("=" * 96)
    _tl(tr[tr["broken"] == True], "IB broken at entry (any)")
    _tl(tr[tr["broken"] == False], "IB not broken at entry")
    _tl(tr[tr["aligned"] == True], "IB broken & ALIGNED w/ dir")
    _tl(tr[(tr["broken"] == True) & (tr["aligned"] == False)], "IB broken COUNTER to dir")

    print("\n" + "=" * 96)
    print("COMBINED — narrow-IB ∧ aligned-break (causal 'extension day, with it')")
    print("=" * 96)
    _tl(post[(post["ibw_band"] == "narrow") & (post["aligned"] == True)], "narrow IB ∧ aligned")
    _tl(post[(post["ibw_band"] == "wide") & (post["broken"] == False)], "wide IB ∧ unbroken (balance)")


if __name__ == "__main__":
    main()
