"""regime_features.py — Grimes-derived regime features for ES.

Computes the codable feature set from
docs/research_notes/grimes_regime/SYNTHESIS_regime_engine_design.md (section 4)
on ES bars resampled from data/bars/_continuous_1m.parquet (RTH session, 2021-06 -> 2026-07).

STRICTLY CAUSAL: every feature at bar t uses only information available at the close of
bar t (or earlier). The ATR-zigzag confirms a pivot only AFTER a k*ATR reversal, so pivot
labels lag — that lag is real and intended (no look-ahead).

Design choices (documented, v0):
  * DAILY  = RTH session close-to-close (one bar per trading day, 08:30-15:15 CT).
    Overnight gap is captured in the next session's OPEN, so gaps survive in the OHLC.
    24h/globex daily is a later refinement.
  * 60m/30m = within-session resample; overnight-spanning bins are dropped.

Feature specs (page cites in the synthesis doc):
  - ATR: SMA of true range, window ATR_N.
  - Keltner: 20-EMA +/- 2.25*ATR(20). position (-1/0/+1 by close vs bands),
    free_bar (whole bar outside a band), pct_outside rolling.
  - Modified MACD: fast = SMA3 - SMA10; signal = SMA16 of fast (all SMA). Flags:
    new momentum extreme over 40-bar lookback, zero-cross, drive-and-hold (fast pegged).
  - MA slope 3-state: slope of MA_SLOPE_N SMA via 5-point linear regression; undefined
    zone = |slope| < SLOPE_EPS * price.
  - Triple MA order: 10/20/50 SMA correctly ordered = +1/-1, interleaved = 0.
  - Vol ratio: ATR(5)/ATR(40); < 0.5 = compressed.
  - Sigma-spike: return / prior 20-bar stdev of returns.
  - GER (Grimes Efficiency Ratio, his EasyLanguage): avg over N of
    (close - lowest_low_N) / (highest_high_N - lowest_low_N). ~1 up, ~0 down, mid = range.
  - ATR-zigzag -> Dow state: HH+HL = +1 (up), LH+LL = -1 (down), else 0 (uncertain).
  - Climax bar: range >= 3x recent avg range at a new N-bar extreme.
  - Leg counter + retracement depth from the confirmed zigzag.

Run:
  .venv/Scripts/python.exe scripts/regime_features.py            # all timeframes
Outputs (dated): data/regime/features_<tf>_<YYYYMMDD>.parquet + a .csv head sample.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS_1M = ROOT / "data" / "bars" / "_continuous_1m.parquet"
OUT = ROOT / "data" / "regime"
OUT.mkdir(parents=True, exist_ok=True)

# ---- parameters (Grimes specs) --------------------------------------------
KELT_N, KELT_MULT = 20, 2.25
ATR_N = 20
MACD_FAST, MACD_SLOW, MACD_SIG = 3, 10, 16
MACD_LOOKBACK = 40           # "new momentum extreme" window (book p.219)
MA_SLOPE_N = 50
SLOPE_EPS = 0.00010          # undefined zone: |slope/price| < this
VOL_FAST, VOL_SLOW = 5, 40   # compression ratio (wb p.596)
COMPRESS_THR = 0.5
SIGMA_N = 20
GER_N = 20
ZZ_K = 3.0                   # zigzag reversal = ZZ_K * ATR (his 3x avg-bar-range, wb p.64)
CLIMAX_MULT = 3.0            # climax bar range >= 3x recent avg (wb p.192)
CLIMAX_N = 10                # recent-avg window for climax


# ---- bar construction ------------------------------------------------------
def _load_1m() -> pd.DataFrame:
    df = pd.read_parquet(BARS_1M).copy()
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    return df.sort_values("DateTime").reset_index(drop=True)


def resample_bars(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """tf in {'daily','60m','30m'}. Session-aware; no overnight-spanning bars."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    if tf == "daily":
        g = m1.set_index("DateTime").groupby(pd.Grouper(freq="D")).agg(agg)
    else:
        freq = {"60m": "60min", "30m": "30min"}[tf]
        # origin='start' -> bins align to the first ts (08:30), and since the RTH open is
        # 08:30 every day and 60/30-min bins tile a day evenly, every session is 08:30-aligned.
        g = m1.set_index("DateTime").resample(freq, origin="start", label="left",
                                              closed="left").agg(agg)
    g = g.dropna(subset=["Open"]).reset_index()
    g = g[g["Volume"] > 0].reset_index(drop=True)
    return g


