"""regime_events_2010.py — the powered rerun: Grimes event tests on ES 2010-2026 (Databento).

Source: data/bars/_db_es_daily_24h.parquet (4,155 session dailies, volume-roll continuous,
back-adjusted; validated 17-2 vs SPX cash on disagreement days against the NT series) and
data/bars/_db_es_1h_continuous.parquet for the 60m check.
Same detectors/scoring/nulls as regime_events.py (20x shuffle + 20x rw, N-weighted).

Run: .venv/Scripts/python.exe scripts/regime_events_2010.py
Out: data/regime/events2010_gate_<tag>.csv + console tables.
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
BARS = ROOT / "data" / "bars"


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    daily = pd.read_parquet(BARS / "_db_es_daily_24h.parquet")
    h1 = pd.read_parquet(BARS / "_db_es_1h_continuous.parquet")
    h1 = h1[["DateTime", "Open", "High", "Low", "Close", "Volume"]]
    print(f"daily {len(daily)} bars {daily['DateTime'].min().date()} -> {daily['DateTime'].max().date()}; "
          f"hourly {len(h1):,}")

    bars = {"daily": daily, "60m": h1}
    real = re_.run_all(bars, "real2010")

    rng = np.random.default_rng(re_.SEED + 2)
    null_rows = []
    for kind, reps in re_.NREPS.items():
        for rep in range(reps):
            for tf in ("daily", "60m"):
                nb = rvd.make_null(kind, bars[tf], rng)
                t = re_.run_all({tf: nb}, f"null_{kind}")
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
    gate.to_csv(OUT / f"events2010_gate_{tag}.csv", index=False)

    pd.set_option("display.width", 250)
    show = gate[gate["h"].isin([1, 3, 5, 20])][
        ["event", "tf", "side", "h", "N", "mean_bp", "median_bp", "up%", "t",
         "null_N", "null_mean_bp", "edge_vs_null_bp"]]
    for ev in re_.EVENTS:
        for tf in ("daily", "60m"):
            sub = show[(show["event"] == ev) & (show["tf"] == tf)]
            if len(sub):
                print(f"\n=== {ev} ({tf}, 2010-2026) ===")
                print(sub.to_string(index=False))
    return gate


if __name__ == "__main__":
    main()
