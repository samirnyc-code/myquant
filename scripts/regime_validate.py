"""regime_validate.py — Pythia-style validation of the v0 regime states on ES.

The decision gate. For each bar, its FORWARD return over horizon h is attributed to the
state known at the PRIOR bar's close (no look-ahead). We then ask: do bull/bear/no_trade/
transition separate ES forward returns, and does that separation SURVIVE synthetic nulls?

Protocol (synthesis doc sec.6, Grimes "Pythia"):
  * horizons h in {1,3,5,10,20} bars.
  * per-state: N, mean forward return (bp), median, %up, std, t-stat vs 0, excess vs the
    all-bars baseline (bp).
  * NULLS: iid-normal random walk, block-shuffled real returns, mild AR(1). Rebuild OHLC,
    rerun the SAME features + state machine + scoring. If bull/bear separate returns on the
    nulls too, the "edge" is an artifact of the classifier, not the market.
  * report guidance: ignore effects < 10 bp or with mean/median sign disagreement.

Run:
  .venv/Scripts/python.exe scripts/regime_validate.py           # daily + 30m real, daily nulls
Outputs (dated): data/regime/validate_<tf>_<YYYYMMDD>.csv, validate_nulls_<YYYYMMDD>.csv,
                 regime_validate_<YYYYMMDD>.png (auto-opened in VSCode).
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import regime_features as rf
import regime_v0 as rv

OUT = ROOT / "data" / "regime"
HORIZONS = [1, 3, 5, 10, 20]
STATES = ["no_trade", "bull", "bear", "transition"]
SEED = 20260723


def score_states(bars: pd.DataFrame) -> pd.DataFrame:
    """bars: OHLCV frame. Returns per-(state,horizon) stats, forward return attributed to
    the state at the PRIOR bar (state.shift(1))."""
    feats = rf.build_features(bars)
    states = rv.run_state_machine(feats)
    close = feats["Close"].to_numpy()
    st_prior = states["state"].shift(1)         # decision made at prior close -> no look-ahead
    rows = []
    for h in HORIZONS:
        fwd = pd.Series(close, index=feats.index).shift(-h) / pd.Series(close, index=feats.index) - 1
        base = fwd.dropna()
        base_mean = base.mean()
        for st in STATES:
            m = (st_prior == st).to_numpy() & fwd.notna().to_numpy()
            r = fwd[m]
            if len(r) < 5:
                rows.append({"state": st, "h": h, "N": len(r), "mean_bp": np.nan,
                             "median_bp": np.nan, "up%": np.nan, "std_bp": np.nan,
                             "t": np.nan, "excess_bp": np.nan})
                continue
            t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if r.std(ddof=1) > 0 else np.nan
            rows.append({
                "state": st, "h": h, "N": len(r),
                "mean_bp": round(1e4 * r.mean(), 1),
                "median_bp": round(1e4 * r.median(), 1),
                "up%": round(100 * (r > 0).mean(), 1),
                "std_bp": round(1e4 * r.std(ddof=1), 1),
                "t": round(float(t), 2) if t == t else np.nan,
                "excess_bp": round(1e4 * (r.mean() - base_mean), 1),
            })
    return pd.DataFrame(rows)


# ---- synthetic nulls -------------------------------------------------------
def _fabricate_ohlc(close: np.ndarray, real_bars: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Wrap a synthetic close path in plausible OHLC using shuffled REAL intrabar geometry:
    range/close and (close-low)/range fractions sampled from the real bars."""
    rb = real_bars
    rrange = ((rb["High"] - rb["Low"]) / rb["Close"]).to_numpy()
    rpos = np.where((rb["High"] - rb["Low"]).to_numpy() > 0,
                    (rb["Close"] - rb["Low"]).to_numpy() / (rb["High"] - rb["Low"]).replace(0, np.nan).to_numpy(),
                    0.5)
    rpos = np.nan_to_num(rpos, nan=0.5)
    n = len(close)
    rr = rng.choice(rrange[~np.isnan(rrange)], size=n)
    pp = rng.choice(rpos, size=n)
    rng_abs = rr * close
    low = close - pp * rng_abs
    high = low + rng_abs
    openp = np.empty(n); openp[0] = close[0]
    openp[1:] = close[:-1]                       # open at prior close (no synthetic gaps)
    high = np.maximum.reduce([high, close, openp])
    low = np.minimum.reduce([low, close, openp])
    return pd.DataFrame({"DateTime": rb["DateTime"].to_numpy()[:n], "Open": openp,
                         "High": high, "Low": low, "Close": close,
                         "Volume": rb["Volume"].to_numpy()[:n]})


