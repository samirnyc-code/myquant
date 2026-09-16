"""volume_profile.py — Wyckoff-2.0 Stage 1: the LOCATION lane.

Computes the Volume Profile levels the discretionary system trades AT — from OUR OWN tick
troves via the canonical `tickdata.py` (never any other tick source; memory canonical-tick-data):

  VPOC        price with the most traded volume (the fair-value magnet)
  VA hi/lo    value area = the central 70% of volume around the VPOC
  HVN / LVN   high/low volume nodes = acceptance shelves / rejection gaps (peaks/troughs
              in the volume-at-price curve). LVNs are where stops go + where breakouts run.
  naked VPOC  a prior session's VPOC that price has NOT revisited since — an untested magnet
  bias line   the last-developed HVN: price above it = long bias, below = short (the book's rule)

Modes: single session, composite (multi-day), fixed range. VP is bar-agnostic (built from
raw ticks) so the same levels hold on any chart timeframe.

    python scripts/volume_profile.py                       # latest RTH day, chart + levels
    python scripts/volume_profile.py --day 2026-09-15 --eth
    python scripts/volume_profile.py --from 2026-09-01 --to 2026-09-15   # composite
    python scripts/volume_profile.py --day 2026-09-15 --naked-lookback 20 # + naked VPOCs

Writes a dated levels JSON (for the NT8 drawer to read) + a profile PNG (opened in VSCode).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td

TICK = 0.25            # ES tick size
OUT = ROOT / "data" / "l1_tape" / "_analysis"


def volume_at_price(df: pd.DataFrame, tick: float = TICK) -> pd.Series:
    """Sum traded volume into price bins of one tick. Index = price, value = volume."""
    if df.empty:
        return pd.Series(dtype="int64")
    binned = (np.round(df["Price"] / tick) * tick).round(2)
    vap = df.groupby(binned)["Volume"].sum().sort_index()
    # fill missing price levels with 0 so peak/trough detection sees a continuous ladder
    full = np.round(np.arange(vap.index.min(), vap.index.max() + tick, tick) / tick) * tick
    return vap.reindex(np.round(full, 2), fill_value=0)


def value_area(vap: pd.Series, pct: float = 0.70):
    """VPOC + the central `pct` of volume. Greedy single-level expansion from the POC:
    at each step take whichever adjacent level (above or below) holds more volume, until
    the accumulated volume reaches `pct` of the total — the standard volume-VA method."""
    prices = vap.index.to_numpy()
    vol = vap.to_numpy(dtype="float64")
    total = vol.sum()
    poc_i = int(vol.argmax())
    target = pct * total
    lo = hi = poc_i
    acc = vol[poc_i]
    n = len(vol)
    while acc < target and (lo > 0 or hi < n - 1):
        up = vol[hi + 1] if hi < n - 1 else -1.0
        dn = vol[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1; acc += vol[hi]
        else:
            lo -= 1; acc += vol[lo]
    return float(prices[poc_i]), float(prices[lo]), float(prices[hi])


def nodes(vap: pd.Series, prominence_frac: float = 0.10):
    """HVN (volume peaks) and LVN (volume troughs) in the volume-at-price curve.
    prominence gate = fraction of the max level, so only meaningful shelves/gaps qualify."""
    vol = vap.to_numpy(dtype="float64")
    prices = vap.index.to_numpy()
    if len(vol) < 3:
        return [], []
    prom = prominence_frac * vol.max()
    try:
        from scipy.signal import find_peaks
        hp, _ = find_peaks(vol, prominence=prom)
        lp, _ = find_peaks(vol.max() - vol, prominence=prom)
    except Exception:                                   # scipy-free fallback: local extrema
        hp = [i for i in range(1, len(vol) - 1) if vol[i] > vol[i-1] and vol[i] >= vol[i+1]
              and vol[i] - min(vol[max(0,i-3):i+4]) >= prom]
        lp = [i for i in range(1, len(vol) - 1) if vol[i] < vol[i-1] and vol[i] <= vol[i+1]
              and max(vol[max(0,i-3):i+4]) - vol[i] >= prom]
    hvn = sorted(round(float(prices[i]), 2) for i in hp)
    lvn = sorted(round(float(prices[i]), 2) for i in lp)
    return hvn, lvn


def build(df: pd.DataFrame, pct: float = 0.70) -> dict:
    vap = volume_at_price(df)
    vpoc, va_lo, va_hi = value_area(vap, pct)
    hvn, lvn = nodes(vap)
    # last-developed HVN = the HVN nearest the session close (the current acceptance shelf)
    close = float(df["Price"].iloc[-1])
    bias_hvn = min(hvn, key=lambda p: abs(p - close)) if hvn else vpoc
    return dict(vpoc=vpoc, va_low=va_lo, va_high=va_hi, hvn=hvn, lvn=lvn,
                bias_hvn=bias_hvn, close=close,
                hi=float(df["Price"].max()), lo=float(df["Price"].min()),
                total_vol=int(df["Volume"].sum()), _vap=vap)


def naked_vpocs(end_day: str, lookback: int, eth: bool) -> list[dict]:
    """Prior-session VPOCs that price has NOT revisited since they formed = untested magnets.
    For each of the `lookback` days before end_day, compute its VPOC, then mark it naked if
    no LATER day's [low,high] range covers it."""
    days = [d for d in td.available("eth" if eth else "rth") if d < end_day][-lookback:]
    if not days:
        return []
    frames = {d: (td.load_eth(d) if eth else td.load_rth(d)) for d in days}
    vpocs = []
    for d in days:
        vap = volume_at_price(frames[d])
        vpocs.append((d, float(vap.idxmax())))
    out = []
    for i, (d, vp) in enumerate(vpocs):
        touched = False
        for d2 in days[i + 1:]:
            f = frames[d2]
            if f["Price"].min() <= vp <= f["Price"].max():
                touched = True; break
        if not touched:
            out.append({"date": d, "vpoc": round(vp, 2)})
    return out


