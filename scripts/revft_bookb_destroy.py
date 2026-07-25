"""DESTROY Book B — adversarial red-team (like the 2ES kill). 2026-07-25 (S85).

The ablation proved the hold-to-EOD exit (E) IS the edge — gates just pick which trades use it. So the
killer question: does the RevFT SIGNAL add anything, or is Book B just "hold with-trend/neutral to the
close on negative-gamma (trending) days"? If a RANDOM-TIME entry, SAME direction, same day, same
wide+EOD exit does as well, the signal is decoration and the 'edge' is trend-day drift capture.

Attacks (all at CONSERVATIVE cost = $5 comm + 2t slip = $30/trade):
  1 RANDOM-TIME NULL  — replace each Book B entry with a random 09-13 bar, same dir, wide+EOD. 2000 MC.
                        If Book B's total sits inside the null -> signal timing is worthless -> DESTROYED.
  2 TAIL JACKKNIFE    — remove top 10/20/30 winners. If profit vanishes -> a few-trade mirage.
  3 RECENT PERIOD     — last ~12 months + 2026: has the edge decayed?

    python scripts/revft_bookb_destroy.py
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
TICKD = ROOT / "data" / "ticks_continuous"
T = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
TICK = 0.25; PT = 50.0; FLOOR = 8 * TICK
CONS_COST = 30.0                     # $5 comm + 2 ticks slip
BASE_COST_IN_PARQUET = 17.5          # w30eod already had $5 + 1t
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def load_day(b, dstr):
    g = b[b["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
    p = TICKD / f"{dstr}.parquet"
    if len(g) < 30 or not p.exists():
        return None, None, None
    tk = pd.read_parquet(p).sort_values("DateTime")
    if tk.empty:
        return None, None, None
    return g, tk["Price"].values, np.searchsorted(g["DateTime"].values, tk["DateTime"].values, "right") - 1


def sim_entry(tP, tbar, entry_bar, long, wide, n):
    a = np.searchsorted(tbar, entry_bar, "left")
    if a >= len(tP):
        return None
    entry = tP[a]; seg = tP[a:]
    stop = entry - wide if long else entry + wide
    hit = np.nonzero(seg <= stop)[0] if long else np.nonzero(seg >= stop)[0]
    ex = stop if len(hit) else seg[-1]
    return ((ex - entry) if long else (entry - ex)) * PT - CONS_COST


def main():
    t = pd.read_parquet(T).sort_values("Date").reset_index(drop=True)
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    notCT = (L & bull) | (S & bear) | neu
    neg = t.mq == "negative_gamma"
    hrs = t.hour.astype(str).isin(["09", "10", "11", "12", "13"])
    B = t[neg & notCT & hrs].copy()
    B["actual"] = B["w30eod"] - (CONS_COST - BASE_COST_IN_PARQUET)     # conservative cost
    print(f"Book B (conservative $30/tr): n={len(B)}  total=${B.actual.sum():,.0f}  $/tr={B.actual.mean():.1f}  PF={pf(B.actual):.2f}\n")

    # ---- Attack 1: RANDOM-TIME NULL ----
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    NDRAW = 20
    null_draws = np.full((len(B), NDRAW), np.nan)     # per-trade random-time outcomes
    idxmap = {ix: i for i, ix in enumerate(B.index)}
    for dstr, grp in B.groupby("Date"):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        hours = pd.to_datetime(g["DateTime"]).dt.strftime("%H").values
        win_bars = np.nonzero(np.isin(hours, ["09", "10", "11", "12", "13"]))[0]
        win_bars = win_bars[(win_bars >= 1) & (win_bars < len(g) - 1)]
        if len(win_bars) < 2:
            continue
        for ix, row in grp.iterrows():
            adr = row["adr"]; wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
            long = row["dir"] == "L"
            picks = RNG.choice(win_bars, size=NDRAW, replace=True)
            for k, eb in enumerate(picks):
                r = sim_entry(tP, tbar, int(eb), long, wide, len(g))
                if r is not None:
                    null_draws[idxmap[ix], k] = r
    # per-trade mean of random-time outcome; how often does the SIGNAL beat random timing?
    per_null_mean = np.nanmean(null_draws, axis=1)
    valid = ~np.isnan(per_null_mean)
    actual = B["actual"].values
    beat = (actual[valid] > per_null_mean[valid]).mean()
    # MC: one random draw per trade, sum over book, 2000 times -> null total distribution
    tot_null = []
    for _ in range(2000):
        pick = np.array([null_draws[i, RNG.integers(0, NDRAW)] if valid[i] else 0.0 for i in range(len(B))])
        tot_null.append(np.nansum(pick))
    tot_null = np.array(tot_null); actual_tot = actual[valid].sum()
    p = (tot_null >= actual_tot).mean()
    print("="*80); print("ATTACK 1 — RANDOM-TIME NULL (same dir/day/exit, random 09-13 entry bar)"); print("="*80)
    print(f"  Book B actual total (valid trades)  ${actual_tot:,.0f}   $/tr ${actual[valid].mean():.1f}")
    print(f"  random-time null total  mean ${tot_null.mean():,.0f}  [p2.5 ${np.percentile(tot_null,2.5):,.0f}, p97.5 ${np.percentile(tot_null,97.5):,.0f}]")
    print(f"  random-time null $/tr   ${np.nanmean(per_null_mean[valid]):.1f}")
    print(f"  empirical p(null >= actual) = {p:.4f}   |   signal beats random-timing on {beat*100:.1f}% of trades")
    print(f"  --> {'SURVIVES (signal timing adds real value)' if p < 0.05 else 'DESTROYED (signal timing ~ random; edge is drift capture)'}")

    # ---- Attack 2: TAIL JACKKNIFE ----
    print("\n"+"="*80); print("ATTACK 2 — TAIL JACKKNIFE (remove top-N winners, conservative cost)"); print("="*80)
    sv = np.sort(actual)[::-1]
    print(f"  full ${actual.sum():,.0f}  (n={len(actual)})")
    for nrm in (10, 20, 30, 50):
        print(f"  remove top-{nrm:>2d}: ${actual.sum() - sv[:nrm].sum():>9,.0f}   ({100*sv[:nrm].sum()/actual.sum():.0f}% of profit in {nrm} trades)")

    # ---- Attack 3: RECENT PERIOD ----
    print("\n"+"="*80); print("ATTACK 3 — RECENT-PERIOD DECAY (conservative cost)"); print("="*80)
    for lab, m in (("2025", B.year == 2025), ("2026 YTD", B.year == 2026),
                   ("last 12mo (>=2025-07)", B.Date >= "2025-07-01"),
                   ("H2-2025+2026 (>=2025-07)", B.Date >= "2025-07-01")):
        v = B.loc[m, "actual"].values
        if len(v):
            print(f"  {lab:26s} n={len(v):4d}  ${v.sum():>8,.0f}  $/tr {v.mean():>6.1f}  PF {pf(v):.2f}")


if __name__ == "__main__":
    main()
