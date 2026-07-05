"""Walk-forward search, menu 2 — structurally different entries (S55, track A).

Same discipline as wf_search.py: dev = 2021-06-18..2022-06-17, OOS = rest, all
configs reported. Exits standardized (ATR stop, target grid incl. none/EOD-hold),
realistic exec. Menu pre-specified before results:

  PDHL   — prior-day high/low acceptance: first 5M close beyond PDH -> Long
           (PDL -> Short). Multi-day structure, not intraday noise.
  PMDRIFT— 12:30 CT check: session net move > +/-0.25 x prior ADR14 -> enter
           WITH the day's direction (afternoon continuation).
  NR7ORB — prior day = narrowest range of last 7 -> trade today's 30-min ORB
           break direction (volatility compression -> expansion).
  DON15  — Donchian M20 on 15M bars (slower TF than menu 1).
  GAPGO  — open gap vs prior close > 0.3 x prior ADR14 -> first 5M close in gap
           direction beyond the first bar's range -> with-gap entry.

Targets: {1, 2, 3, 99}R  (99R = no target: stop + EOD only).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import massive
from simulation_engine import simulate_trades, INSTRUMENTS

BARS5 = ROOT / "data" / "bars" / "_continuous.parquet"
BARS15 = ROOT / "data" / "bars" / "_continuous_15m.parquet"
SPLIT = pd.Timestamp("2022-06-18")
TARGETS = [1.0, 2.0, 3.0, 99.0]
RNG = np.random.default_rng(42)


def day_table(bars):
    d = bars.groupby("_d").agg(o=("Open", "first"), h=("High", "max"),
                               l=("Low", "min"), c=("Close", "last"))
    d["rng"] = d["h"] - d["l"]
    d["adr14"] = d["rng"].rolling(14, min_periods=5).mean().shift(1)   # causal
    d["nr7"] = (d["rng"] == d["rng"].rolling(7).min()).shift(1).fillna(False)
    for col in ("h", "l", "c"):
        d[f"p{col}"] = d[col].shift(1)
    return d


def atr20(g):
    return (g["High"] - g["Low"]).rolling(20, min_periods=5).mean().shift(1)


def _emit(g, i, direction, stop):
    if i + 1 >= len(g): return None
    a = g["atr"].iloc[i]
    if not np.isfinite(a) or a <= 0: return None
    return (g["DateTime"].iloc[i + 1], direction, float(g["Close"].iloc[i]), float(stop))


def strat_pdhl(g, drow):
    out, dl, ds = [], False, False
    if not np.isfinite(drow.get("ph", np.nan)): return out
    for i in range(2, len(g) - 1):
        c, a = g["Close"].iloc[i], g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if not dl and c > drow["ph"]:
            s = _emit(g, i, "Long", c - a); dl = True
            if s: out.append(s)
        elif not ds and c < drow["pl"]:
            s = _emit(g, i, "Short", c + a); ds = True
            if s: out.append(s)
        if dl and ds: break
    return out


def strat_pmdrift(g, drow):
    adr = drow.get("adr14", np.nan)
    if not np.isfinite(adr): return []
    tod = g["DateTime"].dt.hour * 60 + g["DateTime"].dt.minute
    idx = np.where(tod >= 12 * 60 + 30)[0]
    if not len(idx): return []
    i = int(idx[0])
    mv = g["Close"].iloc[i] - g["Open"].iloc[0]
    a = g["atr"].iloc[i]
    if not np.isfinite(a) or a <= 0: return []
    if mv > 0.25 * adr:
        s = _emit(g, i, "Long", g["Close"].iloc[i] - a); return [s] if s else []
    if mv < -0.25 * adr:
        s = _emit(g, i, "Short", g["Close"].iloc[i] + a); return [s] if s else []
    return []


def strat_nr7orb(g, drow, K=6):
    if not drow.get("nr7", False) or len(g) < K + 2: return []
    orh = g["High"].iloc[:K].max(); orl = g["Low"].iloc[:K].min()
    for i in range(K, len(g) - 1):
        c, a = g["Close"].iloc[i], g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if c > orh:
            s = _emit(g, i, "Long", c - a); return [s] if s else []
        if c < orl:
            s = _emit(g, i, "Short", c + a); return [s] if s else []
    return []


def strat_don15(g, M=20):
    hh = g["High"].rolling(M).max().shift(1); ll = g["Low"].rolling(M).min().shift(1)
    out, dl, ds = [], False, False
    for i in range(M, len(g) - 1):
        c, a = g["Close"].iloc[i], g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if not dl and c > hh.iloc[i]:
            s = _emit(g, i, "Long", c - a); dl = True
            if s: out.append(s)
        elif not ds and c < ll.iloc[i]:
            s = _emit(g, i, "Short", c + a); ds = True
            if s: out.append(s)
        if dl and ds: break
    return out


def strat_gapgo(g, drow):
    pc, adr = drow.get("pc", np.nan), drow.get("adr14", np.nan)
    if not (np.isfinite(pc) and np.isfinite(adr)): return []
    gap = g["Open"].iloc[0] - pc
    if abs(gap) < 0.3 * adr: return []
    b1h, b1l = g["High"].iloc[0], g["Low"].iloc[0]
    for i in range(1, min(len(g) - 1, 12)):
        c, a = g["Close"].iloc[i], g["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0: continue
        if gap > 0 and c > b1h:
            s = _emit(g, i, "Long", c - a); return [s] if s else []
        if gap < 0 and c < b1l:
            s = _emit(g, i, "Short", c + a); return [s] if s else []
    return []


def build(bars, dt, fn, needs_day):
    rows = []
    for d, g in bars.groupby("_d"):
        g = g.reset_index(drop=True)
        drow = dt.loc[d].to_dict() if (needs_day and d in dt.index) else {}
        for s in (fn(g, drow) if needs_day else fn(g)):
            if s: rows.append(dict(DateTime=s[0], Direction=s[1], SignalPrice=s[2],
                                   StopPrice=s[3], Date=d))
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("DateTime").reset_index(drop=True)
    df["SignalNum"] = np.arange(1, len(df) + 1); df["SignalType"] = "raw"; df["BarNum"] = 0
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
    b5 = pd.read_parquet(BARS5).drop(columns=["Contract"], errors="ignore")
    b5["DateTime"] = pd.to_datetime(b5["DateTime"]); b5["_d"] = b5["DateTime"].dt.date
    b5["atr"] = b5.groupby("_d", group_keys=False).apply(atr20)
    b15 = pd.read_parquet(BARS15).drop(columns=["Contract"], errors="ignore")
    b15["DateTime"] = pd.to_datetime(b15["DateTime"]); b15["_d"] = b15["DateTime"].dt.date
    b15["atr"] = b15.groupby("_d", group_keys=False).apply(atr20)
    dt5 = day_table(b5)

    dates = sorted(b5["_d"].unique())
    print(f"loading ticks {len(dates)} days…", flush=True)
    tbd = {}
    for dd in dates:
        t = massive.load_continuous_ticks(dd)
        if not t.empty: tbd[dd] = t
    bbd = {dd: gg.reset_index(drop=True) for dd, gg in b5.groupby("_d")}
    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1,
              tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
              commission=4.36, pb_round="nearest")

    menu = {
        "PDHL":    build(b5, dt5, strat_pdhl, True),
        "PMDRIFT": build(b5, dt5, strat_pmdrift, True),
        "NR7ORB":  build(b5, dt5, strat_nr7orb, True),
        "DON15":   build(b15, dt5, strat_don15, False),
        "GAPGO":   build(b5, dt5, strat_gapgo, True),
    }
    dev_rows, oos_rows = [], []
    for name, sig in menu.items():
        if sig.empty:
            print(f"{name}: no signals"); continue
        for tr in TARGETS:
            cfg = f"{name}@{tr:g}R" if tr < 99 else f"{name}@EOD"
            raw = simulate_trades(signals=sig, ticks_by_date=tbd, bars_by_date=bbd,
                                  target_r=tr, ratchet_r=0.0, **bp)
            f = raw[raw["Filled"] == True].copy()
            f["dt"] = pd.to_datetime(f["Date"])
            dev_rows.append((cfg, metrics(f[f["dt"] < SPLIT])))
            oos_rows.append((cfg, metrics(f[f["dt"] >= SPLIT])))

    def show(rows, title):
        print(f"\n{'='*92}\n{title}\n{'='*92}")
        print(f"{'config':14s} {'n':>5s} {'netR':>8s} {'95% CI':>18s} {'PF':>6s} {'net$':>12s}")
        for name, m in rows:
            if not m: print(f"{name:14s}   (thin)"); continue
            print(f"{name:14s} {m['n']:5d} {m['netR']:+8.3f} "
                  f"[{m['lo']:+.3f},{m['hi']:+.3f}] {m['pf']:6.2f} {m['net']:+12,.0f}")

    show(dev_rows, "DEV — 2021-06-18 .. 2022-06-17")
    show(oos_rows, "OOS — 2022-06-18 .. 2026-07-02  (VERDICT; bar: +0.08R, PF1.3, lo>+0.04)")


if __name__ == "__main__":
    main()
