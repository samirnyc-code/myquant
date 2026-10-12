"""library_chart_build.py — build one day's ETH chart (bars + EMA20 + regime
panel + pivots) as JSON, for the Trade Playbook's "Library" tab. Supports
both N-tick bars (e.g. 1000t/2000t/4000t) and time bars (e.g. 5m/15m).

Reuses, unmodified:
  - tickdata.py (main repo)            — THE canonical ES tick source (ETH trove)
  - ticks_to_2000t.py::bars()          — N-tick OHLCV bar builder (main repo)
  - regime_second_entry_study.py::phase_transitions() — the NT<->Python-reconciled
    regime phase machine (this worktree, branch regime/indep)

Two bar-building paths, each with its own exact tick->bar mapping:
  - Tick bars: contiguous by construction, so tick->bar is pure index
    division (tbar = i // size) — exact, not approximate.
  - Time bars: ticks fall into a bar by TIMESTAMP, so tick->bar needs a
    bisect against each bar's start time (same approach as
    chartsim_realtick_day.py's 5-min resample, generalized to any --span).

  python scripts/library_chart_build.py 2026-10-07 --bar-type 2000t
  python scripts/library_chart_build.py 2026-10-07 --bar-type 5m
"""
from __future__ import annotations
import argparse
import json
import sys
from bisect import bisect_right
from pathlib import Path

import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent          # myquant-regime (this worktree)
MAIN = Path(r"c:/Users/Admin/myquant")                # main worktree — canonical data + bar builder

sys.path.insert(0, str(MAIN))
sys.path.insert(0, str(MAIN / "scripts"))
sys.path.insert(0, str(WT / "scripts"))
import tickdata                               # noqa: E402  (main repo — canonical tick access)
from ticks_to_2000t import bars as tick_bars  # noqa: E402  (main repo — N-tick OHLCV builder)
from regime_second_entry_study import phase_transitions  # noqa: E402  (this worktree)

OUT_DEFAULT = WT / "data" / "annotations" / "library"


def parse_bar_type(bar_type: str) -> tuple[str, int]:
    """'2000t' -> ('tick', 2000); '5m' -> ('time', 5)."""
    bar_type = bar_type.strip().lower()
    if bar_type.endswith("t"):
        return "tick", int(bar_type[:-1])
    if bar_type.endswith("m"):
        return "time", int(bar_type[:-1])
    raise ValueError(f"bar_type must end in 't' (tick count) or 'm' (minutes): {bar_type!r}")


