"""redundancy_gate.py — Stage 1 KILL GATE of the tempo/market-state study (S116).

Question: does 2000t tempo carry information NOT already in range/volume/volatility?

Pre-registered kill rule (set before running, per the roadmap):
  KILL if, in every year, (a) |partial corr| of tempo terms with both forward
  outcomes given the baseline < 0.05 AND (b) ΔR² from adding tempo terms < 0.005.
  Otherwise the tempo terms carry independent variance -> Stage 2 (event study).

Setup (full 2000-tick bars only, forward windows never cross a day boundary):
  baseline features (causal): log_range, log_vol, eff, rv20 (std of last-20 bar
    log closes diffs), plus time-of-day via the tod-adjusted tempo construction
  tempo terms: tod_adj_tempo (log tempo minus trailing-60-session median log
    tempo for the same 15-min session bucket), tempo_accel (log tempo minus
    log EMA20 of tempo, within day)
  forward outcomes (H=10 bars): fwd_abs (|close[t+H]-close[t]|),
    fwd_range (sum range t+1..t+H), fwd_signed (direction test, expect null)

Outputs: tempo/outputs/redundancy_gate_<today>.csv (all stats),
         _corr.csv (feature corr matrix), _gate.png (summary chart).

    python tempo/scripts/redundancy_gate.py [--horizon 10]
"""
from __future__ import annotations
import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
ALL = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs"
SIZE = 2000
TOD_BUCKET_MIN = 15
TOD_TRAIL_DAYS = 60


def build_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["log_tempo"] = np.log(df["tempo"])
    df["log_range"] = np.log(df["range"].clip(lower=0.25))
    df["log_vol"] = np.log(df["vol"].clip(lower=1))

    # within-day causal pieces (transforms so the date column survives pandas>=3)
    gb = df.groupby("date")
    lc = np.log(df["close"])
    df["ret"] = lc.groupby(df["date"]).diff()
    df["rv20"] = gb["ret"].transform(lambda s: s.rolling(20).std())
    ema = gb["tempo"].transform(lambda s: s.ewm(span=20, adjust=False).mean().shift(1))
    df["tempo_accel"] = np.log(df["tempo"]) - np.log(ema)
    fwd_close = gb["close"].shift(-horizon)
    df["fwd_abs"] = (fwd_close - df["close"]).abs()
    df["fwd_signed"] = fwd_close - df["close"]
    df["fwd_range"] = gb["range"].transform(
        lambda s: s.shift(-1).rolling(horizon).sum().shift(-(horizon - 1)))

    # time-of-day adjustment: trailing TOD_TRAIL_DAYS median log_tempo per 15-min bucket
    df["bucket"] = (df["session_min"] // TOD_BUCKET_MIN).astype(int)
    day_bucket = (df.groupby(["date", "bucket"])["log_tempo"].mean()
                    .rename("db_mean").reset_index())
    day_bucket["tod_med"] = (day_bucket.sort_values("date")
                             .groupby("bucket")["db_mean"]
                             .transform(lambda s: s.rolling(TOD_TRAIL_DAYS, min_periods=30)
                                        .median().shift(1)))
    df = df.merge(day_bucket[["date", "bucket", "tod_med"]], on=["date", "bucket"], how="left")
    df["tod_adj_tempo"] = df["log_tempo"] - df["tod_med"]
    return df


def ols_r2(X: np.ndarray, y: np.ndarray) -> float:
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    return 1.0 - resid.var() / y.var()


def partial_corr(x, y, Z):
    Z1 = np.column_stack([np.ones(len(Z)), Z])
    rx = x - Z1 @ np.linalg.lstsq(Z1, x, rcond=None)[0]
    ry = y - Z1 @ np.linalg.lstsq(Z1, y, rcond=None)[0]
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=10)
    a = ap.parse_args()
    today = dt.date.today().isoformat()

    df = pd.read_parquet(ALL)
    df = df[df["ticks"] == SIZE].copy()
    df = build_features(df, a.horizon)

    base_cols = ["log_range", "log_vol", "eff", "rv20"]
    tempo_cols = ["tod_adj_tempo", "tempo_accel"]
    need = base_cols + tempo_cols + ["fwd_abs", "fwd_range", "fwd_signed", "log_tempo"]
    d = df.dropna(subset=need).copy()
    d["year"] = d["date"].str[:4]
    print(f"usable bars: {len(d):,} over {d['date'].nunique():,} days "
          f"({d['date'].min()} .. {d['date'].max()})")

    # feature correlation matrix (pooled)
    corr = d[["log_tempo", "tod_adj_tempo", "tempo_accel"] + base_cols].corr()
    corr.to_csv(OUT / f"redundancy_gate_{today}_corr.csv")

    rows = []
    for yr, g in [("ALL", d)] + list(d.groupby("year")):
        Zb = g[base_cols].to_numpy()
        Zt = g[base_cols + tempo_cols].to_numpy()
        for outc in ["fwd_abs", "fwd_range", "fwd_signed"]:
            y = g[outc].to_numpy()
            r2b, r2t = ols_r2(Zb, y), ols_r2(Zt, y)
            rows.append({
                "year": yr, "outcome": outc, "n": len(g),
                "r2_base": r2b, "r2_base_plus_tempo": r2t, "delta_r2": r2t - r2b,
                "pcorr_todadj": partial_corr(g["tod_adj_tempo"].to_numpy(), y, Zb),
                "pcorr_accel": partial_corr(g["tempo_accel"].to_numpy(), y, Zb),
                "raw_corr_logtempo": float(np.corrcoef(g["log_tempo"], y)[0, 1]),
            })
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"redundancy_gate_{today}.csv", index=False)

    # gate verdict: evaluate on the magnitude outcomes, per year
    yrs = res[(res["year"] != "ALL") & (res["outcome"] != "fwd_signed")]
    passes = yrs[(yrs["delta_r2"] >= 0.005) |
                 (yrs[["pcorr_todadj", "pcorr_accel"]].abs().max(axis=1) >= 0.05)]
    verdict = "KILL" if passes.empty else "PASS"

    print("\n=== correlation with tempo (pooled) ===")
    print(corr.round(3).to_string())
    print("\n=== incremental value of tempo terms over baseline ===")
    print(res.round(4).to_string(index=False))
    print(f"\nGATE VERDICT: {verdict}  "
          f"({len(passes)}/{len(yrs)} year×outcome cells beat a threshold)")

    # chart: ΔR² by year/outcome + partial corrs
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    piv = yrs.pivot(index="year", columns="outcome", values="delta_r2")
    piv.plot.bar(ax=axes[0], color=["#4c72b0", "#dd8452"])
    axes[0].axhline(0.005, color="red", ls="--", lw=1, label="kill threshold 0.005")
    axes[0].set_title(f"ΔR² from tempo terms (H={a.horizon} bars)"); axes[0].legend()
    pc = yrs.melt(id_vars=["year", "outcome"], value_vars=["pcorr_todadj", "pcorr_accel"])
    for i, (name, gg) in enumerate(pc.groupby(["outcome", "variable"])):
        axes[1].plot(gg["year"], gg["value"].abs(), marker="o", label=f"{name[0]}/{name[1]}")
    axes[1].axhline(0.05, color="red", ls="--", lw=1)
    axes[1].set_title("|partial corr| of tempo terms given baseline"); axes[1].legend(fontsize=7)
    for ax in axes:
        ax.grid(alpha=0.25)
    png = OUT / f"redundancy_gate_{today}.png"
    fig.suptitle(f"Tempo redundancy gate — verdict: {verdict}")
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    print(f"saved -> {png.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
