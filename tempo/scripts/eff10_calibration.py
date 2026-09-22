"""eff10_calibration.py — thresholds for the multi-bar EXPAND/GRIND redefinition (S116-tempo).

User complaint (2026-09-11): a 60-pt one-way run lit almost no EXPAND cells. Cause:
per-bar state rules demand a single bar be fast+big+efficient, but on a tick chart
amplitude is flat by construction (tod table: p50 4.00-4.25 every bucket) and trends
are multi-bar. New definition: 10-bar displacement efficiency
    eff10 = |close_t - close_{t-10}| / sum(range over the 10 bars)
plus mean tempo pctile over the window. This script reports the eff10 distribution
overall AND during genuine trend legs (top-decile 10-bar net moves) vs the rest, so
the EXPAND gate is picked from data, not taste. Display thresholds only — the states
remain descriptive.

    python tempo/scripts/eff10_calibration.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tempo" / "scripts"))
from climax_at_high_test import rolling_bucket_pct  # noqa: E402

BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs"
W = 10


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, "tempo"] = np.nan
    print("computing tempo percentiles...")
    df["tpct"] = rolling_bucket_pct(df)

    gb = df.groupby("date")
    net = (gb["close"].shift(0) - gb["close"].shift(W)).abs()
    sumrng = gb["range"].transform(lambda s: s.rolling(W).sum())
    df["eff10"] = np.where(sumrng > 0, net / sumrng, np.nan)
    df["t10"] = gb["tpct"].transform(lambda s: s.rolling(W).mean())
    adr = gb["high"].max().sub(gb["low"].min()).shift(1).rolling(8).mean()
    df["net10_adr"] = net / df["date"].map(adr)

    d = df.dropna(subset=["eff10", "t10", "net10_adr"])
    trend = d[d["net10_adr"] >= d["net10_adr"].quantile(0.90)]   # genuine 10-bar runs
    rest = d[d["net10_adr"] < d["net10_adr"].quantile(0.90)]

    lines = []
    q = [0.25, 0.5, 0.75, 0.85, 0.95]
    lines.append("eff10 quantiles  ALL:   " + "  ".join(f"q{int(x*100)}={d['eff10'].quantile(x):.3f}" for x in q))
    lines.append("eff10 quantiles  TREND: " + "  ".join(f"q{int(x*100)}={trend['eff10'].quantile(x):.3f}" for x in q))
    lines.append("eff10 quantiles  REST:  " + "  ".join(f"q{int(x*100)}={rest['eff10'].quantile(x):.3f}" for x in q))
    lines.append(f"t10 mean   TREND: {trend['t10'].mean():.1f}   REST: {rest['t10'].mean():.1f}")
    for e_hi in [0.30, 0.35, 0.40, 0.45, 0.50]:
        for t_hi in [50, 55, 60]:
            tag = d[(d["eff10"] >= e_hi) & (d["t10"] >= t_hi)]
            cover = (trend["eff10"] >= e_hi) & (trend["t10"] >= t_hi)
            lines.append(f"  gate eff10>={e_hi:.2f} & t10>={t_hi}: tags {len(tag)/len(d):5.1%} of all bars, "
                         f"catches {cover.mean():5.1%} of trend-leg bars")
    txt = "\n".join(lines)
    (OUT / f"eff10_calibration_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