def build_tick_bars(df: pd.DataFrame, size: int) -> pd.DataFrame:
    """OHLCV + tick->bar mapping arrays, tick-bar path (exact index division)."""
    b = tick_bars(df, size)
    tbar = (np.arange(len(df)) // size).astype(int)
    return b, df["Price"].values.astype(float), tbar


def build_time_bars(df: pd.DataFrame, span_min: int) -> pd.DataFrame:
    """OHLCV + tick->bar mapping arrays, time-bar path (resample + bisect)."""
    t = df.set_index("DateTime")
    freq = f"{span_min}min"
    o = t["Price"].resample(freq, label="left", closed="left").first()
    h = t["Price"].resample(freq, label="left", closed="left").max()
    l = t["Price"].resample(freq, label="left", closed="left").min()
    c = t["Price"].resample(freq, label="left", closed="left").last()
    vol = t["Volume"].resample(freq, label="left", closed="left").sum()
    ticks = t["Price"].resample(freq, label="left", closed="left").count()
    bb = pd.DataFrame({"start": o.index, "open": o, "high": h, "low": l, "close": c, "vol": vol, "ticks": ticks})
    bb["close"] = bb["close"].ffill()
    for col in ("open", "high", "low"):
        bb[col] = bb[col].fillna(bb["close"])
    bb = bb[bb["ticks"] > 0].reset_index(drop=True)  # drop empty bars (no trades that interval)

    b0 = bb["start"].iloc[0]
    span_s = span_min * 60
    tbar = ((df["DateTime"] - b0).dt.total_seconds() // span_s).astype(int).values
    # tbar can run past the last real bar if trailing empty intervals were
    # dropped above — clip to the valid range so downstream indexing is safe.
    tbar = np.clip(tbar, 0, len(bb) - 1)
    return bb, df["Price"].values.astype(float), tbar


def build(date: str, bar_type: str = "2000t", warmup_days: int = 10) -> dict:
    kind, n_param = parse_bar_type(bar_type)
    df = tickdata.load_eth(date)

    if kind == "tick":
        b, tP, tbar = build_tick_bars(df, n_param)
    else:
        b, tP, tbar = build_time_bars(df, n_param)
    n = len(b)
    H, L, C, O = b["high"].values, b["low"].values, b["close"].values, b["open"].values

    trace: dict = {}
    trans = phase_transitions(H, L, n, tP, tbar, trace=trace)
    tr_ix = [x for (x, _) in trans]   # tick indices, NOT bar indices
    tr_md = [m for (_, m) in trans]
    seg = []
    for i in range(n):
        z = int(np.searchsorted(tbar, i, "right"))  # tick count through bar i
        mode = tr_md[bisect_right(tr_ix, z - 1) - 1] if z else "NEUTRAL"
        if seg and seg[-1]["mode"] == mode:
            seg[-1]["to"] = i
        else:
            seg.append({"from": i, "to": i, "mode": mode})

    pivots = [{"bar": int(p["bar"]), "side": p["side"], "tag": p["tag"],
               "lab": (p.get("majlab") or p.get("disp") or p["tag"]).upper(),
               "major": p.get("major") is not None}
              for p in trace.get("piv", []) if 0 <= p["bar"] < n]

    # EMA20 seeded with prior ETH days' bars (same bar_type) so bar 0 isn't a
    # cold start.
    avail = [d for d in tickdata.available("eth") if d <= date]
    hist_days = avail[-(warmup_days + 1):]
    closes: list[float] = []
    for d in hist_days:
        hdf = tickdata.load_eth(d)
        hb, _, _ = (build_tick_bars(hdf, n_param) if kind == "tick" else build_time_bars(hdf, n_param))
        closes += list(hb["close"].values)
    ema_full = pd.Series(closes).ewm(span=20, adjust=False).mean().values
    ema = ema_full[-n:]

    # Output timestamps are second-precision ("%Y-%m-%dT%H:%M:%S"), but two
    # bars' true opens can be sub-second apart (tick mode) and collide once
    # truncated — dedupe MUST run at the same precision as the output, not
    # full microsecond precision. Time bars are already unique by construction
    # (resample buckets), so this is a no-op safety net for that path.
    starts = b["start"].dt.floor("s")
    for i in range(1, n):
        if starts.iloc[i] <= starts.iloc[i - 1]:
            starts.iloc[i] = starts.iloc[i - 1] + pd.Timedelta(seconds=1)

    bars_out = [
        {"i": i, "t": pd.Timestamp(starts.iloc[i]).strftime("%Y-%m-%dT%H:%M:%S"),
         "o": round(float(O[i]), 2), "h": round(float(H[i]), 2),
         "l": round(float(L[i]), 2), "c": round(float(C[i]), 2),
         "ema20": round(float(ema[i]), 2), "vol": int(b["vol"].values[i])}
        for i in range(n)
    ]

    # Prior session's RTH high/low/close — for the HOY/LOY/COY RTH reference
    # lines (High/Low/Close Of Yesterday's regular session). RTH trove, not
    # ETH: these are the levels traders actually reference, not the overnight
    # extremes. "Yesterday" = the most recent RTH day strictly before `date`.
    rth_days = [d for d in tickdata.available("rth") if d < date]
    prior_rth = None
    if rth_days:
        prior_date = rth_days[-1]
        rp = tickdata.load_rth(prior_date)
        prior_rth = {
            "date": prior_date,
            "high": round(float(rp["Price"].max()), 2),
            "low": round(float(rp["Price"].min()), 2),
            "close": round(float(rp["Price"].iloc[-1]), 2),
        }

    return {
        "date": date, "instrument": "ES", "barType": bar_type, "session": "ETH",
        "n_bars": n, "bars": bars_out, "regime": seg, "pivots": pivots,
        "prior_rth": prior_rth,
        "source": "real-ticks", "built_from": "tickdata.load_eth + phase_transitions",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--bar-type", default="2000t", help="e.g. 1000t, 2000t, 4000t, 5m, 15m")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    rec = build(a.date, a.bar_type)
    out_dir = a.out or OUT_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{a.date}_ES_{a.bar_type}_ETH.json"
    out_path.write_text(json.dumps(rec))
    print(f"{a.date} [{a.bar_type}]: {rec['n_bars']} bars, {len(rec['pivots'])} pivots, "
          f"{len(rec['regime'])} regime segments -> {out_path}")


if __name__ == "__main__":
    main()
