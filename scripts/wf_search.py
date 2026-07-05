"""Walk-forward system search on raw ES bars (S55, from-scratch, no MC signals).

Discipline (user-specified):
  - DEVELOP/SELECT only on the FIRST 12 MONTHS of data (2021-06-18 .. 2022-06-17).
  - WALK FORWARD, untouched, on 2022-06-18 .. 2026-07-02 (~4y OOS).
  - Pre-specified strategy menu + small grids, fixed BEFORE looking at results.
  - Report EVERY config's OOS, not just the dev winner. OOS is the only verdict.
  - Bar to clear (per prior analysis): net >= +0.08R, PF >= 1.3, OOS lower-CI > +0.04R.

Design: each strategy decides DIRECTION + TIMING only. Exits are STANDARDIZED for
comparability — entry next-bar-open, stop = entry -/+ ATR_MULT * ATR20(5m), target 3R,
flat at session close, realistic execution (slip 1/1, comm 4.36). One trade/session/dir.

Timeframe: 5M (primary). Menu: Opening-Range Breakout, Donchian breakout (momentum),
VWAP-band fade (mean-reversion control).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import massive
from simulation_engine import simulate_trades, INSTRUMENTS

BARS = ROOT / "data" / "bars" / "_continuous.parquet"
SPLIT = pd.Timestamp("2022-06-18")
ATR_MULT = 1.0
TARGETS = [1.0, 1.5, 2.0, 3.0]      # exit is SEARCHED on dev, not assumed
RNG = np.random.default_rng(42)


def atr20(g):
    tr = (g["High"] - g["Low"])
    return tr.rolling(20, min_periods=5).mean().shift(1)   # causal


# ── strategy signal generators: return (DateTime, Direction, SignalPrice, StopPrice) ──
def _emit(g, i, direction, stop):
    """Signal decided at bar i close -> enter next bar (i+1). Needs i+1 to exist."""
    if i + 1 >= len(g):
        return None
    a = g["atr"].iloc[i]
    if not np.isfinite(a) or a <= 0:
        return None
    dt_next = g["DateTime"].iloc[i + 1]           # engine fills market at first tick >= this
    ref = float(g["Close"].iloc[i])
    return (dt_next, direction, ref, float(stop))


def strat_orb(g, K):
    """Opening-Range Breakout: first close beyond the first-K-bar range."""
    if len(g) < K + 2: return []
    orh = g["High"].iloc[:K].max(); orl = g["Low"].iloc[:K].min()
    out = []
    for i in range(K, len(g) - 1):
        c = g["Close"].iloc[i]; a = g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if c > orh:
            s = _emit(g, i, "Long", g["Close"].iloc[i] - ATR_MULT * a);
            if s: out.append(s)
            break
        if c < orl:
            s = _emit(g, i, "Short", g["Close"].iloc[i] + ATR_MULT * a)
            if s: out.append(s)
            break
    return out


def strat_donchian(g, M):
    """Momentum: close breaks the prior-M-bar high/low. First break/session/dir."""
    hh = g["High"].rolling(M).max().shift(1)
    ll = g["Low"].rolling(M).min().shift(1)
    out = []; done_l = done_s = False
    for i in range(M, len(g) - 1):
        c = g["Close"].iloc[i]; a = g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if not done_l and c > hh.iloc[i]:
            s = _emit(g, i, "Long", c - ATR_MULT * a); done_l = True
            if s: out.append(s)
        elif not done_s and c < ll.iloc[i]:
            s = _emit(g, i, "Short", c + ATR_MULT * a); done_s = True
            if s: out.append(s)
        if done_l and done_s: break
    return out


def strat_vwap_fade(g, k):
    """Mean-reversion control: close beyond session VWAP +/- k*sigma -> fade."""
    tp = (g["High"] + g["Low"] + g["Close"]) / 3
    cum_v = g["Volume"].cumsum().replace(0, np.nan)
    vwap = (tp * g["Volume"]).cumsum() / cum_v
    dev = (tp - vwap)
    sig = dev.expanding(min_periods=6).std()
    out = []; done_l = done_s = False
    for i in range(6, len(g) - 1):
        c = g["Close"].iloc[i]; a = g["atr"].iloc[i]; s_ = sig.iloc[i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(s_) or s_ <= 0: continue
        if not done_l and c < vwap.iloc[i] - k * s_:
            r = _emit(g, i, "Long", c - ATR_MULT * a); done_l = True
            if r: out.append(r)
        elif not done_s and c > vwap.iloc[i] + k * s_:
            r = _emit(g, i, "Short", c + ATR_MULT * a); done_s = True
            if r: out.append(r)
        if done_l and done_s: break
    return out


MENU = {
    "ORB_K3":  lambda g: strat_orb(g, 3),
    "ORB_K6":  lambda g: strat_orb(g, 6),
    "DON_M20": lambda g: strat_donchian(g, 20),
    "DON_M40": lambda g: strat_donchian(g, 40),
    "VWAP_k1.5": lambda g: strat_vwap_fade(g, 1.5),
    "VWAP_k2.0": lambda g: strat_vwap_fade(g, 2.0),
}


def build_signals(bars, fn):
    rows = []
    for d, g in bars.groupby("_d"):
        g = g.reset_index(drop=True)
        for (dt, dr, sp, st) in fn(g):
            rows.append(dict(DateTime=dt, Direction=dr, SignalPrice=sp, StopPrice=st, Date=d))
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("DateTime").reset_index(drop=True)
    df["SignalNum"] = np.arange(1, len(df) + 1)
    df["SignalType"] = "raw"; df["BarNum"] = 0
    return df


def metrics(f):
    if len(f) < 20: return None
    nr = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    g = f.loc[f.NetPnL > 0, "NetPnL"].sum(); l = f.loc[f.NetPnL < 0, "NetPnL"].sum()
    m = [RNG.choice(nr, len(nr)).mean() for _ in range(3000)]
    return dict(n=len(f), netR=float(nr.mean()), lo=float(np.percentile(m, 2.5)),
                hi=float(np.percentile(m, 97.5)), pf=float(g / abs(l)) if l else 9.99,
                net=float(f.NetPnL.sum()))


def main():
    bars = pd.read_parquet(BARS).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"]); bars["_d"] = bars["DateTime"].dt.date
    bars["atr"] = bars.groupby("_d", group_keys=False).apply(lambda g: atr20(g))

    # ticks (all, once)
    dates = sorted(bars["_d"].unique())
    print(f"loading ticks {len(dates)} days…", flush=True)
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: gg.reset_index(drop=True) for dd, gg in bars.groupby("_d")}
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1, tick_value=INSTRUMENTS["ES"]["tick_value"],
              contracts=1, commission=4.36, pb_round="nearest")

    dev_rows, oos_rows = [], []
    for name, fn in MENU.items():
        sig = build_signals(bars, fn)
        if sig.empty:
            print(f"{name}: no signals"); continue
        for tr in TARGETS:                       # exit grid searched on dev
            cfg = f"{name}@{tr:g}R"
            raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd,
                                  target_r=tr, ratchet_r=0.0, **bp)
            f = raw[raw["Filled"] == True].copy()
            f["dt"] = pd.to_datetime(f["Date"])
            dev = f[f["dt"] < SPLIT]; oos = f[f["dt"] >= SPLIT]
            dev_rows.append((cfg, metrics(dev))); oos_rows.append((cfg, metrics(oos)))

    def show(rows, title):
        print(f"\n{'='*92}\n{title}\n{'='*92}")
        print(f"{'config':12s} {'n':>5s} {'netR':>8s} {'95% CI':>18s} {'PF':>6s} {'net$':>12s}")
        for name, m in rows:
            if not m: print(f"{name:12s}   (thin)"); continue
            print(f"{name:12s} {m['n']:5d} {m['netR']:+8.3f} "
                  f"[{m['lo']:+.3f},{m['hi']:+.3f}] {m['pf']:6.2f} {m['net']:+12,.0f}")

    show(dev_rows, "DEVELOPMENT — first 12 months (2021-06-18 .. 2022-06-17)")
    show(oos_rows, "WALK-FORWARD OOS — 2022-06-18 .. 2026-07-02  (THE VERDICT)")

    # dev selection (pre-specified rule: highest dev netR among PF>1.15, n>=40)
    elig = [(n, m) for n, m in dev_rows if m and m["pf"] > 1.15 and m["n"] >= 40]
    if elig:
        pick = max(elig, key=lambda x: x[1]["netR"])[0]
        om = dict(oos_rows)[pick]
        print(f"\nDEV-SELECTED: {pick}  ->  OOS: "
              + (f"netR={om['netR']:+.3f} [{om['lo']:+.3f},{om['hi']:+.3f}] PF={om['pf']:.2f} "
                 f"${om['net']:+,.0f}  (bar: +0.08R / PF1.3 / lo>+0.04)" if om else "thin"))
    else:
        print("\nNo dev config met the minimum selection sanity (PF>1.15, n>=40).")


if __name__ == "__main__":
    main()