def make_null(kind: str, real_bars: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    ret = real_bars["Close"].pct_change().dropna().to_numpy()
    sigma = ret.std()
    n = len(real_bars)
    c0 = float(real_bars["Close"].iloc[0])
    if kind == "rw":                              # iid normal random walk
        r = rng.normal(0, sigma, n - 1)
    elif kind == "shuffle":                       # real returns, order destroyed
        r = rng.permutation(ret)[: n - 1]
    elif kind == "ar1":                           # mild positive autocorrelation
        r = np.empty(n - 1); prev = 0.0
        for i in range(n - 1):
            r[i] = 0.2 * prev + rng.normal(0, sigma * 0.98)
            prev = r[i]
    else:
        raise ValueError(kind)
    close = c0 * np.cumprod(np.concatenate([[1.0], 1 + r]))
    return _fabricate_ohlc(close, real_bars, rng)


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    m1 = rf._load_1m()

    real = {}
    for tf in ("daily", "30m"):
        bars = rf.resample_bars(m1, tf)
        tbl = score_states(bars)
        tbl.insert(0, "tf", tf)
        tbl.to_csv(OUT / f"validate_{tf}_{tag}.csv", index=False)
        real[tf] = (bars, tbl)

    # nulls on daily (primary) — the gate
    rng = np.random.default_rng(SEED)
    daily_bars = real["daily"][0]
    null_tbls = []
    for kind in ("rw", "shuffle", "ar1"):
        nb = make_null(kind, daily_bars, rng)
        nt = score_states(nb)
        nt.insert(0, "null", kind)
        null_tbls.append(nt)
    nulls = pd.concat(null_tbls, ignore_index=True)
    nulls.to_csv(OUT / f"validate_nulls_{tag}.csv", index=False)

    # ---- console read-out (h=5, the workhorse horizon) ----
    def slab(tbl, label):
        s = tbl[tbl["h"] == 5][["state", "N", "mean_bp", "median_bp", "up%", "t", "excess_bp"]]
        print(f"\n=== {label} (h=5) ===")
        print(s.to_string(index=False))
    slab(real["daily"][1], "REAL daily")
    slab(real["30m"][1], "REAL 30m")
    for kind in ("rw", "shuffle", "ar1"):
        slab(nulls[nulls["null"] == kind], f"NULL {kind} daily")

    _plot(real["daily"][1], nulls, tag)
    return real, nulls


def _plot(real_daily: pd.DataFrame, nulls: pd.DataFrame, tag: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(HORIZONS), figsize=(4.2 * len(HORIZONS), 4.6), sharey=True)
    colors = {"no_trade": "#8b949e", "bull": "#2e7d4f", "bear": "#b0453a", "transition": "#8a6a1f"}
    for ax, h in zip(axes, HORIZONS):
        rd = real_daily[real_daily["h"] == h].set_index("state")["mean_bp"]
        x = np.arange(len(STATES))
        ax.bar(x, [rd.get(s, np.nan) for s in STATES],
               color=[colors[s] for s in STATES], width=0.62, zorder=3)
        # null band: min/max across the 3 nulls per state
        for j, s in enumerate(STATES):
            vals = nulls[(nulls["h"] == h) & (nulls["state"] == s)]["mean_bp"].dropna()
            if len(vals):
                ax.plot([j - 0.31, j + 0.31], [vals.max()] * 2, color="#d9a03f", lw=1.4, zorder=4)
                ax.plot([j - 0.31, j + 0.31], [vals.min()] * 2, color="#d9a03f", lw=1.4, zorder=4)
        ax.axhline(0, color="#444", lw=0.8)
        ax.set_title(f"h={h}")
        ax.set_xticks(x); ax.set_xticks(x)
        ax.set_xticklabels(["no\ntrade", "bull", "bear", "trans"], fontsize=8)
        ax.grid(axis="y", alpha=0.2, zorder=0)
    axes[0].set_ylabel("mean forward return (bp)")
    fig.suptitle(f"ES v0 regime — forward return by prior-bar state (bars=real, gold=null min/max)  {tag}",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    png = OUT / f"regime_validate_{tag}.png"
    fig.savefig(png, dpi=130)
    plt.close(fig)
    print(f"\nchart -> {png}")
    try:
        subprocess.run(["code", str(png)], shell=True, check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
