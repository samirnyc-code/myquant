"""bid_ask_volume_ratio_renko.py — Bid Ask Volume Ratio computed PER FLEX RENKO BRICK
(not a fixed time bar), one RTH day at a time, rendered Sierra-Chart-style (dark theme,
price bricks on top / ratio oscillator below) to match the reference screenshot.

Bricks built from the L1 tape's own trades (data/l1_tape/*, ES only) via the already-
verified scripts/renko.py::flex_renko, same box/trend/reversal convention as the NT8
FlexRenkoBarsType port: "ES 16/8004" = Value=16 (box, real 0.25-tick ES), Value2=8004
(TrendOffset=8, ReversalOffset=4) -> box=16 ticks=4pt, trend=8 ticks=2pt, rev=4 ticks=1pt.

For each completed brick, the window of trades from the PRIOR brick's completion to THIS
brick's completion is classified Aggr A (ask-side)/B (bid-side) -- same classification
l1_footprint.py / bid_ask_volume_ratio_l1.py use -- giving that brick's AskVol/BidVol, then
the same verified Sierra formula + MA smoothing (bid_ask_volume_ratio_l1.smooth()).

    python scripts/bid_ask_volume_ratio_renko.py --day 2026-10-14
    python scripts/bid_ask_volume_ratio_renko.py --day 2026-10-14 --ma wilders --length 20
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from renko import flex_renko
from bid_ask_volume_ratio_l1 import smooth

L1_DIR = ROOT / "data" / "l1_tape"
OUT = L1_DIR / "_analysis"

RTH_START, RTH_END = "08:30", "15:15"   # CT, matches tickdata.py's RTH_TROVE window


def load_day(day: str) -> pd.DataFrame:
    p = L1_DIR / f"ES_12-26_l1_{day}.parquet"
    if not p.exists() or p.stat().st_size < 1_000_000:
        p = L1_DIR / f"ES_12-26_l1_{day}.csv"
    if not p.exists():
        raise SystemExit(f"no L1 file for {day} in {L1_DIR}")
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, low_memory=False)
    df["Time"] = pd.to_datetime(df["Time"])
    if len(df) < 10_000:
        raise SystemExit(f"{p.name} only has {len(df)} rows -- looks like a stub, not the full day")
    print(f"loaded {p.name}: {len(df):,} rows, {df['Time'].min()} -> {df['Time'].max()}")
    return df


def rth_only(df: pd.DataFrame, day: str) -> pd.DataFrame:
    d = pd.Timestamp(day)
    lo = d + pd.Timedelta(RTH_START + ":00")
    hi = d + pd.Timedelta(RTH_END + ":00")
    out = df[(df["Time"] >= lo) & (df["Time"] <= hi)].reset_index(drop=True)
    if out.empty:
        raise SystemExit(f"no RTH rows for {day} ({RTH_START}-{RTH_END} CT)")
    print(f"RTH slice: {len(out):,} rows, {out['Time'].min()} -> {out['Time'].max()}")
    return out


def build(df: pd.DataFrame, box: int, trend: int, rev: int, length: int, ma: str, sign: int):
    tape = df[df["Ev"] == "T"].sort_values("Time").reset_index(drop=True)
    tape["Size"] = tape["Size"].astype("int64")

    # flex_renko wants DateTime/Price/Volume
    renko_in = tape.rename(columns={"Time": "DateTime", "Size": "Volume"})
    R = flex_renko(renko_in, box, trend, rev, tick=0.25)
    if R.empty:
        raise SystemExit("no bricks produced for this day/session")

    R["open"]  = np.where(R["dir"] == "up", R["bottom"], R["top"])
    R["close"] = np.where(R["dir"] == "up", R["top"], R["bottom"])
    R["high"]  = R["whi"]
    R["low"]   = R["wlo"]

    # per-brick ask/bid volume: trades strictly after the PRIOR brick's time, up to and
    # including this brick's time (mirrors how the brick's own wick excursion is windowed)
    ask_s = tape["Aggr"].eq("A") * tape["Size"]
    bid_s = tape["Aggr"].eq("B") * tape["Size"]
    t_edges = [tape["Time"].iloc[0]] + list(R["t"])
    askVol, bidVol = [], []
    for i in range(len(R)):
        lo, hi = t_edges[i], t_edges[i + 1]
        m = (tape["Time"] > lo) & (tape["Time"] <= hi)
        askVol.append(int(ask_s[m].sum()))
        bidVol.append(int(bid_s[m].sum()))
    R["askVol"] = askVol
    R["bidVol"] = bidVol

    denom = R["askVol"] + R["bidVol"]
    R["raw_vr"] = np.where(denom > 0, 100.0 * sign * (R["askVol"] - R["bidVol"]) / denom, 0.0)
    R["ma_vr"] = smooth(R["raw_vr"].to_numpy(), length, ma)
    return R.reset_index(drop=True)


def chart(R: pd.DataFrame, day: str, box: int, trend: int, rev: int, ma: str, length: int, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.style.use("dark_background")
    n = len(R)
    fig, (axp, axv) = plt.subplots(2, 1, figsize=(max(14, n * 0.09), 8), sharex=True,
                                    gridspec_kw={"height_ratios": [2.3, 1]})
    fig.patch.set_facecolor("black")
    fig.suptitle(f"ES {day} RTH  ·  Flex Renko {box}-{trend}-{rev}  ·  Bid Ask Volume Ratio {ma} MA({length})",
                 fontsize=11, color="white")

    # bricks, Sierra-style: up = blue (DodgerBlue-like), down = white
    up_c, dn_c = "#2f6fed", "#f2f2f2"
    for i, r in R.iterrows():
        c = up_c if r["dir"] == "up" else dn_c
        axp.plot([i, i], [r["low"], r["high"]], color=c, lw=0.8, zorder=2)
        blo, bhi = min(r["open"], r["close"]), max(r["open"], r["close"])
        axp.add_patch(Rectangle((i - 0.35, blo), 0.70, max(bhi - blo, 0.01),
                                 facecolor=c, edgecolor=c, lw=0.3, zorder=3))
    axp.set_xlim(-1, n)
    axp.set_ylabel("ES", color="white")
    axp.grid(alpha=0.15, color="gray")
    axp.tick_params(colors="white")

    axv.plot(range(n), R["ma_vr"].values, color="#2f6fed", lw=1.3, label=f"{ma} MA({length})")
    axv.plot(range(n), R["raw_vr"].values, color="#888", lw=0.4, alpha=0.6, label="raw VR")
    axv.axhline(0, color="#888", lw=0.7)
    axv.set_ylim(-105, 105)
    axv.set_ylabel("VR", color="white")
    axv.grid(alpha=0.15, color="gray")
    axv.legend(loc="upper left", fontsize=8, facecolor="black", labelcolor="white")
    axv.tick_params(colors="white")

    step = max(1, n // 30)
    ticks = list(range(0, n, step))
    axv.set_xticks(ticks)
    axv.set_xticklabels([R["t"].iloc[i].strftime("%H:%M") for i in ticks], rotation=90, fontsize=7, color="white")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=115, bbox_inches="tight", facecolor="black")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="YYYY-MM-DD (trading day)")
    ap.add_argument("--box", type=int, default=16)
    ap.add_argument("--trend", type=int, default=8)
    ap.add_argument("--rev", type=int, default=4)
    ap.add_argument("--length", type=int, default=14)
    ap.add_argument("--ma", default="exponential",
                     choices=["simple", "exponential", "weighted", "linreg", "wilders", "smoothed"])
    ap.add_argument("--sign", default="ask_minus_bid", choices=["ask_minus_bid", "bid_minus_ask"])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    df = load_day(a.day)
    rth = rth_only(df, a.day)
    sign = 1 if a.sign == "ask_minus_bid" else -1
    R = build(rth, a.box, a.trend, a.rev, a.length, a.ma, sign)

    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    stamp = f"{a.day}_renko{a.box}-{a.trend}-{a.rev}_{a.ma}{a.length}"
    csv_out = outdir / f"bavr_renko_{stamp}.csv"
    R.drop(columns=["bottom", "top"]).to_csv(csv_out, index=False)
    png_out = outdir / f"bavr_renko_{stamp}.png"
    chart(R, a.day, a.box, a.trend, a.rev, a.ma, a.length, png_out)

    print(f"\n{len(R)} bricks, box={a.box} trend={a.trend} rev={a.rev} ({a.box*0.25}pt box)")
    print(f"raw VR:  mean={R['raw_vr'].mean():+.2f}  min={R['raw_vr'].min():+.2f}  max={R['raw_vr'].max():+.2f}")
    print(f"MA VR:   mean={R['ma_vr'].mean():+.2f}  min={R['ma_vr'].min():+.2f}  max={R['ma_vr'].max():+.2f}")
    print(f"\nsaved: {csv_out}")
    print(f"chart: {png_out}")
    try:
        import subprocess
        subprocess.Popen(["code", "-r", str(png_out)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
