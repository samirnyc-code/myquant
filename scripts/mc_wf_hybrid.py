"""Track B — MC signals as entry engine; selection/exits re-derived on YEAR 1 ONLY (S55).

Honest version of Stack v2: the original 3 skip rules were discovered on the full
sample. Here the SAME pre-specified filter menu is evaluated on dev-year data only
(2021-06-18..2022-06-17), a config is selected by a pre-specified rule, and the
OOS window (2022-06-18..2026-07-02) is scored untouched. All configs' OOS reported.

Filter menu (all causal at signal time, pre-specified):
  none        — unfiltered
  early13     — signal before 13:00 CT
  early14     — signal before 14:00 CT
  noCIB       — skip counter-IB-break (stack F1 logic)
  noPT        — skip day after prior trend day (prior range > 1.6 x ADR14)
  S3          — noCIB + noPT + early14  (= Stack v2 rules, year-1-derived)
  S3_long     — S3, Longs only
  S3_early13  — noCIB + noPT + early13
Targets: {1, 2, 3}R. Selection rule: dev netR >= +0.08 AND PF >= 1.2 AND n >= 100;
pick max dev netR among qualifiers.
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
from stack_filter import _ib_break_state

SIG = ROOT / "data" / "signals" / ("MyMicroChannel Signal Export - ES SEP26 - 5 Minute "
                                   "from 02.07.2026 - 1850 Days.txt")
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
SPLIT = pd.Timestamp("2022-06-18")
TARGETS = [1.0, 2.0, 3.0]
RNG = np.random.default_rng(42)


def metrics(f):
    if len(f) < 30: return None
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    m = [RNG.choice(nr, len(nr)).mean() for _ in range(3000)]
    by = f.groupby(pd.to_datetime(f["Date"]).dt.year)["NetPnL"].sum()
    return dict(n=len(f), netR=float(nr.mean()), lo=float(np.percentile(m, 2.5)),
                hi=float(np.percentile(m, 97.5)), pf=float(g / abs(l)) if l else 9.99,
                net=float(f.NetPnL.sum()), yrs=f"{int((by > 0).sum())}/{len(by)}")


def main():
    sig = parse_signals(SIG.read_text())
    bars = pd.read_parquet(BARS).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"]); bars["_d"] = bars["DateTime"].dt.date

    # causal per-signal features
    sig = sig.reset_index(drop=True)
    st = _ib_break_state(sig, bars).values
    is_long = sig["Direction"].astype(str).str.upper().str.startswith("L")
    counter = ((is_long & (st == "down")) | (~is_long & (st == "up")))
    day = bars.groupby("_d").agg(h=("High", "max"), l=("Low", "min"))
    day["rng"] = day["h"] - day["l"]
    day["adr14"] = day["rng"].rolling(14, min_periods=5).mean().shift(1)
    day["ptrend"] = (day["rng"] > 1.6 * day["adr14"]).shift(1).fillna(False)
    ptrend = sig["Date"].map(day["ptrend"]).fillna(False).astype(bool)
    tod = sig["DateTime"].dt.hour * 60 + sig["DateTime"].dt.minute
    masks = {
        "none":       pd.Series(True, index=sig.index),
        "early13":    tod < 13 * 60,
        "early14":    tod < 14 * 60,
        "noCIB":      ~counter,
        "noPT":       ~ptrend,
        "S3":         ~counter & ~ptrend & (tod < 14 * 60),
        "S3_long":    ~counter & ~ptrend & (tod < 14 * 60) & is_long,
        "S3_early13": ~counter & ~ptrend & (tod < 13 * 60),
    }

    dates = sorted(sig["Date"].unique())
    print(f"{len(sig)} signals, loading ticks {len(dates)} days…", flush=True)
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: g.reset_index(drop=True) for dd, g in bars.groupby("_d")}
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1,
              tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
              commission=4.36, pb_round="nearest")

    dev_rows, oos_rows = [], []
    for tr in TARGETS:                       # one sim per target; filters subset post-hoc
        raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd,
                              target_r=tr, ratchet_r=0.0, **bp)
        f = raw[raw["Filled"] == True].copy()
        f["dt"] = pd.to_datetime(f["Date"])
        keep = f["SignalNum"].map(dict(zip(sig["SignalNum"], sig.index)))
        for name, m in masks.items():
            sel = f[keep.map(m).fillna(False)]
            cfg = f"{name}@{tr:g}R"
            dev_rows.append((cfg, metrics(sel[sel["dt"] < SPLIT])))
            oos_rows.append((cfg, metrics(sel[sel["dt"] >= SPLIT])))

    def show(rows, title):
        print(f"\n{'='*98}\n{title}\n{'='*98}")
        print(f"{'config':16s} {'n':>5s} {'netR':>8s} {'95% CI':>18s} {'PF':>6s} {'net$':>12s} {'yrs+':>6s}")
        for name, m in rows:
            if not m: print(f"{name:16s}   (thin)"); continue
            print(f"{name:16s} {m['n']:5d} {m['netR']:+8.3f} "
                  f"[{m['lo']:+.3f},{m['hi']:+.3f}] {m['pf']:6.2f} {m['net']:+12,.0f} {m['yrs']:>6s}")

    show(dev_rows, "DEV — 2021-06-18 .. 2022-06-17 (selection window)")
    show(oos_rows, "OOS — 2022-06-18 .. 2026-07-02 (untouched; bar: +0.08R, PF1.3, lo>+0.04)")

    elig = [(n, m) for n, m in dev_rows if m and m["netR"] >= 0.08 and m["pf"] >= 1.2 and m["n"] >= 100]
    if elig:
        pick = max(elig, key=lambda x: x[1]["netR"])[0]
        om = dict(oos_rows).get(pick)
        print(f"\nDEV-SELECTED: {pick}")
        if om:
            verdict = ("CLEARS BAR" if om["netR"] >= 0.08 and om["pf"] >= 1.3 and om["lo"] > 0.04
                       else "fails bar")
            print(f"  OOS: netR={om['netR']:+.3f} [{om['lo']:+.3f},{om['hi']:+.3f}] "
                  f"PF={om['pf']:.2f} ${om['net']:+,.0f} yrs+{om['yrs']}  -> {verdict}")
    else:
        print("\nNo dev config qualified (netR>=+0.08, PF>=1.2, n>=100).")


if __name__ == "__main__":
    main()
