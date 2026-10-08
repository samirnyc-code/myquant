"""library_chart_build.py — build one day's N-tick ETH chart (bars + EMA20 + regime
panel + pivots) as JSON, for the Trade Playbook's "Library" tab.

Reuses, unmodified:
  - tickdata.py (main repo)            — THE canonical ES tick source (ETH trove)
  - ticks_to_2000t.py::bars()          — N-tick OHLCV bar builder (main repo)
  - regime_second_entry_study.py::phase_transitions() — the NT<->Python-reconciled
    regime phase machine (this worktree, branch regime/indep)

Ticks map to tick-bars by pure index division (tbar = i // size), unlike
chartsim_realtick_day.py's 5-min resample which needs a time-bisect — N-tick
bars are contiguous by construction, so this is exact, not approximate.

  python scripts/library_chart_build.py 2026-10-07 [--size 2000] [--out PATH]
"""
from __future__ import annotations
import argparse
import json
import sys
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


def build(date: str, size: int = 2000, warmup_days: int = 10) -> dict:
    df = tickdata.load_eth(date)
    b = tick_bars(df, size)
    n = len(b)
    H, L, C, O = b["high"].values, b["low"].values, b["close"].values, b["open"].values

    # ticks -> bar index is exact index division (bars are built the same way)
    tP = df["Price"].values.astype(float)
    tbar = (np.arange(len(df)) // size).astype(int)

    trace: dict = {}
    trans = phase_transitions(H, L, n, tP, tbar, trace=trace)
    tr_ix = [x for (x, _) in trans]   # tick indices, NOT bar indices
    tr_md = [m for (_, m) in trans]
    from bisect import bisect_right
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

    # EMA20 seeded with prior ETH days' tick-bars so bar 0 isn't a cold start
    avail = [d for d in tickdata.available("eth") if d <= date]
    hist_days = avail[-(warmup_days + 1):]
    closes: list[float] = []
    for d in hist_days:
        hb = tick_bars(tickdata.load_eth(d), size)
        closes += list(hb["close"].values)
    ema_full = pd.Series(closes).ewm(span=20, adjust=False).mean().values
    ema = ema_full[-n:]

    # Output timestamps are second-precision ("%Y-%m-%dT%H:%M:%S"), but two
    # bars' true opens can be sub-second apart (e.g. 14:59:59.041 vs .578) and
    # collide once truncated — dedupe MUST run at the same precision as the
    # output, not full microsecond precision (that sees them as distinct and
    # nudges nothing, leaving the truncated strings still equal). The chart's
    # x-axis requires strictly increasing time. Display-only; OHLC untouched.
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

    return {
        "date": date, "instrument": "ES", "barType": f"{size}t", "session": "ETH",
        "n_bars": n, "bars": bars_out, "regime": seg, "pivots": pivots,
        "source": "real-ticks", "built_from": "tickdata.load_eth + phase_transitions",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--size", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    rec = build(a.date, a.size)
    out_dir = a.out or OUT_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{a.date}_ES_{a.size}t_ETH.json"
    out_path.write_text(json.dumps(rec))
    print(f"{a.date}: {rec['n_bars']} bars, {len(rec['pivots'])} pivots, "
          f"{len(rec['regime'])} regime segments -> {out_path}")


if __name__ == "__main__":
    main()