# ---- primitive indicators --------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - pc).abs(),
                    (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    return true_range(df).rolling(n, min_periods=n).mean()


def _slope_5pt(s: pd.Series) -> pd.Series:
    """Slope of a 5-point linear regression through the last 5 values of s (wb p.548)."""
    x = np.arange(5)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()
    def f(w):
        return ((x - xm) * (w - w.mean())).sum() / denom
    return s.rolling(5, min_periods=5).apply(f, raw=True)


# ---- zigzag + Dow state (causal) ------------------------------------------
def zigzag_dow(df: pd.DataFrame, atr_series: pd.Series, k: float):
    """Confirmed ATR-zigzag. Returns per-bar arrays:
       dow_state (+1/-1/0), leg_count, retr_depth (last completed pullback BC/AB),
       swings_dir at confirmation. Pivots confirm only after a k*ATR counter-move,
       so labels are causal (known at bar t)."""
    n = len(df)
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    a = atr_series.to_numpy()

    dow = np.zeros(n, dtype=np.int8)
    legc = np.zeros(n, dtype=np.int16)
    retr = np.full(n, np.nan)

    # confirmed pivots: lists of (idx, price, kind) kind=+1 high, -1 low
    piv_idx: list[int] = []
    piv_prc: list[float] = []
    piv_knd: list[int] = []

    direction = 0            # current provisional swing direction
    ext_idx = 0             # index of running extreme
    ext_prc = (high[0] + low[0]) / 2.0

    def push_pivot(i, p, kind):
        piv_idx.append(i); piv_prc.append(p); piv_knd.append(kind)

    for i in range(n):
        thr = a[i] * k if not np.isnan(a[i]) else np.inf
        if direction >= 0:
            # in an up (or undecided) swing: track higher highs
            if high[i] > ext_prc:
                ext_prc = high[i]; ext_idx = i
            # reversal down?
            if ext_prc - low[i] >= thr and thr != np.inf:
                push_pivot(ext_idx, ext_prc, +1)   # confirm the high
                direction = -1
                ext_prc = low[i]; ext_idx = i
        else:
            if low[i] < ext_prc:
                ext_prc = low[i]; ext_idx = i
            if high[i] - ext_prc >= thr and thr != np.inf:
                push_pivot(ext_idx, ext_prc, -1)
                direction = +1
                ext_prc = high[i]; ext_idx = i

        # Dow state from the last two confirmed highs and last two confirmed lows
        highs = [(piv_idx[j], piv_prc[j]) for j in range(len(piv_knd)) if piv_knd[j] == +1]
        lows = [(piv_idx[j], piv_prc[j]) for j in range(len(piv_knd)) if piv_knd[j] == -1]
        st = 0
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1][1] > highs[-2][1]
            hl = lows[-1][1] > lows[-2][1]
            lh = highs[-1][1] < highs[-2][1]
            ll = lows[-1][1] < lows[-2][1]
            if hh and hl:
                st = +1
            elif lh and ll:
                st = -1
            else:
                st = 0
        dow[i] = st

        # leg count = confirmed pivots in the current directional run
        legc[i] = len(piv_knd)

        # retracement depth of the last completed pullback (BC/AB) using last 3 pivots
        if len(piv_prc) >= 3:
            a_, b_, c_ = piv_prc[-3], piv_prc[-2], piv_prc[-1]
            ab = abs(b_ - a_)
            bc = abs(c_ - b_)
            retr[i] = (bc / ab) if ab > 0 else np.nan

    return dow, legc, retr


