"""bid_ask_volume_ratio_l1.py — Sierra Chart "Bid Ask Volume Ratio" study, computed OFFLINE
from our recorded L1 tape, since the NT8 port (nt8/indicators/BidAskVolumeRatio.cs) can only
run forward from when it's live on a connected feed — OnMarketData does not replay history,
even against our own recorded data, on an NT8 chart. This script computes the identical
formula directly from data/l1_tape/*, which already carries per-trade aggressor tagging
(same classification l1_footprint.py uses, validated exact vs MzPack).

FORMULA (verified against sierrachart.com doc/StudiesReference.php?ID=230, same as the NT8
port): per bar, VR = 100 x (AskVol-BidVol)/(AskVol+BidVol) [or reversed sign], 0 bars have
denom 0; then a Moving Average over `--length` bars, type selectable to match Sierra's 6:
simple / exponential / weighted / linreg / wilders / smoothed (wilders==smoothed formula).

ES ONLY — the L1 recorder has never run on NQ. Coverage: data/l1_tape/ES*_l1_*.{csv,parquet},
2026-09-16 onward.

    python scripts/bid_ask_volume_ratio_l1.py --from 2026-10-01 --to 2026-10-15
    python scripts/bid_ask_volume_ratio_l1.py --from 2026-10-01 --to 2026-10-15 --bar 1min --ma wilders --length 20
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
from l1_footprint import load, bar_key

L1_DIR = ROOT / "data" / "l1_tape"
OUT = L1_DIR / "_analysis"


def load_range(d_from: str, d_to: str) -> pd.DataFrame:
    cands = sorted(L1_DIR.glob("ES*_l1_*.csv")) + sorted(L1_DIR.glob("ES*_l1_*.parquet"))
    # one file per day per format (csv+parquet both exist for most days) -- keep parquet, it's
    # the same data, just dedupe by date stem so we don't double-count a day.
    by_date: dict[str, Path] = {}
    for p in cands:
        date = p.stem.split("_l1_")[-1]
        if d_from <= date <= d_to:
            if date not in by_date or p.suffix == ".parquet":
                by_date[date] = p
    if not by_date:
        raise SystemExit(f"no L1 files found for {d_from}..{d_to} in {L1_DIR}")
    frames = [load(by_date[d]) for d in sorted(by_date)]
    print(f"loaded {len(frames)} day(s): {sorted(by_date)[0]} .. {sorted(by_date)[-1]}")
    return pd.concat(frames, ignore_index=True)


def compute(df: pd.DataFrame, bar: str, length: int, ma: str, sign: int) -> pd.DataFrame:
    tape = df[df["Ev"] == "T"].sort_values("Time").reset_index(drop=True)
    if tape.empty:
        raise SystemExit("no tape (T) rows in range")
    tape["Size"] = tape["Size"].astype("int64")
    tape["ask"] = tape["Aggr"].astype(str).eq("A") * tape["Size"]
    tape["bid"] = tape["Aggr"].astype(str).eq("B") * tape["Size"]
    tape["bar"] = bar_key(tape, bar)

    g = tape.groupby("bar", sort=True)
    b = pd.DataFrame({
        "t_start": g["Time"].first(),
        "close":   g["Price"].last(),
        "askVol":  g["ask"].sum(),
        "bidVol":  g["bid"].sum(),
    }).reset_index(drop=True)

    denom = b["askVol"] + b["bidVol"]
    b["raw_vr"] = np.where(denom > 0, 100.0 * sign * (b["askVol"] - b["bidVol"]) / denom, 0.0)
    b["ma_vr"] = smooth(b["raw_vr"].to_numpy(), length, ma)
    return b


def smooth(raw: np.ndarray, length: int, kind: str) -> np.ndarray:
    n = len(raw)
    out = np.zeros(n)
    if kind == "simple":
        for i in range(n):
            lo = max(0, i - length + 1)
            out[i] = raw[lo:i + 1].mean()
    elif kind == "weighted":
        for i in range(n):
            lo = max(0, i - length + 1)
            window = raw[lo:i + 1]
            w = np.arange(1, len(window) + 1)
            out[i] = np.sum(window * w) / w.sum()
    elif kind == "linreg":
        for i in range(n):
            lo = max(0, i - length + 1)
            window = raw[lo:i + 1]
            m = len(window)
            if m == 1:
                out[i] = window[0]
                continue
            x = np.arange(m)
            slope, intercept = np.polyfit(x, window, 1)
            out[i] = intercept + slope * (m - 1)
    else:   # exponential / wilders / smoothed -- recursive, same shape as the NT8 port
        alpha = 2.0 / (length + 1.0) if kind == "exponential" else 1.0 / length
        out[0] = raw[0]
        for i in range(1, n):
            out[i] = out[i - 1] + alpha * (raw[i] - out[i - 1])
    return out


def chart(b: pd.DataFrame, bar: str, ma: str, length: int, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(b)
    fig, (axp, axv) = plt.subplots(2, 1, figsize=(max(13, n * 0.02), 7.5), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1.2]})
    fig.suptitle(f"Bid Ask Volume Ratio (L1, ES)  ·  {bar} bars  ·  {ma} MA({length})"
                 f"  ·  {b['t_start'].iloc[0]:%Y-%m-%d} → {b['t_start'].iloc[-1]:%Y-%m-%d}", fontsize=11)

    axp.plot(range(n), b["close"].values, color="#1f77b4", lw=0.8)
    axp.set_ylabel("ES close"); axp.grid(alpha=0.2)

    axv.plot(range(n), b["ma_vr"].values, color="#d62728", lw=1.1, label=f"{ma} MA({length})")
    axv.plot(range(n), b["raw_vr"].values, color="#888", lw=0.4, alpha=0.5, label="raw VR")
    axv.axhline(0, color="#888", lw=0.7)
    axv.set_ylim(-105, 105)
    axv.set_ylabel("VR  (+ask dominant / -bid dominant)")
    axv.grid(alpha=0.2); axv.legend(loc="upper left", fontsize=8)

    step = max(1, n // 40)
    ticks = list(range(0, n, step))
    axv.set_xticks(ticks)
    axv.set_xticklabels([b["t_start"].iloc[i].strftime("%m-%d %H:%M") for i in ticks], rotation=90, fontsize=7)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="d_to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--bar", default="5min", help="bar size: 1min / 5min / 2000t")
    ap.add_argument("--length", type=int, default=14)
    ap.add_argument("--ma", default="exponential",
                     choices=["simple", "exponential", "weighted", "linreg", "wilders", "smoothed"])
    ap.add_argument("--sign", default="ask_minus_bid", choices=["ask_minus_bid", "bid_minus_ask"])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    df = load_range(a.d_from, a.d_to)
    sign = 1 if a.sign == "ask_minus_bid" else -1
    b = compute(df, a.bar, a.length, a.ma, sign)

    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    stamp = f"{a.d_from}_{a.d_to}_{a.bar}_{a.ma}{a.length}"
    csv_out = outdir / f"bavr_{stamp}.csv"
    b.to_csv(csv_out, index=False)
    png_out = outdir / f"bavr_{stamp}.png"
    chart(b, a.bar, a.ma, a.length, png_out)

    print(f"\n{len(b)} bars, {a.bar}, {a.ma} MA({a.length}), sign={a.sign}")
    print(f"raw VR:  mean={b['raw_vr'].mean():+.2f}  min={b['raw_vr'].min():+.2f}  max={b['raw_vr'].max():+.2f}")
    print(f"MA VR:   mean={b['ma_vr'].mean():+.2f}  min={b['ma_vr'].min():+.2f}  max={b['ma_vr'].max():+.2f}")
    print(f"\nsaved: {csv_out}")
    print(f"chart: {png_out}")
    try:
        subprocess.Popen(["code", "-r", str(png_out)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
