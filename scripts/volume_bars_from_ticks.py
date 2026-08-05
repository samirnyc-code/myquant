"""
Constant-volume bars (e.g. 6500V) from continuous ES tick data.

Source: data/ticks_continuous/<YYYY-MM-DD>.parquet  (cols: DateTime, Price, Volume)
A new bar closes every time cumulative traded volume reaches VOL_PER_BAR.
A tick that would cross the boundary is SPLIT so each bar holds exactly
VOL_PER_BAR contracts (except possibly the last, partial bar of the day).

Outputs (dated):
  data/bars/volume_bars/ES_<DATE>_<VOL>V_bars.csv   -- the OHLCV bars
  reports/volume_bars/ES_<DATE>_<VOL>V.png          -- candlestick chart

Usage:
  python scripts/volume_bars_from_ticks.py                 # latest day, 6500V
  python scripts/volume_bars_from_ticks.py 2026-07-09 6500
"""
import sys, glob, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

TICK_DIR = "data/ticks_continuous"


def latest_date():
    fs = sorted(glob.glob(f"{TICK_DIR}/*.parquet"))
    return os.path.basename(fs[-1])[:10]


def build_volume_bars(df, vol_per_bar):
    """df: DateTime, Price, Volume (per-trade). Returns OHLCV bars of size vol_per_bar."""
    dt = df["DateTime"].to_numpy()
    px = df["Price"].to_numpy(dtype="float64")
    vol = df["Volume"].to_numpy(dtype="int64")

    bars = []
    cur_o = cur_h = cur_l = cur_c = None
    cur_start = None
    filled = 0  # volume accumulated in current bar

    for i in range(len(px)):
        p = px[i]
        v = vol[i]
        t = dt[i]
        while v > 0:
            if cur_o is None:
                cur_o = cur_h = cur_l = cur_c = p
                cur_start = t
                filled = 0
            cur_h = max(cur_h, p)
            cur_l = min(cur_l, p)
            cur_c = p
            take = min(v, vol_per_bar - filled)
            filled += take
            v -= take
            if filled >= vol_per_bar:
                bars.append((cur_start, t, cur_o, cur_h, cur_l, cur_c, filled))
                cur_o = None  # start fresh on next tick/remainder
    if cur_o is not None:  # trailing partial bar
        bars.append((cur_start, dt[-1], cur_o, cur_h, cur_l, cur_c, filled))

    return pd.DataFrame(bars, columns=["start", "end", "open", "high", "low", "close", "volume"])


def plot_bars(bars, date, vol_per_bar, out_png):
    n = len(bars)
    x = np.arange(n)
    up = bars["close"].to_numpy() >= bars["open"].to_numpy()
    o, h, l, c = (bars[k].to_numpy() for k in ("open", "high", "low", "close"))

    fig, ax = plt.subplots(figsize=(max(12, n * 0.06), 7), dpi=130)
    w = 0.7
    for i in range(n):
        col = "#26a69a" if up[i] else "#ef5350"
        ax.plot([x[i], x[i]], [l[i], h[i]], color=col, linewidth=0.6, zorder=1)
        lo = min(o[i], c[i]); hi = max(o[i], c[i])
        ax.add_patch(Rectangle((x[i] - w / 2, lo), w, max(hi - lo, 0.01),
                               facecolor=col, edgecolor=col, linewidth=0.3, zorder=2))

    # hourly gridlines from bar end-times
    ends = pd.to_datetime(bars["end"])
    hour = ends.dt.floor("h")
    marks = hour.ne(hour.shift()).to_numpy()
    for i in np.where(marks)[0]:
        ax.axvline(i, color="#888", alpha=0.18, linewidth=0.7, zorder=0)
        ax.text(i, ax.get_ylim()[0], ends.iloc[i].strftime("%H:%M"),
                fontsize=7, color="#555", rotation=0, va="bottom", ha="left")

    ax.set_title(f"ES  {date}  —  {vol_per_bar:,}V constant-volume bars  ({n} bars)", fontsize=12)
    ax.set_ylabel("Price")
    ax.set_xlabel("bar #  (each = {:,} contracts)  ·  times = machine tz".format(vol_per_bar))
    ax.margins(x=0.005)
    ax.grid(axis="y", alpha=0.15)
    fig.tight_layout()
    fig.savefig(out_png)
    print(f"saved chart: {out_png}")


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else latest_date()
    vol_per_bar = int(sys.argv[2]) if len(sys.argv) > 2 else 6500

    path = f"{TICK_DIR}/{date}.parquet"
    df = pd.read_parquet(path).sort_values("DateTime").reset_index(drop=True)
    print(f"loaded {len(df):,} ticks  {df['DateTime'].min()} -> {df['DateTime'].max()}")
    print(f"total volume: {int(df['Volume'].sum()):,}")

    bars = build_volume_bars(df, vol_per_bar)
    print(f"built {len(bars)} bars of {vol_per_bar:,}V each")

    os.makedirs("data/bars/volume_bars", exist_ok=True)
    os.makedirs("reports/volume_bars", exist_ok=True)
    out_csv = f"data/bars/volume_bars/ES_{date}_{vol_per_bar}V_bars.csv"
    out_png = f"reports/volume_bars/ES_{date}_{vol_per_bar}V.png"
    bars.to_csv(out_csv, index=False)
    print(f"saved bars: {out_csv}")

    plot_bars(bars, date, vol_per_bar, out_png)
    print("\nfirst 3 bars:\n", bars.head(3).to_string())
    print("\nlast 3 bars:\n", bars.tail(3).to_string())


if __name__ == "__main__":
    main()
