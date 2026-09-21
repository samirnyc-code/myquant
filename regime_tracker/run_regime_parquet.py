#!/usr/bin/env python3
"""Run compute_mywedge() + compute_regime() on ES bars from a myquant parquet
file, resampled to N-minute bars, and export regime_data.json for charting.

Usage:
  python run_regime_parquet.py PARQUET --date 2026-05-06 [--bar-minutes 5]
                                [--lookback-days 0] [--out regime_data.json]

--lookback-days pulls in N additional prior RTH sessions (each its own
is_new_session) so the swing-structure classifier has more history to
confirm regimes on, instead of starting cold on the single target day.
"""
import sys, os, json, math, argparse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mywedge import compute_mywedge
from regime_tracker import compute_regime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parquet")
    ap.add_argument("--date", required=True, help="target session date, YYYY-MM-DD")
    ap.add_argument("--bar-minutes", type=int, default=5)
    ap.add_argument("--lookback-days", type=int, default=0)
    ap.add_argument("--tick-size", type=float, default=0.25)
    ap.add_argument("--out", default="regime_data.json")
    a = ap.parse_args()

    df = pd.read_parquet(a.parquet)
    df = df.sort_values("DateTime").reset_index(drop=True)

    target = pd.Timestamp(a.date)
    session_dates = sorted(df["DateTime"].dt.normalize().unique())
    session_dates = [d for d in session_dates if d <= target]
    if not session_dates or session_dates[-1] != target:
        sys.exit(f"no bars found for session date {a.date} in {a.parquet}")
    idx = session_dates.index(target)
    lo = max(0, idx - a.lookback_days)
    keep_dates = set(session_dates[lo:idx + 1])

    df = df[df["DateTime"].dt.normalize().isin(keep_dates)]

    rs = df.set_index("DateTime").resample(f"{a.bar_minutes}min", label="left", closed="left").agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"),
    ).dropna().reset_index()

    ts = list(rs["DateTime"])
    O = list(rs["Open"]); H = list(rs["High"]); L = list(rs["Low"]); C = list(rs["Close"])

    ins = []
    prev_date = None
    for t in ts:
        d = t.normalize()
        ins.append(d != prev_date)
        prev_date = d

    # lookback=0, warmup_floor=0 (not mywedge's own defaults of 12 / 4): this
    # only delays when compute_mywedge starts computing swing_low/swing_high at
    # all (start = max(1.5*lookback, warmup_floor)) -- it doesn't change the
    # swing/pivot logic itself, which never reads `lookback`. We only ever use
    # swing_low/swing_high here, never the wedge/signal-bar outputs, so there's
    # no fidelity tradeoff -- just pivots available from bar 1 instead of bar ~19.
    w = compute_mywedge(O, H, L, C, tick_size=a.tick_size, is_new_session=ins,
                         lookback=0, warmup_floor=0, show_w2l=True, wedge_symmetry=4, ol_sensitivity=1,
                         ctsb_ignore=True, ib_ignore=True, show_wedge_sb=True,
                         signal_bar_ibs=66.0, continue_mc=False, continue_on_gap=False)

    r = compute_regime(w.swing_low, w.swing_high, L, H, bar_dir=w.bar_dir)

    # lookback days were only for warmup context -- trim the export back down to
    # the target session so the chart shows just that day, carrying forward
    # whatever regime/majors were already established from the lookback bars
    trim = next(i for i, t in enumerate(ts) if t.normalize() == target) if a.lookback_days else 0
    ts, O, H, L, C = ts[trim:], O[trim:], H[trim:], L[trim:], C[trim:]
    regime = r.regime[trim:]
    pivot_lows = [(i - trim, p, m) for i, p, m in r.pivot_lows if i >= trim]
    pivot_highs = [(i - trim, p, m) for i, p, m in r.pivot_highs if i >= trim]

    n = len(ts)
    segments = []
    start, cur = 0, regime[0]
    for i in range(1, n):
        if regime[i] != cur:
            segments.append({"start": start, "end": i, "regime": cur})
            start, cur = i, regime[i]
    segments.append({"start": start, "end": n, "regime": cur})

    data = {
        "bars": [{"t": ts[i].isoformat(), "o": O[i], "h": H[i], "l": L[i], "c": C[i]} for i in range(n)],
        "regime": regime,
        "segments": segments,
        "pivot_lows": [{"i": i, "price": p, "major": m} for i, p, m in pivot_lows],
        "pivot_highs": [{"i": i, "price": p, "major": m} for i, p, m in pivot_highs],
        "events": [{"i": i - trim, "kind": k, "dir": dr, "level": lv}
                   for i, k, dr, lv in r.events if i >= trim],
    }
    with open(a.out, "w") as f:
        json.dump(data, f)

    counts = {}
    for lbl in regime:
        counts[lbl] = counts.get(lbl, 0) + 1
    print(f"{n} bars ({a.bar_minutes}min, {len(keep_dates)} session(s), {a.lookback_days} lookback day(s)) -> {a.out}")
    print(", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
