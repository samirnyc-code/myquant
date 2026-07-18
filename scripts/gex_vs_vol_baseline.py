"""S75Q step 3 — does net-GEX add anything over the vol proxies we already have?

Target : today's realised range, (High-Low)/prevClose * 100
Baselines, all known at the PRIOR close:
    B1  prior-day range
    B2  B1 + ATR(10)
    B3  B2 + VIX close        <- the honest baseline; VIX already prices expected vol
    B4  B3 + net-GEX features (sign, and signed magnitude percentile)

Scored walk-forward (expanding window, refit each session, no lookahead) so
the extra columns in B4 cannot buy R-squared with in-sample overfit.
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MIN_TRAIN = 250          # ~1yr before the first out-of-sample prediction


def gex_daily():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data" / "orats" / "SPX" / "SPX_*.parquet"))):
        yr = pd.read_parquet(f)
        for c in ["gamma", "delta", "callOpenInterest", "putOpenInterest",
                  "dte", "spotPrice"]:
            yr[c] = pd.to_numeric(yr[c], errors="coerce")
        yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
        for d, g in yr.groupby("tradeDate"):
            net = float((g.gamma * (g.callOpenInterest - g.putOpenInterest)).sum())
            if np.isfinite(net):
                rows.append({"date": str(d)[:10], "gex": net})
    return pd.DataFrame(rows).set_index("date")


def walkforward(X, y):
    """Expanding-window OLS. Returns out-of-sample MAE and R^2."""
    pred = np.full(len(y), np.nan)
    for i in range(MIN_TRAIN, len(y)):
        A, b = X[:i], y[:i]
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        pred[i] = X[i] @ coef
    m = ~np.isnan(pred)
    err = y[m] - pred[m]
    ss = 1 - (err**2).sum() / ((y[m] - y[m].mean())**2).sum()
    return np.abs(err).mean(), ss, m.sum()


def main():
    spx = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
    spx["Date"] = spx.Date.astype(str).str[:10]
    spx = spx.set_index("Date")[["High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce")

    vix = pd.read_csv(ROOT / "data" / "vix_daily.csv")
    vix["date"] = vix.date.astype(str).str[:10]
    vix = vix.set_index("date")[["close"]].rename(columns={"close": "vix"})

    df = spx.join(vix, how="left").join(gex_daily(), how="inner").sort_index()
    df["rng"] = (df.High - df.Low) / df.Close.shift(1) * 100
    df["prior_rng"] = df.rng.shift(1)
    df["atr10"] = df.rng.rolling(10).mean().shift(1)
    df["vix_p"] = df.vix.shift(1)
    df["gex_sign"] = np.sign(df.gex).shift(1)
    # signed magnitude as an expanding percentile -> scale-free, no lookahead
    df["gex_pct"] = (df.gex.expanding().rank(pct=True) - 0.5).shift(1)

    df = df.dropna(subset=["rng", "prior_rng", "atr10", "vix_p", "gex_sign", "gex_pct"])
    y = df.rng.to_numpy()
    one = np.ones((len(df), 1))

    cols = {
        "B1 prior range":        ["prior_rng"],
        "B2 + ATR10":            ["prior_rng", "atr10"],
        "B3 + VIX":              ["prior_rng", "atr10", "vix_p"],
        "B4 + net GEX":          ["prior_rng", "atr10", "vix_p", "gex_sign", "gex_pct"],
        "GEX only (reference)":  ["gex_sign", "gex_pct"],
    }
    print(f"\n=== incremental value of net GEX, walk-forward OOS "
          f"({len(df)} sessions, {MIN_TRAIN} warmup) ===")
    print(f"  {'model':22s} {'OOS MAE':>9s} {'OOS R^2':>9s} {'n':>6s}")
    for name, cs in cols.items():
        X = np.hstack([one, df[cs].to_numpy()])
        mae, r2, n = walkforward(X, y)
        print(f"  {name:22s} {mae:9.4f} {r2:9.4f} {n:6d}")

    # is the vol split just VIX in disguise?
    print("\n=== mean realised range by GEX sign, within VIX terciles ===")
    df["vix_t"] = pd.qcut(df.vix_p, 3, labels=["low VIX", "mid VIX", "high VIX"])
    tab = df.pivot_table(index="vix_t", columns=np.sign(df.gex_sign),
                         values="rng", aggfunc=["mean", "size"], observed=True)
    print(tab.round(2).to_string())


if __name__ == "__main__":
    main()
