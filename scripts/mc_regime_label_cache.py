"""mc_regime_label_cache.py — batch per-bar regime labels for all MC signal days.

Heavy step (tick replay of the fast-flip phase machine over ~1,850 days). Runs
once, caches to data/regime/mc_signal_day_regime.parquet so the ablation study
(mc_regime_filter_study.py) is cheap and re-runnable. Resumable: skips days
already in the cache.

Output columns: Date, bar, bar_open (bar label), bar_close (label+5min),
regime {neutral,bull,bear}.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive  # noqa: E402
from bar_analysis import parse_signals  # noqa: E402
from regime_label_engine import label_day  # noqa: E402

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT = _ROOT / "data" / "regime" / "mc_signal_day_regime.parquet"


def _log(m):
    sys.stdout.buffer.write((str(m) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def main():
    sig = parse_signals(_SIG_TXT.read_text())
    dates = sorted(pd.to_datetime(sig["Date"]).dt.date.unique())
    _log(f"{len(dates)} signal days ({dates[0]} -> {dates[-1]})")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars["_d"] = bars["DateTime"].dt.date
    bars_by_date = {d: g.sort_values("DateTime").reset_index(drop=True)
                    for d, g in bars.groupby("_d")}

    done = set()
    prior = []
    if _OUT.exists():
        prior_df = pd.read_parquet(_OUT)
        done = set(pd.to_datetime(prior_df["Date"]).dt.date.unique())
        prior = [prior_df]
        _log(f"resume: {len(done)} days already cached")

    out = []
    t0 = time.time()
    for i, d in enumerate(dates):
        if d in done:
            continue
        g = bars_by_date.get(d)
        if g is None or len(g) < 3:
            continue
        tk = massive.load_continuous_ticks(d)
        if tk.empty:
            continue
        lab = label_day(g, tk)
        lab.insert(0, "Date", str(d))
        lab = lab.rename(columns={"DateTime": "bar_open"})
        lab["bar_close"] = lab["bar_open"] + pd.Timedelta(minutes=5)
        out.append(lab[["Date", "bar", "bar_open", "bar_close", "regime"]])
        if (i + 1) % 100 == 0:
            el = time.time() - t0
            _log(f"  …{i + 1}/{len(dates)} days  ({el:.0f}s, {el / max(len(out),1):.2f}s/day)")
            # checkpoint
            pd.concat(prior + out, ignore_index=True).to_parquet(_OUT)

    allrows = pd.concat(prior + out, ignore_index=True) if out else (prior[0] if prior else None)
    if allrows is not None:
        allrows.to_parquet(_OUT)
        _log(f"WROTE {_OUT}  ({len(allrows)} bar-rows, "
             f"{allrows['Date'].nunique()} days, {time.time() - t0:.0f}s)")
        _log("regime bar-share: " + str(
            (allrows["regime"].value_counts(normalize=True) * 100).round(1).to_dict()))


if __name__ == "__main__":
    main()
