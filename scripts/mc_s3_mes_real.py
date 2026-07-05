"""S3_early13@3R under REAL trading constraints (S55): MES only, $2.00 RT,
no simultaneous long+short (first-in-wins: an entry against a still-open opposite
position is SKIPPED; skipped trades do not block later entries — S53 convention).

Reports OOS (2022-06-18..) before/after the no-hedge pass: netR, PF, $, maxDD,
per-year, and how many trades the rule removed.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import massive
from bar_analysis import parse_signals
from simulation_engine import simulate_trades
from stack_filter import _ib_break_state

SIG = ROOT / "data" / "signals" / ("MyMicroChannel Signal Export - ES SEP26 - 5 Minute "
                                   "from 02.07.2026 - 1850 Days.txt")
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
SPLIT = pd.Timestamp("2022-06-18")
TICK_VALUE_MES = 1.25
COMM_MES = 2.00
RNG = np.random.default_rng(42)


def no_hedge(f):
    """First-in-wins chronological pass. Returns kept frame."""
    f = f.sort_values("EntryTime").reset_index(drop=True)
    open_list = []   # (ExitTime, Direction)
    keep = np.ones(len(f), dtype=bool)
    for i, r in f.iterrows():
        t = r["EntryTime"]
        open_list = [(x, d) for (x, d) in open_list if x > t]
        if any(d != r["Direction"] for (_, d) in open_list):
            keep[i] = False          # conflicts with open opposite position
            continue
        open_list.append((r["ExitTime"], r["Direction"]))
    return f[keep].copy(), int((~keep).sum())


def stats(f, label):
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    m = [RNG.choice(nr, len(nr)).mean() for _ in range(3000)]
    lo, hi = np.percentile(m, 2.5), np.percentile(m, 97.5)
    eq = f.sort_values("EntryTime")["NetPnL"].cumsum()
    mdd = float((eq - eq.cummax()).min())
    print(f"{label:28s} n={len(f):5d}  netR={nr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  "
          f"PF={g/abs(l) if l else 9.99:.2f}  ${f.NetPnL.sum():+,.0f}  maxDD ${mdd:+,.0f}")
    return mdd


def main():
    sig = parse_signals(SIG.read_text()).reset_index(drop=True)
    bars = pd.read_parquet(BARS).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"]); bars["_d"] = bars["DateTime"].dt.date
    day = bars.groupby("_d").agg(h=("High", "max"), l=("Low", "min"))
    day["rng"] = day["h"] - day["l"]
    day["adr14"] = day["rng"].rolling(14, min_periods=5).mean().shift(1)
    day["ptrend"] = (day["rng"] > 1.6 * day["adr14"]).shift(1).fillna(False)

    st = _ib_break_state(sig, bars).values
    is_long = sig["Direction"].astype(str).str.upper().str.startswith("L")
    counter = ((is_long & (st == "down")) | (~is_long & (st == "up")))
    ptrend = sig["Date"].map(day["ptrend"]).fillna(False).astype(bool)
    tod = sig["DateTime"].dt.hour * 60 + sig["DateTime"].dt.minute
    s3 = sig[(~counter & ~ptrend & (tod < 13 * 60))].copy()

    dates = sorted(s3["Date"].unique())
    print(f"{len(s3)} S3_early13 signals, loading ticks {len(dates)} days…", flush=True)
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: g.reset_index(drop=True) for dd, g in bars.groupby("_d")}

    raw = simulate_trades(signals=s3, ticks_by_date=tbd, bars_by_date=bbd,
                          target_r=3.0, ratchet_r=0.0,
                          entry_slip=1.0, exit_slip=1.0, stop_offset=1,
                          tick_value=TICK_VALUE_MES, contracts=1,
                          commission=COMM_MES, pb_round="nearest")
    f = raw[raw["Filled"] == True].copy()
    f["dt"] = pd.to_datetime(f["Date"])
    o = f[f["dt"] >= SPLIT].copy()

    print("\n" + "=" * 96)
    print("S3_early13@3R — MES $1.25/tick, $2.00 RT, OOS 2022-06-18..2026-07-02")
    print("=" * 96)
    stats(o, "MES all signals (hedged)")
    kept, dropped = no_hedge(o)
    stats(kept, f"MES no-hedge (skip {dropped})")
    print("\nper-year (no-hedge):")
    for y, grp in kept.groupby(kept["dt"].dt.year):
        nr = (grp["NetPnL"] / grp["RiskDollar"]).mean()
        g = grp.loc[grp.NetPnL > 0, "NetPnL"].sum(); l = grp.loc[grp.NetPnL < 0, "NetPnL"].sum()
        eq = grp.sort_values("EntryTime")["NetPnL"].cumsum()
        mdd = float((eq - eq.cummax()).min())
        print(f"  {y}: n={len(grp):4d} netR={nr:+.3f} PF={g/abs(l) if l else 9.99:.2f} "
              f"${grp.NetPnL.sum():+,.0f}  yearDD ${mdd:+,.0f}")
    # concurrency after no-hedge
    ev = []
    for _, r in kept.iterrows():
        ev.append((r["EntryTime"], 1)); ev.append((r["ExitTime"], -1))
    ev.sort()
    c = mx = 0
    for _, d in ev:
        c += d; mx = max(mx, c)
    print(f"\nmax concurrent MES after no-hedge: {mx}")


if __name__ == "__main__":
    main()
