"""Augment RevFT signals with TRADE-LOCATION features (causal — only bars completed
at the FT-bar close time are used). Location is likely the key to reversal edge.

Features per signal:
  rlow/rhigh  : session running low/high THROUGH the FT bar (1D intraday min/max).
  loc_pct     : (entry - rlow) / (rhigh - rlow)   0=at day low, 1=at day high.
  dist_ext    : points from the day extreme in the fade-favourable direction
                (long: entry - rlow ; short: rhigh - entry).  small = good location.
  pdh/pdl     : prior RTH day high/low.
  d_pdl/d_pdh : entry distance to PDL / PDH (pts).
  fresh_ext   : signal made a fresh N-bar extreme within the last 3 bars (bool),
                the indicator's own 'Extreme' filter (N default 8).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "revsim"))
import revsim as R

N_EXT = 8


def build(sig_txt=None, out=None, n_ext=N_EXT):
    sg = R.parse_signals() if sig_txt is None else R.parse_signals(sig_txt)
    sg = sg[sg.Date >= "2021-06-18"].reset_index(drop=True)
    df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
    df5["DateTime"] = pd.to_datetime(df5["DateTime"])
    # prior-day H/L
    dayHL = df5.groupby("Date").agg(dh=("High", "max"), dl=("Low", "min"))
    dates = list(dayHL.index)
    pdh = {d: (dayHL.dh.iloc[i - 1] if i > 0 else np.nan) for i, d in enumerate(dates)}
    pdl = {d: (dayHL.dl.iloc[i - 1] if i > 0 else np.nan) for i, d in enumerate(dates)}

    feats = []
    for date, day in df5.groupby("Date", sort=True):
        day = day.sort_values("DateTime").reset_index(drop=True)
        H, Lo = day.High.values, day.Low.values
        bt = day.DateTime.values.astype("datetime64[ns]")
        rhigh = np.maximum.accumulate(H); rlow = np.minimum.accumulate(Lo)
        ssig = R  # noop
        ds = sg[sg.Date == date]
        for idx, s in ds.iterrows():
            T = np.datetime64(s["time"])
            # bars completed at/by FT close T -> open-time <= T-5min (FT bar open = T-5)
            k = np.searchsorted(bt, T, side="right") - 1  # last bar with open <= T; FT bar open=T-5<=T
            if k < 0:
                continue
            rl, rh = rlow[k], rhigh[k]
            rng = max(rh - rl, 0.25)
            loc = (s["entry"] - rl) / rng
            if s["side"] > 0:
                dist_ext = s["entry"] - rl
            else:
                dist_ext = rh - s["entry"]
            # fresh N-bar extreme within last 3 bars
            fresh = False
            if k >= n_ext:
                if s["side"] > 0:
                    fresh = Lo[max(0, k - 2):k + 1].min() <= Lo[max(0, k - n_ext + 1):k + 1].min() + 1e-9
                else:
                    fresh = H[max(0, k - 2):k + 1].max() >= H[max(0, k - n_ext + 1):k + 1].max() - 1e-9
            feats.append(dict(idx=idx, rlow=rl, rhigh=rh, loc_pct=round(loc, 3),
                              dist_ext=round(dist_ext, 2), fresh_ext=bool(fresh),
                              pdh=pdh.get(date, np.nan), pdl=pdl.get(date, np.nan),
                              d_pdl=round(s["entry"] - pdl.get(date, np.nan), 2),
                              d_pdh=round(pdh.get(date, np.nan) - s["entry"], 2)))
    fdf = pd.DataFrame(feats).set_index("idx")
    aug = sg.join(fdf)
    outp = out or (ROOT / "research" / "revsim" / "signals_located.parquet")
    aug.to_parquet(outp)
    print(f"wrote {outp}  {len(aug)} signals, {fdf.shape[1]} loc features")
    print(aug[["rev", "side", "entry", "loc_pct", "dist_ext", "fresh_ext", "d_pdl", "d_pdh"]].head(8).to_string())
    return aug


if __name__ == "__main__":
    build()
