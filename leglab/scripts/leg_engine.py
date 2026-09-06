"""
LegLab reusable engine — per-day leg records (timing, size, price, direction).

Same leg definition as leg_count_es.py (0.15*ADR, 8d ADR, intrabar HL reversal,
per-day reset) but returns the full list of legs per day so downstream studies can
slice by time (early-leg classifier), measure leg size/ratios, and tag structure.

A leg dict:
  dir        +1 up / -1 down
  i0, i1     bar index of leg start (prior pivot) and end (this pivot / extreme)
  t0, t1     timestamps of start/end bars
  p0, p1     price at start (prior pivot extreme) and end (this leg's extreme)
  size       abs(p1 - p0), points
  bars       i1 - i0
  closed     True if ended by a threshold reversal; False = final in-progress leg
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "data" / "bars" / "_db_es_5m_rth.parquet"
ADR_LOOKBACK = 8
THRESH_FRAC = 0.15


def load_bars():
    df = pd.read_parquet(BARS)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["date"] = df["DateTime"].dt.date
    return df


def daily_table(df):
    daily = df.groupby("date").agg(
        d_open=("Open", "first"), d_close=("Close", "last"),
        d_high=("High", "max"), d_low=("Low", "min"),
        n_bars=("Close", "size"),
    )
    daily["d_range"] = daily["d_high"] - daily["d_low"]
    daily["adr"] = daily["d_range"].shift(1).rolling(ADR_LOOKBACK).mean()
    daily["thr"] = THRESH_FRAC * daily["adr"]
    daily["net"] = daily["d_close"] - daily["d_open"]
    return daily


def legs_for_day(o, h, l, t, thr, include_final=True):
    n = len(h)
    legs = []
    if n == 0:
        return legs

    def mk(i0, p0, i1, p1, d, closed):
        return {"dir": d, "i0": i0, "i1": i1, "t0": t[i0], "t1": t[i1],
                "p0": float(p0), "p1": float(p1), "size": abs(float(p1) - float(p0)),
                "bars": i1 - i0, "closed": closed}

    anchor_i, anchor_p = 0, o[0]      # current leg start (day opens at bar-0 open)
    direction = 0
    hiP, hiI = h[0], 0
    loP, loI = l[0], 0
    # NOTE: mirrors the validated count_legs (leg_count_es.py) EXACTLY — the
    # reversal test is `elif`, so a bar that EXTENDS the current extreme never
    # also triggers a reversal (prevents whippy 0-1 bar legs). Do not change to
    # a plain `if` or the count inflates (~24 vs 15 median).
    for i in range(1, n):
        if direction == 1:
            if h[i] >= hiP:
                hiP, hiI = h[i], i
            elif (hiP - l[i]) >= thr:                      # reversal down -> close up leg
                legs.append(mk(anchor_i, anchor_p, hiI, hiP, +1, True))
                anchor_i, anchor_p = hiI, hiP
                direction = -1
                loP, loI = l[i], i
        elif direction == -1:
            if l[i] <= loP:
                loP, loI = l[i], i
            elif (h[i] - loP) >= thr:                       # reversal up -> close down leg
                legs.append(mk(anchor_i, anchor_p, loI, loP, -1, True))
                anchor_i, anchor_p = loI, loP
                direction = 1
                hiP, hiI = h[i], i
        else:  # direction == 0, bootstrap (update both, then test down-rev first)
            if h[i] >= hiP:
                hiP, hiI = h[i], i
            if l[i] <= loP:
                loP, loI = l[i], i
            if (hiP - l[i]) >= thr:                          # up leg completed -> now down
                legs.append(mk(anchor_i, anchor_p, hiI, hiP, +1, True))
                anchor_i, anchor_p = hiI, hiP
                direction = -1
                loP, loI = l[i], i
            elif (h[i] - loP) >= thr:                        # down leg completed -> now up
                legs.append(mk(anchor_i, anchor_p, loI, loP, -1, True))
                anchor_i, anchor_p = loI, loP
                direction = 1
                hiP, hiI = h[i], i

    if include_final and direction != 0:
        if direction == 1:
            legs.append(mk(anchor_i, anchor_p, hiI, hiP, +1, False))
        else:
            legs.append(mk(anchor_i, anchor_p, loI, loP, -1, False))
    return legs


def iter_days(df=None, daily=None, min_bars=20):
    """Yield (date, day_df, thr) for days with a valid ADR threshold."""
    if df is None:
        df = load_bars()
    if daily is None:
        daily = daily_table(df)
    for date, g in df.groupby("date"):
        thr = daily.loc[date, "thr"]
        if not np.isfinite(thr) or thr <= 0 or len(g) < min_bars:
            continue
        yield date, g.reset_index(drop=True), float(thr)


if __name__ == "__main__":
    # smoke test: legs_closed count should match leg_count_es (~15 median)
    df = load_bars()
    daily = daily_table(df)
    counts = []
    for date, g, thr in iter_days(df, daily):
        legs = legs_for_day(g["Open"].to_numpy(), g["High"].to_numpy(),
                            g["Low"].to_numpy(), g["DateTime"].to_numpy(), thr)
        counts.append(sum(1 for lg in legs if lg["closed"]))
    s = pd.Series(counts)
    print(f"days={len(s)}  legs_closed median={s.median()}  mean={s.mean():.2f}")
