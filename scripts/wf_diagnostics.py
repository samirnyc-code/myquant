"""S55 follow-up: (1) NR7ORB validation pass, (2) S3_early13@3R tradeability diagnostics.

NR7ORB: per-year OOS breakdown + pre-specified parameter neighborhood
  NR{4,7} x ORB K{3,6,12} x target {2,3,99=EOD}. If the original cell (NR7,K6)
  is a lone spike and neighbors are dead, it's noise. All cells reported.

S3_early13@3R: exit-reason mix (Target/Stop/EOD $ contribution), 1-contract
  equity max drawdown + longest underwater, per-year, concurrency and
  simultaneous long+short (hedge) exposure.
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
RNG = np.random.default_rng(42)


def nr_orb_signals(bars, day, nr_n, K):
    rows = []
    nr = (day["rng"] == day["rng"].rolling(nr_n).min()).shift(1).fillna(False)
    for d, g in bars.groupby("_d"):
        if not nr.get(d, False): continue
        g = g.reset_index(drop=True)
        if len(g) < K + 2: continue
        orh = g["High"].iloc[:K].max(); orl = g["Low"].iloc[:K].min()
        for i in range(K, len(g) - 1):
            c, a = g["Close"].iloc[i], g["atr"].iloc[i]
            if not np.isfinite(a) or a <= 0: continue
            if c > orh:
                rows.append(dict(DateTime=g["DateTime"].iloc[i + 1], Direction="Long",
                                 SignalPrice=float(c), StopPrice=float(c - a), Date=d)); break
            if c < orl:
                rows.append(dict(DateTime=g["DateTime"].iloc[i + 1], Direction="Short",
                                 SignalPrice=float(c), StopPrice=float(c + a), Date=d)); break
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("DateTime").reset_index(drop=True)
    df["SignalNum"] = np.arange(1, len(df) + 1); df["SignalType"] = "raw"; df["BarNum"] = 0
    return df


def mrow(f):
    if len(f) < 8: return None
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    return dict(n=len(f), netR=float(nr.mean()), pf=float(g / abs(l)) if l else 9.99,
                net=float(f.NetPnL.sum()))


def dd_stats(f):
    f = f.sort_values("EntryTime")
    eq = f["NetPnL"].cumsum()
    dd = eq - eq.cummax()
    maxdd = float(dd.min())
    # longest underwater in calendar days
    dts = pd.to_datetime(f["Date"]).to_numpy(); longest, start = 0, None
    for i, u in enumerate((dd < 0).to_numpy()):
        if u and start is None: start = dts[i]
        elif not u and start is not None:
            longest = max(longest, int((dts[i] - start) / np.timedelta64(1, "D"))); start = None
    if start is not None:
        longest = max(longest, int((dts[-1] - start) / np.timedelta64(1, "D")))
    return maxdd, longest


def main():
    bars = pd.read_parquet(BARS).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"]); bars["_d"] = bars["DateTime"].dt.date
    bars["atr"] = bars.groupby("_d", group_keys=False).apply(
        lambda g: (g["High"] - g["Low"]).rolling(20, min_periods=5).mean().shift(1))
    day = bars.groupby("_d").agg(h=("High", "max"), l=("Low", "min"))
    day["rng"] = day["h"] - day["l"]
    day["adr14"] = day["rng"].rolling(14, min_periods=5).mean().shift(1)
    day["ptrend"] = (day["rng"] > 1.6 * day["adr14"]).shift(1).fillna(False)

    dates = sorted(bars["_d"].unique())
    print(f"loading ticks {len(dates)} days…", flush=True)
    tbd = {}
    for dd_ in dates:
        t = massive.load_continuous_ticks(dd_)
        if not t.empty: tbd[dd_] = t
    bbd = {dd_: g.reset_index(drop=True) for dd_, g in bars.groupby("_d")}
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1,
              tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
              commission=4.36, pb_round="nearest")

    # ── 1) NR7ORB neighborhood ──
    print("\n" + "=" * 90)
    print("NR-ORB PARAMETER NEIGHBORHOOD — OOS only (2022-06-18..)  [original cell: NR7,K6]")
    print("=" * 90)
    print(f"{'cell':16s} {'n':>4s} {'netR':>8s} {'PF':>6s} {'net$':>10s}")
    keep = {}
    for nr_n in (4, 7):
        for K in (3, 6, 12):
            sig = nr_orb_signals(bars, day, nr_n, K)
            if sig.empty: continue
            for tr in (2.0, 3.0, 99.0):
                raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd,
                                      target_r=tr, ratchet_r=0.0, **bp)
                f = raw[raw["Filled"] == True].copy()
                f["dt"] = pd.to_datetime(f["Date"])
                o = f[f["dt"] >= SPLIT]
                m = mrow(o)
                tag = f"NR{nr_n},K{K}@{'EOD' if tr == 99 else f'{tr:g}R'}"
                if m: print(f"{tag:16s} {m['n']:4d} {m['netR']:+8.3f} {m['pf']:6.2f} {m['net']:+10,.0f}")
                if nr_n == 7 and K == 6 and tr == 99.0: keep["nr"] = o

    if "nr" in keep:
        o = keep["nr"]
        print("\nNR7,K6@EOD per-year (OOS):")
        for y, grp in o.groupby(pd.to_datetime(o["Date"]).dt.year):
            m = mrow(grp)
            if m: print(f"  {y}: n={m['n']:3d} netR={m['netR']:+.3f} PF={m['pf']:.2f} ${m['net']:+,.0f}")
        mdd, uw = dd_stats(o)
        print(f"  maxDD ${mdd:+,.0f} | longest underwater {uw}d")

    # ── 2) S3_early13@3R diagnostics ──
    sig = parse_signals(SIG.read_text()).reset_index(drop=True)
    st = _ib_break_state(sig, bars).values
    is_long = sig["Direction"].astype(str).str.upper().str.startswith("L")
    counter = ((is_long & (st == "down")) | (~is_long & (st == "up")))
    ptrend = sig["Date"].map(day["ptrend"]).fillna(False).astype(bool)
    tod = sig["DateTime"].dt.hour * 60 + sig["DateTime"].dt.minute
    mask = (~counter & ~ptrend & (tod < 13 * 60))
    raw = simulate_trades(signals=sig[mask].copy(), ticks_by_date=tbd, bars_by_date=bbd,
                          target_r=3.0, ratchet_r=0.0, **bp)
    f = raw[raw["Filled"] == True].copy()
    f["dt"] = pd.to_datetime(f["Date"])
    o = f[f["dt"] >= SPLIT].copy()

    print("\n" + "=" * 90)
    print(f"S3_early13@3R — OOS diagnostics (n={len(o)})")
    print("=" * 90)
    er = o["ExitReason"].astype(str)
    tgt = er.str.contains("Target"); stp = er.isin(["Stop", "E1E2+Stop"]); eod = ~tgt & ~stp
    for lbl, m_ in (("Target", tgt), ("Stop", stp), ("EOD", eod)):
        print(f"  {lbl:7s} {m_.mean()*100:5.1f}%  ${o.loc[m_, 'NetPnL'].sum():+,.0f}")
    mdd, uw = dd_stats(o)
    print(f"  maxDD (1 ES, chronological): ${mdd:+,.0f} | longest underwater: {uw} days")
    print(f"  net/DD: {o['NetPnL'].sum() / abs(mdd):.1f}")
    print("  per-year:")
    for y, grp in o.groupby(o["dt"].dt.year):
        m = mrow(grp)
        mdd_y, _ = dd_stats(grp)
        print(f"    {y}: n={m['n']:4d} netR={m['netR']:+.3f} PF={m['pf']:.2f} "
              f"${m['net']:+,.0f}  yearDD ${mdd_y:+,.0f}")

    # concurrency / hedge
    ev = []
    for _, r in o.iterrows():
        ev.append((r["EntryTime"], 1, r["Direction"])); ev.append((r["ExitTime"], -1, r["Direction"]))
    ev.sort(key=lambda x: (x[0], x[1]))
    nl = ns = 0; maxc = 0; hedge_time = 0; last = None; tot = 0; hedge_events = 0
    for t, delta, d in ev:
        if last is not None:
            span = (t - last).total_seconds()
            tot += span
            if nl > 0 and ns > 0: hedge_time += span
        if delta == 1:
            if d == "Long":
                nl += 1
                if ns > 0: hedge_events += 1
            else:
                ns += 1
                if nl > 0: hedge_events += 1
        else:
            if d == "Long": nl -= 1
            else: ns -= 1
        maxc = max(maxc, nl + ns); last = t
    print(f"  concurrency: max {maxc} open | long+short simultaneously: "
          f"{hedge_events} entries ({hedge_events/len(o)*100:.1f}% of trades), "
          f"{hedge_time/tot*100:.1f}% of open-time")


if __name__ == "__main__":
    main()
