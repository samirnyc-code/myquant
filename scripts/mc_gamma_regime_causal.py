"""Causal gamma-regime × MC hold-to-close edge, three definitions (S55).

User's correction: S54 tested only net_gex SIGN. The dealer-gamma framing is
sign(spot - flip_level), where flip = HVL (published pre-market). Test all three,
all CAUSAL (MQ row re-dated to the trading day it applies to, MQ_APPLY_NEXT_DAY=1):

  R_hvl  = open < HVL_prev      -> "neg" (below flip, amplify)   else "pos"
  R_gw   = open < gamma_wall_0dte_prev -> "neg" else "pos"
  R_ngex = net_gex < 0          -> "neg" (positioning)           else "pos"

Two questions (n=82 MQ days, 2026 only -> HYPOTHESIS-GEN, not confirmation):
  Q1 (day level): does regime predict the Dalton day type? P(extension | neg) vs pos.
  Q2 (trade level, 3R): does the hold-to-close / EOD edge concentrate on neg-regime days?

EXTENSION day types = {Trend, Double Distribution, Normal Variation} (hold-to-close pays)
BALANCE            = {Normal, Nontrend}          Neutral reported separately.
"""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ["MQ_APPLY_NEXT_DAY"] = "1"          # causal d->d+1

import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

import massive
from bar_analysis import parse_signals
from simulation_engine import simulate_trades, INSTRUMENTS
from auction_features import build_session_features
from menthorq_edge_study import load_mq, BARS_PQ
from menthorq_sr_followup import offsets_for

SIG = ROOT / "data" / "signals" / ("MyMicroChannel Signal Export - ES SEP26 - 5 Minute "
                                   "from 02.07.2026 - 1850 Days.txt")
EXT = {"Trend", "Double Distribution", "Normal Variation"}
BAL = {"Normal", "Nontrend"}
RNG = np.random.default_rng(42)


def _ci(x, it=4000):
    x = np.asarray(x, float)
    if len(x) < 5: return (np.nan, np.nan)
    m = [RNG.choice(x, len(x)).mean() for _ in range(it)]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def _tl(f, lbl):
    if len(f) < 5:
        print(f"  {lbl:26s} n={len(f):4d}  (thin)"); return
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    er = f["ExitReason"].astype(str)
    eod = ~(er.str.contains("Target") | er.isin(["T1+BE", "T1_only"]) | er.isin(["Stop", "E1E2+Stop"]))
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    lo, hi = _ci(nr)
    print(f"  {lbl:26s} n={len(f):4d}  netR={nr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  "
          f"PF={g/abs(l) if l else 9.99:.2f}  ${f.NetPnL.sum():+,.0f}  "
          f"EOD {eod.mean()*100:.0f}% (${f.loc[eod,'NetPnL'].sum():+,.0f})")


def main():
    sig = parse_signals(SIG.read_text())
    bars = pd.read_parquet(BARS_PQ); bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    bars["_d"] = bars["DateTime"].dt.date

    # per-session features (day_type) + open
    feat = build_session_features(bars.rename(columns={"_d": "Date"}) if "Date" not in bars else bars)
    feat = feat.copy()
    # build_session_features indexes by session date; find its date col
    dcol = "Date" if "Date" in feat.columns else feat.columns[0]
    opens = bars.groupby("_d")["Open"].first()
    day = pd.DataFrame({"date": pd.to_datetime(list(opens.index)), "open": opens.values})
    dt_map = dict(zip(pd.to_datetime(feat[dcol]) if dcol in feat else feat.index, feat["day_type"]))
    day["day_type"] = day["date"].map(dt_map)

    # MQ causal
    mq = load_mq(); mq["date"] = mq["date"].dt.normalize()
    off = offsets_for(mq, bars); mq = mq[mq["date"].isin(off)].reset_index(drop=True)
    mq["_off"] = mq["date"].map(off)
    mq["hvl_c"] = mq["high_vol_level"] + mq["_off"]
    mq["gw_c"] = mq["gamma_wall_0dte"] + mq["_off"]
    mq["ngex"] = pd.to_numeric(mq["net_gex"].astype(str).str.replace("M", "e6").str.replace("B", "e9"), errors="coerce")

    d = mq.merge(day, on="date", how="inner")
    d["R_hvl"] = np.where(d["open"] < d["hvl_c"], "neg", "pos")
    d["R_gw"] = np.where(d["open"] < d["gw_c"], "neg", "pos")
    d["R_ngex"] = np.where(d["ngex"] < 0, "neg", "pos")
    d["ext"] = d["day_type"].isin(EXT)
    d["Date"] = d["date"].dt.date

    print(f"MQ trading days matched: {len(d)}  ({d.date.min().date()}→{d.date.max().date()})")
    print(f"day_type mix: " + ", ".join(f"{k} {v}" for k, v in d.day_type.value_counts().items()))

    print("\n" + "=" * 84)
    print("Q1 — does regime predict the day type? P(EXTENSION day | regime)")
    print("=" * 84)
    for arm in ("R_hvl", "R_gw", "R_ngex"):
        ne = d.loc[d[arm] == "neg", "ext"]; po = d.loc[d[arm] == "pos", "ext"]
        print(f"  {arm:7s}  neg: {ne.mean()*100:4.0f}% ext (n={len(ne)})   "
              f"pos: {po.mean()*100:4.0f}% ext (n={len(po)})   Δ={((ne.mean()-po.mean())*100):+.0f}pp")

    # trades at 3R on MQ days
    dates = sorted(set(sig["Date"]) & set(d["Date"]))
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: g.reset_index(drop=True) for dd, g in bars.groupby("_d") if dd in tbd}
    sig_mq = sig[sig["Date"].isin(tbd)].copy()
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1, tick_value=INSTRUMENTS["ES"]["tick_value"],
              contracts=1, commission=4.36, pb_round="nearest")
    raw = simulate_trades(signals=sig_mq, ticks_by_date=tbd, bars_by_date=bbd, target_r=3.0, ratchet_r=0.0, **bp)
    tr = raw[raw["Filled"] == True].copy()
    tr = tr.merge(d[["Date", "R_hvl", "R_gw", "R_ngex", "ext", "day_type"]], on="Date", how="inner")

    print("\n" + "=" * 84)
    print(f"Q2 — MC trades @3R on MQ days (n={len(tr)}) — hold-to-close edge by regime")
    print("=" * 84)
    _tl(tr, "ALL MQ-day trades")
    for arm in ("R_hvl", "R_gw", "R_ngex"):
        print(f"-- {arm} --")
        _tl(tr[tr[arm] == "neg"], f"{arm}=neg (below flip)")
        _tl(tr[tr[arm] == "pos"], f"{arm}=pos (above flip)")

    print("\n-- day-type cross (all MQ trades) --")
    _tl(tr[tr["ext"]], "EXTENSION day types")
    _tl(tr[~tr["ext"] & ~tr["day_type"].eq("Neutral")], "BALANCE day types")
    _tl(tr[tr["day_type"].eq("Neutral")], "Neutral days")


if __name__ == "__main__":
    main()
