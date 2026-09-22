"""opening_tempo_range_forecast.py — first-hour tempo -> rest-of-day range (S116-tempo, desk deliverable).

Formalizes the two verified relationships (Stage-1 bar-level activity forecast;
LegLab morning->afternoon range corr +0.40) into a lookup the 0DTE desk can use
against the EM: given the first hour's tempo profile, what rest-of-day range
should be expected?

=== FROZEN SPEC ===
Per day (half-days and no-ADR days excluded):
  features (known 09:30 CT): r1h = first-hour range; tempo1h = mean self-calib
    tempo pctile of first-hour bars; nclimax1h = count of first-hour bars >=p95;
    gap = |open - prior close| (from bars: prior day last close).
  target: rest_range = (max high - min low) of bars with session_min >= 60,
    in ADR units (trailing 8-day mean daily range).
Tests:
  1) OLS rest_range_adr ~ r1h_adr (+ gap_adr) baseline vs + tempo1h + nclimax1h
     -> delta-R2, pooled + by year. (Does tempo add beyond the range the desk
     already sees on the screen?)
  2) Quintile lookup: within-year quintiles of tempo1h -> median rest_range_adr
     (the practical table).

    python tempo/scripts/opening_tempo_range_forecast.py
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
ADR_LB = 8


def ols_r2(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    return 1.0 - resid.var() / y.var()


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, "tempo"] = np.nan
    print("computing rolling self-calibrated percentiles...")
    df["tpct"] = rolling_bucket_pct(df)

    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"),
                                 op=("open", "first"), cl=("close", "last"),
                                 last_end=("end", "max"))
    day["adr"] = (day["hi"] - day["lo"]).shift(1).rolling(ADR_LB).mean()
    day["prev_close"] = day["cl"].shift(1)
    day["last_t"] = pd.to_datetime(day["last_end"]).dt.time

    fh = df[df["session_min"] < 60]
    rest = df[df["session_min"] >= 60]
    feat = pd.DataFrame({
        "r1h": fh.groupby("date").apply(lambda g: g["high"].max() - g["low"].min()),
        "tempo1h": fh.groupby("date")["tpct"].mean(),
        "nclimax1h": fh.groupby("date")["tpct"].apply(lambda s: int((s >= 95).sum())),
        "rest_range": rest.groupby("date").apply(lambda g: g["high"].max() - g["low"].min()),
    })
    feat = feat.join(day[["adr", "prev_close", "op", "last_t"]])
    feat = feat[(feat["last_t"] >= dt.time(14, 0)) & feat["adr"].notna()
                & (feat["adr"] > 0) & feat["tempo1h"].notna() & feat["rest_range"].notna()
                & feat["prev_close"].notna()]
    feat["gap_adr"] = (feat["op"] - feat["prev_close"]).abs() / feat["adr"]
    feat["r1h_adr"] = feat["r1h"] / feat["adr"]
    feat["rest_adr"] = feat["rest_range"] / feat["adr"]
    feat["year"] = feat.index.str[:4]
    feat.to_csv(OUT / f"opening_tempo_days_{today}.csv")
    print(f"days: {len(feat)}")

    lines = ["=== OLS: rest_range_adr ~ baseline vs + tempo ==="]
    for name, g in [("ALL", feat)] + list(feat.groupby("year")):
        if len(g) < 100:
            continue
        y = g["rest_adr"].to_numpy()
        Xb = g[["r1h_adr", "gap_adr"]].to_numpy()
        Xt = g[["r1h_adr", "gap_adr", "tempo1h", "nclimax1h"]].to_numpy()
        r2b, r2t = ols_r2(Xb, y), ols_r2(Xt, y)
        lines.append(f"  {name}: base R2={r2b:.3f}  +tempo R2={r2t:.3f}  dR2={r2t-r2b:+.4f}  n={len(g)}")

    lines.append("\n=== lookup: first-hour tempo pctile quintile -> median rest-of-day range (ADR units) ===")
    feat["q"] = feat.groupby("year")["tempo1h"].transform(
        lambda s: pd.qcut(s, 5, labels=False, duplicates="drop"))
    tabl = feat.groupby("q").agg(n=("rest_adr", "size"),
                                 tempo1h_mean=("tempo1h", "mean"),
                                 rest_med=("rest_adr", "median"),
                                 rest_q75=("rest_adr", lambda s: s.quantile(.75)))
    lines.append(tabl.round(3).to_string())
    lines.append("\nby-year medians (rows=quintile):")
    piv = feat.pivot_table(index="q", columns="year", values="rest_adr", aggfunc="median").round(2)
    lines.append(piv.to_string())
    txt = "\n".join(lines)
    (OUT / f"opening_tempo_forecast_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