def chart(res: dict, title: str, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vap = res["_vap"]
    prices = vap.index.to_numpy()
    vol = vap.to_numpy()
    fig, ax = plt.subplots(figsize=(9, 11))
    inva = (prices >= res["va_low"]) & (prices <= res["va_high"])
    ax.barh(prices, vol, height=TICK * 0.9, color=np.where(inva, "#4C78A8", "#B7C7DC"))
    ax.axhline(res["vpoc"], color="#E45756", lw=2, label=f"VPOC {res['vpoc']:.2f}")
    ax.axhline(res["va_high"], color="#54A24B", lw=1, ls="--", label=f"VA high {res['va_high']:.2f}")
    ax.axhline(res["va_low"], color="#54A24B", lw=1, ls="--", label=f"VA low {res['va_low']:.2f}")
    ax.axhline(res["bias_hvn"], color="#9D4EDD", lw=1.4, ls="-.", label=f"bias HVN {res['bias_hvn']:.2f}")
    for h in res["hvn"]:
        ax.plot(vol.max() * 1.02, h, ">", color="#54A24B", ms=6)
    for l in res["lvn"]:
        ax.plot(vol.max() * 1.02, l, "<", color="#F58518", ms=6)
    ax.plot([], [], ">", color="#54A24B", label="HVN")
    ax.plot([], [], "<", color="#F58518", label="LVN")
    ax.set_xlabel("volume"); ax.set_ylabel("price")
    ax.set_title(title, fontsize=11)
    ax.legend(loc="upper right", fontsize=8); ax.grid(axis="y", alpha=0.15)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="single session YYYY-MM-DD (default: latest)")
    ap.add_argument("--from", dest="frm", default=None, help="composite start")
    ap.add_argument("--to", default=None, help="composite end")
    ap.add_argument("--eth", action="store_true", help="use the ETH trove (full session)")
    ap.add_argument("--pct", type=float, default=0.70, help="value-area fraction")
    ap.add_argument("--naked-lookback", type=int, default=0, help="also find naked VPOCs over N prior days")
    a = ap.parse_args()

    if a.frm and a.to:
        df = td.load_range(a.frm, a.to, eth=a.eth)
        label = f"{a.frm}→{a.to} composite ({'ETH' if a.eth else 'RTH'})"
        stamp = f"vp_{a.frm}_{a.to}_composite"
        end_day = a.to
    else:
        day = a.day or td.available("eth" if a.eth else "rth")[-1]
        df = td.load_eth(day) if a.eth else td.load_rth(day)
        label = f"{day} session ({'ETH' if a.eth else 'RTH'})"
        stamp = f"vp_{day}_{'eth' if a.eth else 'rth'}"
        end_day = day

    res = build(df, a.pct)
    naked = naked_vpocs(end_day, a.naked_lookback, a.eth) if a.naked_lookback else []

    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{stamp}.png"
    chart(res, f"Volume Profile — {label}", png)

    levels = {k: v for k, v in res.items() if not k.startswith("_")}
    levels["naked_vpocs"] = naked
    levels["label"] = label
    js = OUT / f"{stamp}_levels.json"
    js.write_text(json.dumps(levels, indent=2))

    # ---- inline summary ----
    print(f"\nVolume Profile — {label}")
    print(f"  range {res['lo']:.2f}–{res['hi']:.2f}  |  total vol {res['total_vol']:,}  |  close {res['close']:.2f}")
    print(f"  VPOC        {res['vpoc']:.2f}")
    print(f"  Value area  {res['va_low']:.2f} … {res['va_high']:.2f}  ({int(a.pct*100)}%)")
    print(f"  bias HVN    {res['bias_hvn']:.2f}  -> price is {'ABOVE (long bias)' if res['close']>=res['bias_hvn'] else 'BELOW (short bias)'}")
    print(f"  HVN ({len(res['hvn'])}): " + ", ".join(f"{h:.2f}" for h in res["hvn"]))
    print(f"  LVN ({len(res['lvn'])}): " + ", ".join(f"{l:.2f}" for l in res["lvn"]))
    if a.naked_lookback:
        if naked:
            print(f"  naked VPOCs (untested, last {a.naked_lookback}d): "
                  + ", ".join(f"{n['vpoc']:.2f}({n['date']})" for n in naked))
        else:
            print(f"  naked VPOCs: none untested in the last {a.naked_lookback}d")
    print(f"\nlevels: {js}\nchart:  {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
