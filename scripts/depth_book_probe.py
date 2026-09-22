"""depth_book_probe.py — sanity-check what the reconstructed L2 book actually holds.

The heatmap hugs price as a ~15pt ribbon even with a wide clip. Before concluding the
FEED is shallow (vs a reconstruction bug wiping far levels), this replays the raw event
stream and reports, at sampled instants: how many levels are resting each side, their
price SPAN from touch, and how often a C (connection) resync clears the book. If the
book genuinely only spans ~15pt, distant fixed-price walls don't exist in this data.

    python scripts/depth_book_probe.py 2026-07-29
    python scripts/depth_book_probe.py 2026-07-29 --at 09:00 11:15 14:00
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "data" / "depth" / "addon_test"
TICK = 0.25


def probe(date: str, ats: list[str]):
    p = ADDON / f"ES_09-26_depth_{date}.parquet"
    df = pd.read_parquet(p, columns=["Time", "Ev", "Side", "Pos", "Price", "Size"])
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])
    ns = df["Time"].to_numpy(dtype="datetime64[ns]").view("int64")
    ev = df["Ev"].astype(str).to_numpy()
    side = df["Side"].astype(str).to_numpy()
    pos = df["Pos"].to_numpy(dtype=np.int32, na_value=0)
    price = df["Price"].to_numpy(dtype=np.float64, na_value=0.0)
    size = df["Size"].to_numpy(dtype=np.int64, na_value=0)

    targets = sorted(pd.Timestamp(f"{date} {a}").value for a in ats)
    ti = 0
    c_count = 0
    max_levels = 0
    span_samples = []          # (n_bid, n_ask, span_bid_pts, span_ask_pts) each event
    bid: list[list[float]] = []
    ask: list[list[float]] = []

    def report(tstamp):
        cur_last = None
        bb = max((pt for pt, s in bid if s > 0), default=None)
        aa = min((pt for pt, s in ask if s > 0), default=None)
        bprices = [pt for pt, s in bid if s > 0]
        aprices = [pt for pt, s in ask if s > 0]
        bl = (max(bprices) - min(bprices)) * TICK if bprices else 0
        al = (max(aprices) - min(aprices)) * TICK if aprices else 0
        touch = (bb * TICK if bb else 0, aa * TICK if aa else 0)
        print(f"  {pd.Timestamp(tstamp):%H:%M:%S}  bid_levels={len(bprices):2d} "
              f"span={bl:5.2f}pt  |  ask_levels={len(aprices):2d} span={al:5.2f}pt  "
              f"|  touch {touch[0]:.2f}/{touch[1]:.2f}")
        if bprices:
            far = min(bprices) * TICK
            print(f"        deepest bid {far:.2f} ({(touch[0]-far):.2f}pt below touch), "
                  f"sizes near-to-far: {[int(s) for _, s in sorted(bid, key=lambda x:-x[0]) if s>0][:12]}")

    for i in range(len(ns)):
        e = ev[i]
        if e == "T":
            continue
        if e == "C":
            c_count += 1
            bid.clear(); ask.clear()
            continue
        lst = bid if side[i] == "B" else ask
        pp = int(pos[i])
        if e == "A":
            if 0 <= pp <= len(lst):
                lst.insert(pp, [int(round(price[i] / TICK)), int(size[i])])
        elif e == "U":
            if 0 <= pp < len(lst):
                lst[pp] = [int(round(price[i] / TICK)), int(size[i])]
        elif e == "R":
            if 0 <= pp < len(lst):
                del lst[pp]
        max_levels = max(max_levels, len(bid) + len(ask))
        if ti < len(targets) and ns[i] >= targets[ti]:
            report(targets[ti])
            ti += 1

    print(f"\n  C (resync) events all day: {c_count}")
    print(f"  max levels held (bid+ask) at any instant: {max_levels}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--at", nargs="+", default=["09:00", "11:15", "12:00", "14:00"])
    a = ap.parse_args()
    print(f"book probe {a.date} at {a.at}")
    probe(a.date, a.at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
