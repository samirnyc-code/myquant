"""depth_level_edge.py — does a LARGE resting level at the touch predict a hold?

The NT L2 feed is only ~30 levels (~7pt) deep, so the only testable order-flow claim is
a NEAR-TOUCH one: when the size resting at the best bid (ask) is unusually large, does
price bounce off it more often than a normal-sized level? This is the honest, quantified
version of "the 362-lot bid held the low" — tested before it is trusted.

PRE-REGISTERED design (fixed knobs, no tuning-to-fit):
  event    : sample the reconstructed book every STEP_S seconds during RTH; read the size
             resting at the best bid (support side) and best ask (resistance side).
  predictor: that size / the day's median best-touch size on that side  -> ratio.
             "big" = ratio >= BIG_MULT (reported for 2x, 3x, 5x).
  outcome  : over the next HORIZON_S seconds, HOLD = price never traded more than
             BUFFER_TICKS through the level (bid: min tape >= bid_px - buf;
             ask: max tape <= ask_px + buf); else BREAK.
  controls : (1) base rate = hold rate over all samples; (2) hold rate by size quintile;
             (3) a DE-OVERLAPPED pass (stride = HORIZON_S so samples are independent),
             because 3s samples with a 60s horizon are autocorrelated and inflate n.
  honesty  : ~6 sessions only; spoof-pulls are counted as holds (a pulled level that
             price then bounces from looks identical here); report nulls as nulls.

    python scripts/depth_level_edge.py                       # all default days
    python scripts/depth_level_edge.py --days 2026-07-29 2026-07-28
Outputs: data/depth/level_edge_events_<stamp>.csv + printed summary (also saved .txt).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "data" / "depth" / "addon_test"
OUTDIR = ROOT / "data" / "depth"
TICK = 0.25

# ---- pre-registered knobs ----
STEP_S = 3
HORIZON_S = 60
BUFFER_TICKS = 2
BIG_MULTS = (2.0, 3.0, 5.0)
RTH = ("08:30", "15:15")
DEFAULT_DAYS = ["2026-07-22", "2026-07-23", "2026-07-24",
                "2026-07-27", "2026-07-28", "2026-07-29"]


def _events_for_day(date: str) -> pd.DataFrame:
    """Reconstruct the book, sample best-touch size every STEP_S, and score the forward
    hold/break outcome against the tape. Returns one row per (sample, side)."""
    p = ADDON / f"ES_09-26_depth_{date}.parquet"
    if not p.exists():
        print(f"  [skip] {date}: no parquet")
        return pd.DataFrame()
    df = pd.read_parquet(p, columns=["Time", "Ev", "Side", "Pos", "Price", "Size"])
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])
    ns = df["Time"].to_numpy(dtype="datetime64[ns]").view("int64")
    ev = df["Ev"].astype(str).to_numpy()
    side = df["Side"].astype(str).to_numpy()
    pos = df["Pos"].to_numpy(dtype=np.int32, na_value=0)
    price = df["Price"].to_numpy(dtype=np.float64, na_value=0.0)
    size = df["Size"].to_numpy(dtype=np.int64, na_value=0)

    w0 = pd.Timestamp(f"{date} {RTH[0]}").value
    w1 = pd.Timestamp(f"{date} {RTH[1]}").value
    step = STEP_S * 1_000_000_000

    bid: list[list[int]] = []      # [price_tick, size], index = Pos (0 = best)
    ask: list[list[int]] = []
    samp_ns, bb_px, bb_sz, ba_px, ba_sz, med_sz = [], [], [], [], [], []
    tape_ns, tape_px = [], []
    next_sample = (w0 // step) * step

    def best_bid():
        live = [(pt, s) for pt, s in bid if s > 0]
        return max(live, key=lambda x: x[0]) if live else None

    def best_ask():
        live = [(pt, s) for pt, s in ask if s > 0]
        return min(live, key=lambda x: x[0]) if live else None

    for i in range(len(ns)):
        e = ev[i]
        if e == "T":
            if w0 <= ns[i] <= w1:
                tape_ns.append(ns[i]); tape_px.append(price[i])
            continue
        if e == "C":
            bid.clear(); ask.clear(); continue
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
        # sample on the grid, inside RTH
        t = ns[i]
        if t >= next_sample and w0 <= t <= w1:
            bbid, bask = best_bid(), best_ask()
            if bbid and bask:
                sizes = [s for _, s in bid if s > 0] + [s for _, s in ask if s > 0]
                samp_ns.append(t)
                bb_px.append(bbid[0]); bb_sz.append(bbid[1])
                ba_px.append(bask[0]); ba_sz.append(bask[1])
                med_sz.append(float(np.median(sizes)) if sizes else np.nan)
            next_sample += step * ((t - next_sample) // step + 1)

    if not samp_ns:
        return pd.DataFrame()
    tn = np.array(tape_ns, dtype=np.int64)
    tp = np.array(tape_px, dtype=np.float64)
    order = np.argsort(tn); tn, tp = tn[order], tp[order]

    sn = np.array(samp_ns, dtype=np.int64)
    hz = HORIZON_S * 1_000_000_000
    buf = BUFFER_TICKS * TICK
    lo = np.searchsorted(tn, sn, "right")
    hi = np.searchsorted(tn, sn + hz, "right")

    rows = []
    day_med_bid = np.nanmedian(bb_sz)
    day_med_ask = np.nanmedian(ba_sz)
    for k in range(len(sn)):
        a, b = lo[k], hi[k]
        if b <= a:
            continue                      # no forward tape (end of day) -> drop
        seg = tp[a:b]
        fmin, fmax = seg.min(), seg.max()
        bidpx = bb_px[k] * TICK
        askpx = ba_px[k] * TICK
        rows.append((date, sn[k], "support", bidpx, bb_sz[k],
                     bb_sz[k] / day_med_bid if day_med_bid else np.nan,
                     int(fmin >= bidpx - buf)))
        rows.append((date, sn[k], "resistance", askpx, ba_sz[k],
                     ba_sz[k] / day_med_ask if day_med_ask else np.nan,
                     int(fmax <= askpx + buf)))
    out = pd.DataFrame(rows, columns=["date", "ns", "side", "px", "sz",
                                      "ratio", "hold"])
    print(f"  [ok]  {date}: {len(out)//2:,} samples  "
          f"(med touch size bid={day_med_bid:.0f}/ask={day_med_ask:.0f})")
    return out


def _summ(df: pd.DataFrame, label: str, lines: list):
    lines.append(f"\n===== {label}  (n={len(df):,} side-samples) =====")
    for sd in ("support", "resistance"):
        s = df[df["side"] == sd]
        if s.empty:
            continue
        base = s["hold"].mean()
        lines.append(f"\n  {sd}: base hold rate = {base:.3f}  (n={len(s):,})")
        # quintiles of size ratio
        try:
            s = s.assign(q=pd.qcut(s["ratio"], 5, labels=[1, 2, 3, 4, 5]))
            g = s.groupby("q", observed=True)["hold"].agg(["mean", "count"])
            lines.append("    hold rate by size quintile (1=small .. 5=big):")
            for q, r in g.iterrows():
                lines.append(f"      Q{q}: {r['mean']:.3f}  (n={int(r['count']):,})")
        except Exception as e:
            lines.append(f"    (quintiles n/a: {e})")
        for m in BIG_MULTS:
            big = s[s["ratio"] >= m]["hold"]
            rest = s[s["ratio"] < m]["hold"]
            if len(big) >= 30 and len(rest) >= 30:
                lift = big.mean() - rest.mean()
                lines.append(f"    big(>= {m:g}x): hold {big.mean():.3f} (n={len(big):,})"
                             f"  vs rest {rest.mean():.3f}  -> lift {lift:+.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", default=DEFAULT_DAYS)
    a = ap.parse_args()

    print(f"level-edge study — {len(a.days)} day(s), step {STEP_S}s, horizon {HORIZON_S}s, "
          f"break {BUFFER_TICKS}t")
    parts = [_events_for_day(d) for d in a.days]
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    if df.empty:
        print("no events"); return 1

    stamp = a.days[-1].replace("-", "")
    csv = OUTDIR / f"level_edge_events_{stamp}.csv"
    df.to_csv(csv, index=False)

    lines = [f"L2 near-touch level-edge study — days {a.days}",
             f"step={STEP_S}s horizon={HORIZON_S}s buffer={BUFFER_TICKS}t  "
             f"events CSV: {csv.name}"]
    _summ(df, "ALL SAMPLES (overlapping, 3s)", lines)

    # de-overlapped: keep one sample per HORIZON per side per day (independent outcomes)
    stride = HORIZON_S * 1_000_000_000
    df = df.sort_values("ns")
    df["slot"] = df["ns"] // stride
    indep = df.drop_duplicates(["date", "side", "slot"])
    _summ(indep, "DE-OVERLAPPED (1 sample / 60s, independent)", lines)

    lines.append("\nNOTE: pulled (spoof) levels that price then bounces from are counted "
                 "as HOLDs — this measures the level as a VISUAL signal, not fill quality.")
    report = "\n".join(lines)
    print(report)
    (OUTDIR / f"level_edge_summary_{stamp}.txt").write_text(report, encoding="utf-8")
    print(f"\nsaved: {csv.name} + level_edge_summary_{stamp}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