# ---- full feature frame ----------------------------------------------------
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    f = df.copy()
    c = f["Close"]

    f["tr"] = true_range(f)
    f["atr"] = atr(f, ATR_N)
    f["atr_fast"] = atr(f, VOL_FAST)
    f["atr_slow"] = atr(f, VOL_SLOW)

    # Keltner 20-EMA +/- 2.25 ATR
    ema = c.ewm(span=KELT_N, adjust=False).mean()
    f["kelt_mid"] = ema
    f["kelt_up"] = ema + KELT_MULT * f["atr"]
    f["kelt_dn"] = ema - KELT_MULT * f["atr"]
    f["kelt_pos"] = np.where(c > f["kelt_up"], 1, np.where(c < f["kelt_dn"], -1, 0))
    f["free_bar"] = np.where(f["Low"] > f["kelt_up"], 1,
                             np.where(f["High"] < f["kelt_dn"], -1, 0))
    f["pct_outside_20"] = (f["kelt_pos"] != 0).rolling(20, min_periods=5).mean()

    # Modified MACD (all SMA)
    fast = c.rolling(MACD_FAST).mean() - c.rolling(MACD_SLOW).mean()
    sig = fast.rolling(MACD_SIG).mean()
    f["macd_fast"] = fast
    f["macd_sig"] = sig
    f["macd_new_hi"] = (fast >= fast.rolling(MACD_LOOKBACK, min_periods=10).max()).astype(int)
    f["macd_new_lo"] = (fast <= fast.rolling(MACD_LOOKBACK, min_periods=10).min()).astype(int)
    f["macd_zero_cross"] = (np.sign(fast) != np.sign(fast.shift(1))).astype(int)
    # drive-and-hold: fast in top/bottom decile of its lookback for >=3 consecutive bars
    hi_dec = fast >= fast.rolling(MACD_LOOKBACK, min_periods=10).quantile(0.9)
    lo_dec = fast <= fast.rolling(MACD_LOOKBACK, min_periods=10).quantile(0.1)
    f["macd_drive"] = np.where(hi_dec.rolling(3).sum() == 3, 1,
                               np.where(lo_dec.rolling(3).sum() == 3, -1, 0))

    # MA slope 3-state
    ma = c.rolling(MA_SLOPE_N).mean()
    slope = _slope_5pt(ma)
    f["ma_slope"] = slope
    f["ma_slope_state"] = np.where(slope > SLOPE_EPS * c, 1,
                                   np.where(slope < -SLOPE_EPS * c, -1, 0))

    # Triple MA order
    s10, s20, s50 = c.rolling(10).mean(), c.rolling(20).mean(), c.rolling(50).mean()
    f["triple_ma"] = np.where((s10 > s20) & (s20 > s50), 1,
                              np.where((s10 < s20) & (s20 < s50), -1, 0))

    # Vol compression ratio
    f["vol_ratio"] = f["atr_fast"] / f["atr_slow"]
    f["compressed"] = (f["vol_ratio"] < COMPRESS_THR).astype(int)

    # Sigma-spike (return / prior 20-bar stdev of returns)
    ret = c.pct_change()
    f["ret"] = ret
    f["sigma_spike"] = ret / ret.rolling(SIGMA_N).std().shift(1)

    # GER (his EasyLanguage)
    hh = f["High"].rolling(GER_N).max()
    ll = f["Low"].rolling(GER_N).min()
    rng = hh - ll
    crng = np.where(rng > 0, (c - ll) / rng, np.nan)
    f["ger"] = pd.Series(crng, index=f.index).rolling(GER_N).mean()

    # Climax bar
    avg_rng = (f["High"] - f["Low"]).rolling(CLIMAX_N, min_periods=CLIMAX_N).mean().shift(1)
    new_hi = f["High"] >= f["High"].rolling(CLIMAX_N).max()
    new_lo = f["Low"] <= f["Low"].rolling(CLIMAX_N).min()
    big = (f["High"] - f["Low"]) >= CLIMAX_MULT * avg_rng
    f["climax"] = np.where(big & new_hi, 1, np.where(big & new_lo, -1, 0))

    # ATR-zigzag -> Dow state, leg count, retracement depth
    dow, legc, retr = zigzag_dow(f, f["atr"], ZZ_K)
    f["dow_state"] = dow
    f["leg_count"] = legc
    f["retr_depth"] = retr

    return f


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    m1 = _load_1m()
    print(f"loaded 1m bars: {len(m1):,}  {m1['DateTime'].min()} -> {m1['DateTime'].max()}")
    summary = []
    for tf in ("daily", "60m", "30m"):
        bars = resample_bars(m1, tf)
        feats = build_features(bars)
        outp = OUT / f"features_{tf}_{tag}.parquet"
        feats.to_parquet(outp, index=False)
        # small csv head/tail sample for eyeballing
        feats.tail(300).to_csv(OUT / f"features_{tf}_{tag}_tail.csv", index=False)
        # coverage of the causal features (fraction non-null once warmed up)
        warm = feats.iloc[max(60, GER_N + 5):]
        summary.append({
            "tf": tf, "bars": len(bars),
            "first": str(bars["DateTime"].min()), "last": str(bars["DateTime"].max()),
            "dow_up%": round(100 * (warm["dow_state"] == 1).mean(), 1),
            "dow_dn%": round(100 * (warm["dow_state"] == -1).mean(), 1),
            "dow_unc%": round(100 * (warm["dow_state"] == 0).mean(), 1),
            "compressed%": round(100 * warm["compressed"].mean(), 1),
            "out": outp.name,
        })
    sm = pd.DataFrame(summary)
    sm.to_csv(OUT / f"features_summary_{tag}.csv", index=False)
    print(sm.to_string(index=False))
    return sm


if __name__ == "__main__":
    main()
