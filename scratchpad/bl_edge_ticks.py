"""Do ES Blind Spots act as real reaction zones? — tick-based, 200-session backtest.

For each session with BL levels, resample that day's ticks to 1-min OHLC and, for each of
the 10 BLs, find the FIRST touch and measure:
  reaction    = max move AWAY from the level after first touch (favorable rejection)
  penetration = max move THROUGH the level after first touch
  rejected    = reaction > penetration
Everything normalized by the session's own range so days are comparable.

NULL control: for each session, the SAME test on random levels drawn uniformly inside the
day's [low, high]. If BLs are real reaction zones, BL rejection-rate / reaction should beat
the random null. This is an honest test — no look-ahead beyond first-touch, no fills.
"""
import csv, glob, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MQ = ROOT / "data" / "menthorq"
TICKS = ROOT / "data" / "ticks_continuous"
RNG = np.random.default_rng(42)


def load_bl():
    rows = {}
    with open(MQ / "ES1!_mq_blindspots_history.csv", newline="") as f:
        for r in csv.DictReader(f):
            v = [float(r[f"bl_{i}"]) for i in range(1, 11) if r.get(f"bl_{i}")]
            if len(v) == 10:
                rows[r["date"]] = v
    return rows


def day_bars(date):
    p = TICKS / f"{date}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p, columns=["DateTime", "Price"])
    t = t.set_index("DateTime")
    o = t.Price.resample("1min").ohlc().dropna()
    return o if len(o) > 30 else None


def test_levels(bars, levels, open_px):
    hi, lo = bars.high.values, bars.low.values
    rng = hi.max() - lo.min()
    if rng <= 0:
        return []
    out = []
    for L in levels:
        above = L > open_px
        idx = np.where(hi >= L)[0] if above else np.where(lo <= L)[0]
        if len(idx) == 0:
            continue
        i0 = idx[0]
        if i0 >= len(bars) - 3:
            continue
        h2, l2 = hi[i0:], lo[i0:]
        react = (L - l2.min()) if above else (h2.max() - L)
        pen = (h2.max() - L) if above else (L - l2.min())
        out.append((react / rng, pen / rng, react > pen))
    return out


def main():
    BL = load_bl()
    real, null = [], []
    used = 0
    for date, levels in sorted(BL.items()):
        bars = day_bars(date)
        if bars is None:
            continue
        open_px = float(bars.open.iloc[0])
        lo, hi = float(bars.low.min()), float(bars.high.max())
        r = test_levels(bars, levels, open_px)
        if not r:
            continue
        real += r
        # null: random levels drawn from the SAME band the BLs span around the open,
        # so touched-null and touched-BL are the same population (fixes the in-range bias).
        offs = [(L - open_px) / open_px for L in levels]
        omin, omax = min(offs), max(offs)
        rnd = [open_px * (1 + o) for o in RNG.uniform(omin, omax, size=40)]  # 40 for power
        null += test_levels(bars, rnd, open_px)
        used += 1

    def summ(rows, name):
        a = np.array([x[0] for x in rows]); p = np.array([x[1] for x in rows])
        rej = np.array([x[2] for x in rows])
        print(f"  {name:12} n={len(rows):5}  med reaction={np.median(a):.3f}  "
              f"med penetration={np.median(p):.3f}  rejected={rej.mean()*100:.1f}%")
        return a, rej

    print(f"ES Blind Spots as reaction zones — {used} sessions, {len(real)} BL touches\n")
    ra, rrej = summ(real, "BLIND SPOTS")
    na, nrej = summ(null, "RANDOM null")
    # significance on rejection rate
    pr, pn = rrej.mean(), nrej.mean()
    se = np.sqrt(pr*(1-pr)/len(rrej) + pn*(1-pn)/len(nrej))
    print(f"\n  rejection-rate diff (BL - random): {(pr-pn)*100:+.1f} pp "
          f"(se {se*100:.1f}, z={(pr-pn)/se:+.1f})")
    # reaction magnitude
    se2 = np.sqrt(ra.var()/len(ra) + na.var()/len(na))
    print(f"  reaction diff: {(ra.mean()-na.mean()):+.4f} range-units "
          f"(z={(ra.mean()-na.mean())/se2:+.1f})")
    verdict = "BLs ARE stronger reaction zones than random" if (pr-pn)/se > 2 else \
              "BLs are NOT distinguishable from random levels"
    print(f"\n  VERDICT: {verdict}")


if __name__ == "__main__":
    main()
