"""Regime x SECOND-ENTRY timeframe sweep — S83 stage 3 (branch regime/indep).

Same pipeline as regime_second_entry_study.py (tick-driven phase machine v4 +
S61 entry engine + S61 fill sim, regime labeled at the fill tick), run on
DIFFERENT BAR TIMEFRAMES. The machine stays tick-driven — only the bar
bookkeeping (pivot bars, prior-bar break levels, signal-bar stops) changes.

Timeframes: 1, 15, 30, 60 minutes (5m = the base study, already run).
  1m  : bars resampled from ticks within the day's RTH session window
  15/30/60m : aggregated from the 5m RTH bars
1D is NOT here: the engine is day-scoped (opens NEUTRAL, EOD flat) — a daily
variant needs cross-day state + overnight holds and is built separately.

Day-scoped, EOD flat, $5 RT, 1 ES. No charts (5m base run has them).

Usage:  python scripts/regime_2e_tf_sweep.py TF_MINUTES [--limit N]
Output: data/regime/second_entries_tf<TF>_20260723.csv  (+ summary on stdout)
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, run_day  # noqa: E402

BARS = DATA / "bars" / "_continuous.parquet"
TICKD = DATA / "ticks_continuous"


def bars_1m_from_ticks(tk, t_start, t_end):
    """1-minute OHLC bars from ticks inside [t_start, t_end] (the RTH window)."""
    m = tk[(tk["DateTime"] >= t_start) & (tk["DateTime"] <= t_end)].copy()
    if m.empty:
        return None
    m = m.set_index("DateTime")
    o = m["Price"].resample("1min").ohlc().dropna()
    if len(o) < 30:
        return None
    g = o.reset_index().rename(columns={"open": "Open", "high": "High",
                                        "low": "Low", "close": "Close"})
    return g


def agg_bars(g5, tf_min):
    """Aggregate 5m bars to tf_min (15/30/60), anchored on the session open."""
    k = tf_min // 5
    n5 = len(g5)
    rows = []
    for a in range(0, n5, k):
        c = g5.iloc[a:a + k]
        rows.append((c["DateTime"].iloc[0], c["Open"].iloc[0], c["High"].max(),
                     c["Low"].min(), c["Close"].iloc[-1]))
    return pd.DataFrame(rows, columns=["DateTime", "Open", "High", "Low", "Close"])


def main():
    tf = int(sys.argv[1])
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    out = WT_ROOT / "data" / "regime" / f"second_entries_tf{tf}_20260723.csv"

    b5 = pd.read_parquet(BARS)
    b5["Date"] = b5["DateTime"].dt.date.astype(str)
    days = sorted(b5["Date"].unique())
    if limit:
        days = days[:limit]

    t0 = time.time(); rows = []; ndone = 0
    for di, dstr in enumerate(days):
        g5 = b5[b5["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
        p = TICKD / f"{dstr}.parquet"
        if len(g5) < 30 or not p.exists():
            continue
        tk = pd.read_parquet(p).sort_values("DateTime")
        if tk.empty:
            continue
        # session window = the 5m RTH bar range (bar DateTime = bar START assumed;
        # extend end by one 5m bar to cover the last bar's ticks)
        t_start = g5["DateTime"].iloc[0]
        t_end = g5["DateTime"].iloc[-1] + pd.Timedelta(minutes=5)
        if tf == 1:
            g = bars_1m_from_ticks(tk, t_start, t_end)
        elif tf in (15, 30, 60):
            g = agg_bars(g5, tf)
        else:
            raise SystemExit("tf must be 1/15/30/60")
        if g is None or len(g) < 5:
            continue
        m = tk[(tk["DateTime"] >= t_start) & (tk["DateTime"] <= t_end)]
        tP = m["Price"].values
        tbar = np.searchsorted(g["DateTime"].values, m["DateTime"].values, side="right") - 1
        if len(tP) < 100:
            continue
        H, L = g["High"].values, g["Low"].values
        try:
            transitions = phase_transitions(H, L, len(g), tP, tbar)
            for r in run_day(g, tP, tbar, transitions):
                for book in ("T1", "T2"):
                    r_, net_ = r["books"][book]
                    rows.append((dstr, r["dir"], r["cnt"], book, r["regime"],
                                 r["fb"] + 1, r["sb"] + 1, r["fill"], r["stop"],
                                 r_, net_, r["R"]))
            ndone += 1
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tk, tP, tbar; gc.collect()
        if (di + 1) % 100 == 0:
            print(f"tf{tf} [{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "dir", "count", "book", "regime",
                                     "fire_bar", "sig_bar", "fill", "stop",
                                     "R", "net", "Rpts"])
    df.to_csv(out, index=False)
    print(f"\nDONE tf{tf} {time.time()-t0:.0f}s days={ndone} rows={len(df)} -> {out}")

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    d1 = df[df["count"] == 2]
    print(f"\n== tf{tf}m SECOND ENTRIES ==  n/book={len(d1)//2}")
    for book in ["T1", "T2"]:
        d2 = d1[d1.book == book]
        if not len(d2):
            continue
        print(f"\n-- {book} --  n={len(d2)}  meanR {d2['R'].mean():+.3f}  "
              f"win {(d2['R']>0).mean()*100:.1f}%  net ${d2['net'].sum():,.0f}  "
              f"PF {pf(d2['net']):.2f}")
        t = d2.groupby(["regime", "dir"]).agg(
            n=("R", "size"), meanR=("R", "mean"),
            win=("R", lambda s: (s > 0).mean() * 100),
            net=("net", "sum"), PF=("net", pf)).round(3)
        print(t.to_string())


if __name__ == "__main__":
    main()
