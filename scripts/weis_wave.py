"""weis_wave.py — Wyckoff-2.0 EFFORT lane: the Weis wave (per-swing cumulative volume).

The book's rule (S120): measure effort on SWINGS, not per bar — a 2000t bar's per-bar volume
is ~constant, so it tells you nothing; the volume it takes to make each up/down leg does.
A Weis wave segments price into alternating up/down swings (a reversal-threshold zigzag) and
sums the volume traded during each swing. Big volume on a swing that makes little price = effort
without result = the absorption/exhaustion the trigger lane looks for; a new price extreme on
SHRINKING wave volume = a Wyckoff shortening-of-thrust / divergence warning.

Built from OUR tick troves via canonical tickdata.py (RTH or ETH), or an L1 file (with delta).

    python scripts/weis_wave.py                          # latest RTH day, 2.0-pt reversal
    python scripts/weis_wave.py --day 2026-09-15 --reversal 2.5 --bar 1min
    python scripts/weis_wave.py --eth --reversal 3
    python scripts/weis_wave.py --file data/l1_tape/ES_12-26_l1_2026-09-16.csv --reversal 1

Writes a dated waves CSV + a 2-panel PNG (price with pivots · wave volume bars) to VSCode.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def to_bars(df: pd.DataFrame, bar: str) -> pd.DataFrame:
    """Resample raw ticks to base bars for a clean swing skeleton. df: DateTime, Price, Volume
    (+ optional signed for delta from an L1 file). `bar` = a pandas offset ('1min','5min') OR
    a tick-count spec ('2000t','1000t') → group every N trade prints (the true 2000-tick bar)."""
    d = df.sort_values("DateTime").reset_index(drop=True)
    if bar.endswith("t"):
        n = int(bar[:-1])
        grp = np.arange(len(d)) // n
        g = d.groupby(grp)
        out = pd.DataFrame({
            "close": g["Price"].last().values, "high": g["Price"].max().values,
            "low": g["Price"].min().values, "vol": g["Volume"].sum().values,
        }, index=g["DateTime"].last().values)
        if "signed" in d.columns:
            out["delta"] = g["signed"].sum().values
        return out
    d = d.set_index("DateTime")
    o = d["Price"].resample(bar).ohlc()
    v = d["Volume"].resample(bar).sum()
    out = pd.DataFrame({"close": o["close"], "high": o["high"], "low": o["low"], "vol": v})
    if "signed" in d.columns:
        out["delta"] = d["signed"].resample(bar).sum()
    return out.dropna(subset=["close"])


def zigzag(prices: np.ndarray, reversal: float) -> list[int]:
    """Reversal-threshold zigzag → indices of alternating swing pivots. A swing flips when
    price retraces `reversal` points from the running extreme."""
    n = len(prices)
    if n < 2:
        return list(range(n))
    piv = [0]
    trend = 0                       # 0 unknown, +1 up, -1 down
    hi = lo = prices[0]; hi_i = lo_i = 0
    for i in range(1, n):
        p = prices[i]
        if p > hi:
            hi, hi_i = p, i
        if p < lo:
            lo, lo_i = p, i
        if trend <= 0 and p >= lo + reversal:          # up-reversal off the low
            if piv[-1] != lo_i:
                piv.append(lo_i)
            trend = 1; hi, hi_i = p, i                 # start tracking the new high
        elif trend >= 0 and p <= hi - reversal:        # down-reversal off the high
            if piv[-1] != hi_i:
                piv.append(hi_i)
            trend = -1; lo, lo_i = p, i
    piv.append(hi_i if trend >= 0 else lo_i)           # final extreme
    out = []
    for x in piv:                                      # strictly increasing, unique
        if not out or x > out[-1]:
            out.append(x)
    return out


def waves(bars: pd.DataFrame, reversal: float) -> pd.DataFrame:
    prices = bars["close"].to_numpy()
    piv = zigzag(prices, reversal)
    rows = []
    for a, b in zip(piv[:-1], piv[1:]):
        seg = bars.iloc[a:b + 1]
        up = prices[b] >= prices[a]
        rows.append({
            "t_start": bars.index[a], "t_end": bars.index[b],
            "dir": "up" if up else "dn",
            "p_start": round(float(prices[a]), 2), "p_end": round(float(prices[b]), 2),
            "move": round(float(prices[b] - prices[a]), 2),
            "vol": int(seg["vol"].sum()),
            "delta": int(seg["delta"].sum()) if "delta" in bars.columns else None,
            "bars": int(b - a),
        })
    w = pd.DataFrame(rows)
    if not w.empty:
        # effort/result: volume per point of swing — high = grinding (absorption), low = easy move
        w["vol_per_pt"] = (w["vol"] / w["move"].abs().replace(0, np.nan)).round(0)
    return w


def chart(bars: pd.DataFrame, w: pd.DataFrame, title: str, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (axp, axv) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    fig.suptitle(title, fontsize=11)
    axp.plot(bars.index, bars["close"], color="#888", lw=0.7, alpha=0.6)
    # zigzag skeleton through the pivots
    px = list(w["t_start"]) + [w["t_end"].iloc[-1]] if not w.empty else []
    py = list(w["p_start"]) + [w["p_end"].iloc[-1]] if not w.empty else []
    axp.plot(px, py, color="#1f77b4", lw=1.4, marker="o", ms=3)
    axp.set_ylabel("price"); axp.grid(alpha=0.2)

    for _, r in w.iterrows():
        col = "#2ca02c" if r["dir"] == "up" else "#d62728"
        axv.plot([r["t_end"], r["t_end"]], [0, r["vol"]], color=col, lw=4, solid_capstyle="butt")
        axv.annotate(f"{r['vol']/1000:.0f}k", (r["t_end"], r["vol"]), fontsize=6,
                     ha="center", va="bottom", color=col)
    axv.set_ylabel("wave volume"); axv.set_xlabel("time"); axv.grid(alpha=0.2)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.98]); fig.savefig(path, dpi=110); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--eth", action="store_true")
    ap.add_argument("--file", default=None, help="an L1 CSV/parquet instead of the trove (adds delta)")
    ap.add_argument("--reversal", type=float, default=2.0, help="swing reversal amount in points")
    ap.add_argument("--bar", default="1min", help="base resample bar")
    a = ap.parse_args()

    if a.file:
        p = Path(a.file)
        raw = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
        raw = raw[raw["Ev"] == "T"].copy() if "Ev" in raw.columns else raw
        raw["DateTime"] = pd.to_datetime(raw["Time" if "Time" in raw.columns else "DateTime"])
        if "Aggr" in raw.columns:
            raw["signed"] = np.where(raw["Aggr"].astype(str) == "A", raw["Volume"], -raw["Volume"])
        label = f"{p.stem} (L1)"; stamp = f"weis_{p.stem}_{a.bar}"
    else:
        day = a.day or td.available("eth" if a.eth else "rth")[-1]
        raw = td.load_eth(day) if a.eth else td.load_rth(day)
        label = f"{day} ({'ETH' if a.eth else 'RTH'})"; stamp = f"weis_{day}_{'eth' if a.eth else 'rth'}_{a.bar}"

    bars = to_bars(raw, a.bar)
    w = waves(bars, a.reversal)
    if w.empty:
        print("no swings found — try a smaller --reversal"); return 1

    OUT.mkdir(parents=True, exist_ok=True)
    csv = OUT / f"{stamp}_r{a.reversal}.csv"; w.to_csv(csv, index=False)
    png = OUT / f"{stamp}_r{a.reversal}.png"; chart(bars, w, f"Weis wave — {label}  (reversal {a.reversal}pt)", png)

    up, dn = w[w["dir"] == "up"], w[w["dir"] == "dn"]
    print(f"\nWeis wave — {label}  ·  reversal {a.reversal}pt  ·  {len(w)} swings "
          f"({len(up)} up / {len(dn)} dn)")
    print(f"  up-wave vol total {up['vol'].sum():,}  |  dn-wave vol total {dn['vol'].sum():,}")
    show = w.copy()
    show["t"] = show["t_start"].dt.strftime("%H:%M")
    cols = ["t", "dir", "p_start", "p_end", "move", "vol", "vol_per_pt"] + (["delta"] if "delta" in w.columns and w["delta"].notna().any() else [])
    with pd.option_context("display.max_rows", 80, "display.width", 160):
        print(show[cols].to_string(index=False))
    print(f"\nwaves: {csv}\nchart: {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
