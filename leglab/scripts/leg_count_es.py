"""
Leg-counting study — reproduces Tim's zentradingtech "leg counting" analysis on ES.

Article: https://zentradingtech.com/2026/09/06/not-another-post-on-leg-counting/
It is a market-STRUCTURE study (not a strategy): walk each RTH day bar-by-bar from
the open, track the running extreme; when price reverses off that extreme by more
than a threshold, the current leg closes and a new one starts. Count legs/day.

Design (confirmed with user, S111):
  1. Reversal measured on intrabar HIGH/LOW (not close).
  2. Threshold = 0.15 * ADR, ADR = mean of the prior 8 RTH daily ranges
     (high-low), recomputed each day, fixed for that day.
  3. RTH only; leg count RESETS each morning at the open.

Data: data/bars/_db_es_5m_rth.parquet  (5M ES RTH OHLCV, 2010-06 -> 2026-07).

Outputs (dated):
  data/research/leg_count_es_5m_<YYYYMMDD>.csv       per-day legs + context
  data/research/leg_count_es_summary_<YYYYMMDD>.txt  summary stats
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "data" / "bars" / "_db_es_5m_rth.parquet"
OUTDIR = ROOT / "leglab" / "outputs"
OUTDIR.mkdir(parents=True, exist_ok=True)
RUN_DATE = "20260906"  # machine date; keep dated per persist rule

ADR_LOOKBACK = 8
THRESH_FRAC = 0.15


def count_legs(highs, lows, thr):
    """Directional zigzag on HL bars. Returns (legs_closed, legs_total, n_pivots).

    legs_closed = legs completed by a threshold reversal.
    legs_total  = legs_closed + 1 for the final in-progress leg (if direction set).
    """
    n = len(highs)
    if n == 0:
        return 0, 0, 0
    direction = 0          # +1 up leg, -1 down leg, 0 not yet established
    pivot_hi = highs[0]
    pivot_lo = lows[0]
    legs_closed = 0
    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        if direction == 1:
            if h >= pivot_hi:
                pivot_hi = h
            elif (pivot_hi - l) >= thr:      # reversal down -> up leg closes
                legs_closed += 1
                direction = -1
                pivot_lo = l
        elif direction == -1:
            if l <= pivot_lo:
                pivot_lo = l
            elif (h - pivot_lo) >= thr:       # reversal up -> down leg closes
                legs_closed += 1
                direction = 1
                pivot_hi = h
        else:  # direction == 0, bootstrap first leg
            pivot_hi = max(pivot_hi, h)
            pivot_lo = min(pivot_lo, l)
            # whichever side breaks the threshold first sets the initial leg
            down_rev = (pivot_hi - l) >= thr
            up_rev = (h - pivot_lo) >= thr
            if down_rev and not up_rev:
                legs_closed += 1
                direction = -1
                pivot_lo = l
            elif up_rev and not down_rev:
                legs_closed += 1
                direction = 1
                pivot_hi = h
            elif up_rev and down_rev:
                # both in one bar: use net bar direction as tie-break
                if (highs[i] - highs[i - 1]) >= (lows[i - 1] - lows[i]):
                    legs_closed += 1
                    direction = 1
                    pivot_hi = h
                else:
                    legs_closed += 1
                    direction = -1
                    pivot_lo = l
    legs_total = legs_closed + (1 if direction != 0 else 0)
    n_pivots = legs_closed + 1 if direction != 0 else 0
    return legs_closed, legs_total, n_pivots


def main():
    df = pd.read_parquet(BARS)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["date"] = df["DateTime"].dt.date

    # per-day RTH range for ADR
    daily = df.groupby("date").agg(
        d_open=("Open", "first"),
        d_close=("Close", "last"),
        d_high=("High", "max"),
        d_low=("Low", "min"),
        n_bars=("Close", "size"),
    )
    daily["d_range"] = daily["d_high"] - daily["d_low"]
    daily["adr"] = daily["d_range"].shift(1).rolling(ADR_LOOKBACK).mean()
    daily["thr"] = THRESH_FRAC * daily["adr"]
    daily["net"] = daily["d_close"] - daily["d_open"]

    rows = []
    for date, g in df.groupby("date"):
        thr = daily.loc[date, "thr"]
        if not np.isfinite(thr) or thr <= 0:
            continue  # need 8 prior days for ADR
        closed, total, piv = count_legs(
            g["High"].to_numpy(), g["Low"].to_numpy(), float(thr)
        )
        rows.append({
            "date": date,
            "n_bars": int(daily.loc[date, "n_bars"]),
            "adr": round(float(daily.loc[date, "adr"]), 4),
            "thr": round(float(thr), 4),
            "d_range": round(float(daily.loc[date, "d_range"]), 4),
            "net": round(float(daily.loc[date, "net"]), 4),
            "legs_closed": closed,
            "legs_total": total,
        })

    out = pd.DataFrame(rows)
    out["year"] = pd.to_datetime(out["date"]).dt.year
    csv_path = OUTDIR / f"leg_count_es_5m_{RUN_DATE}.csv"
    out.to_csv(csv_path, index=False)

    # ---- summary ----
    lines = []
    def p(s=""):
        lines.append(s)
        print(s)

    p(f"Leg-count study — ES 5M RTH  (0.15*ADR, 8d ADR, HL reversals)")
    p(f"rows written: {len(out)}   -> {csv_path}")
    p(f"span: {out['date'].min()} -> {out['date'].max()}")
    p("")
    for col in ["legs_total", "legs_closed"]:
        p(f"{col}: median={out[col].median():.1f}  mean={out[col].mean():.2f}  "
          f"p10={out[col].quantile(.1):.0f}  p90={out[col].quantile(.9):.0f}")
    p("")

    # Tim's window 2021-08 -> 2026-07
    tim = out[(out["date"] >= pd.to_datetime("2021-08-01").date())
              & (out["date"] <= pd.to_datetime("2026-09-30").date())]
    p(f"TIM WINDOW 2021-08+ (n={len(tim)}): "
      f"legs_total median={tim['legs_total'].median():.1f} mean={tim['legs_total'].mean():.2f} | "
      f"legs_closed median={tim['legs_closed'].median():.1f} mean={tim['legs_closed'].mean():.2f}")
    p("")

    p("legs_total median by year:")
    by = out.groupby("year")["legs_total"].agg(["median", "mean", "size"])
    p(by.to_string())
    p("")

    # day-type buckets by net move (quintiles): extreme-down .. extreme-up
    out["net_q"] = pd.qcut(out["net"], 5, labels=["ext_down", "down", "flat", "up", "ext_up"])
    p("legs_total by net-move quintile (Tim: ext-down~18, ext-up~12):")
    bt = out.groupby("net_q", observed=True)["legs_total"].agg(["median", "mean", "size"])
    p(bt.to_string())

    txt_path = OUTDIR / f"leg_count_es_summary_{RUN_DATE}.txt"
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsummary -> {txt_path}")


if __name__ == "__main__":
    main()
