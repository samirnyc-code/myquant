"""regime_events_24h.py — robustness rerun of the Grimes event tests on TRUE 24h daily bars.

The primary run (regime_events.py) used RTH-only daily bars: overnight moves fold into the
next session's open and forward returns are RTH-close-to-RTH-close, which understates ES
drift (most of which is overnight) and distorts TR/ATR vs Grimes's full-day data.
This rerun builds daily bars from data/bars/_continuous_1m_24h.parquet grouped by CME
trading day (17:00 CT session start -> next 16:00 CT), then runs the same event detectors,
scoring, and aggregated nulls.

Run:  .venv/Scripts/python.exe scripts/regime_events_24h.py
Out:  data/regime/events24h_gate_<tag>.csv (+ console table)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import regime_events as re_
import regime_validate as rvd

OUT = ROOT / "data" / "regime"
BARS_24H = ROOT / "data" / "bars" / "_continuous_1m_24h.parquet"


def daily_24h_bars() -> pd.DataFrame:
    m1 = pd.read_parquet(BARS_24H)
    m1["DateTime"] = pd.to_datetime(m1["DateTime"])
    m1 = m1.sort_values("DateTime")
    # CME trading day: 17:00 CT belongs to the NEXT calendar day's session
    tday = (m1["DateTime"] + pd.Timedelta(hours=7)).dt.normalize()
    g = m1.groupby(tday).agg(Open=("Open", "first"), High=("High", "max"),
                             Low=("Low", "min"), Close=("Close", "last"),
                             Volume=("Volume", "sum"))
    g = g[g["Volume"] > 0].reset_index().rename(columns={"DateTime": "DateTime"})
    g.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
    return g


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    bars = daily_24h_bars()
    print(f"24h daily bars: {len(bars)}  {bars['DateTime'].min().date()} -> {bars['DateTime'].max().date()}")

    real = re_.run_all({"daily": bars}, "real24h")

    rng = np.random.default_rng(re_.SEED + 1)
    null_rows = []
    for kind, reps in re_.NREPS.items():
        for rep in range(reps):
            nb = rvd.make_null(kind, bars, rng)
            t = re_.run_all({"daily": nb}, f"null_{kind}")
            t["rep"] = rep
            null_rows.append(t)
    nulls = pd.concat(null_rows, ignore_index=True)

    def agg_null(g):
        w = g["N"].to_numpy(); m = g["mean_bp"].to_numpy()
        ok = (w > 0) & ~np.isnan(m)
        return pd.Series({
            "null_N": int(w[ok].sum()),
            "null_mean_bp": round(float((m[ok] * w[ok]).sum() / w[ok].sum()), 1) if w[ok].sum() else np.nan,
        })
    na = (nulls.groupby(["event", "tf", "side", "h"])
                .apply(agg_null, include_groups=False).reset_index())
    gate = real.merge(na, on=["event", "tf", "side", "h"], how="left")
    gate["edge_vs_null_bp"] = (gate["mean_bp"] - gate["null_mean_bp"]).round(1)
    gate.to_csv(OUT / f"events24h_gate_{tag}.csv", index=False)

    pd.set_option("display.width", 250)
    show = gate[gate["h"].isin([1, 3, 5, 20])][
        ["event", "side", "h", "N", "mean_bp", "median_bp", "up%", "t",
         "null_N", "null_mean_bp", "edge_vs_null_bp"]]
    for ev in re_.EVENTS:
        sub = show[show["event"] == ev]
        if len(sub):
            print(f"\n=== {ev} (24h daily) ===")
            print(sub.to_string(index=False))
    return gate


if __name__ == "__main__":
    main()
