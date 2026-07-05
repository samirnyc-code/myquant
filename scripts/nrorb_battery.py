"""NR-ORB full validation battery (S55). Primary cell = NR4,K6 (largest n, NOT the
post-hoc best). Secondary = NR7,K6. All tests pre-specified:

  T1 dev-window neighborhood (2021-06-18..2022-06-17) — OOS-only luck check
  T2 MES costs ($1.25/tick, $2.00 RT) vs ES costs — tight-stop commission drag
  T3 long/short split (OOS)
  T4 stop multiple {0.75, 1.0, 1.5} x ATR20(5m) (OOS, EOD exit)
  T5 concentration: drop best 5 trades; quarterly texture (OOS)
  T6 same-day P&L correlation with MC S3_early13@3R book (OOS)
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

BARS = ROOT / "data" / "bars" / "_continuous.parquet"
SIG = ROOT / "data" / "signals" / ("MyMicroChannel Signal Export - ES SEP26 - 5 Minute "
                                   "from 02.07.2026 - 1850 Days.txt")
SPLIT = pd.Timestamp("2022-06-18")
RNG = np.random.default_rng(42)


def nr_orb_signals(bars, day, nr_n, K, stop_mult=1.0):
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
                                 SignalPrice=float(c), StopPrice=float(c - stop_mult * a), Date=d)); break
            if c < orl:
                rows.append(dict(DateTime=g["DateTime"].iloc[i + 1], Direction="Short",
                                 SignalPrice=float(c), StopPrice=float(c + stop_mult * a), Date=d)); break
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("DateTime").reset_index(drop=True)
    df["SignalNum"] = np.arange(1, len(df) + 1); df["SignalType"] = "raw"; df["BarNum"] = 0
    return df


def row(f, label):
    if len(f) < 8:
        print(f"  {label:34s} n={len(f)} (thin)"); return
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    m = [RNG.choice(nr, len(nr)).mean() for _ in range(3000)]
    lo, hi = np.percentile(m, 2.5), np.percentile(m, 97.5)
    print(f"  {label:34s} n={len(f):4d}  netR={nr.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  "
          f"PF={g/abs(l) if l else 9.99:.2f}  ${f.NetPnL.sum():+,.0f}")


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
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: g.reset_index(drop=True) for dd, g in bars.groupby("_d")}
    ES = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1, tick_value=12.5,
              contracts=1, commission=4.36, pb_round="nearest")
    MES = dict(ES, tick_value=1.25, commission=2.00)

    def run(sig, costs, tr=99.0):
        raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd,
                              target_r=tr, ratchet_r=0.0, **costs)
        f = raw[raw["Filled"] == True].copy()
        f["dt"] = pd.to_datetime(f["Date"])
        return f

    print("\nT1 — DEV window, all cells @EOD (ES costs)")
    for nr_n in (4, 7):
        for K in (3, 6, 12):
            sig = nr_orb_signals(bars, day, nr_n, K)
            f = run(sig, ES)
            row(f[f["dt"] < SPLIT], f"NR{nr_n},K{K}@EOD dev")

    for nr_n, tag in ((4, "PRIMARY NR4,K6"), (7, "secondary NR7,K6")):
        sig = nr_orb_signals(bars, day, nr_n, 6)
        fes = run(sig, ES); oes = fes[fes["dt"] >= SPLIT]
        fmes = run(sig, MES); omes = fmes[fmes["dt"] >= SPLIT]
        print(f"\n{'='*92}\n{tag} @EOD — OOS battery\n{'='*92}")
        avg_risk = omes["RiskDollar"].mean()
        print(f"  avg risk/trade: ES ${oes['RiskDollar'].mean():,.0f} | MES ${avg_risk:,.0f}")
        print("T2 — costs:")
        row(oes, "ES  $4.36")
        row(omes, "MES $2.00 (tradeable version)")
        print("T3 — direction (MES):")
        row(omes[omes["Direction"] == "Long"], "Long")
        row(omes[omes["Direction"] == "Short"], "Short")
        print("T4 — stop multiple (MES, EOD):")
        for sm in (0.75, 1.5):
            s2 = nr_orb_signals(bars, day, nr_n, 6, stop_mult=sm)
            f2 = run(s2, MES)
            row(f2[f2["dt"] >= SPLIT], f"stop {sm}xATR")
        print("T5 — concentration (MES):")
        srt = omes.sort_values("NetPnL", ascending=False)
        row(srt.iloc[5:], "drop best 5 trades")
        q = omes.groupby(omes["dt"].dt.to_period("Q"))["NetPnL"].sum()
        print(f"  quarters +: {(q > 0).sum()}/{len(q)}  worst Q ${q.min():+,.0f}  best Q ${q.max():+,.0f}")

    # T6 — same-day correlation with MC S3_early13@3R (ES-cost book, direction of P&L only)
    mc = parse_signals(SIG.read_text()).reset_index(drop=True)
    st = _ib_break_state(mc, bars).values
    is_long = mc["Direction"].astype(str).str.upper().str.startswith("L")
    counter = ((is_long & (st == "down")) | (~is_long & (st == "up")))
    ptr = mc["Date"].map(day["ptrend"]).fillna(False).astype(bool)
    tod = mc["DateTime"].dt.hour * 60 + mc["DateTime"].dt.minute
    s3 = mc[(~counter & ~ptr & (tod < 13 * 60))].copy()
    fmc = run(s3, ES, tr=3.0); omc = fmc[fmc["dt"] >= SPLIT]
    a = omc.groupby("Date")["NetPnL"].sum()
    sig = nr_orb_signals(bars, day, 4, 6)
    fnr = run(sig, ES); onr = fnr[fnr["dt"] >= SPLIT]
    b = onr.groupby("Date")["NetPnL"].sum()
    common = a.index.intersection(b.index)
    print(f"\nT6 — portfolio overlap: NR4 trades on {len(b)} days; {len(common)} shared with MC book "
          f"({len(common)/len(b)*100:.0f}%)")
    if len(common) > 20:
        r = np.corrcoef(a.loc[common], b.loc[common])[0, 1]
        print(f"  same-day P&L correlation: {r:+.2f} (n={len(common)} days)")


if __name__ == "__main__":
    main()
