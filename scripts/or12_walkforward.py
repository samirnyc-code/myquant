"""
or12_walkforward.py — THE decision test for the OR12 twin-day tool: as of each
day D (after a 250-day burn-in), find D's K nearest same-bucket neighbours
among PAST days only (exactly what a live tool could do at 9:30), read their
outcome DISTRIBUTION (not a majority vote), and score it against what actually
happened — vs honest baselines computable from the same past data.

Outcomes tested:
  class3   — day close vs IB (above / inside / below)
  trend    — MWG86 trend day (range > 1.1x ADR20, close within 25% of extreme)

Scoring:
  - log-loss + accuracy of the twin distribution vs (a) past same-bucket base
    rates ("context prior"), (b) past same-bucket x IB-width-tercile base rates
    ("conditional prior" — the free baseline twins must beat)
  - lift table: P(trend day | twin trend-fraction decile) vs base rate —
    the practical "early trend-day warning" value
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from or12_pattern_groups import build_features, BARS_PQ, N_BARS  # noqa: E402
from or12_outcome_agreement import day_outcome                    # noqa: E402

K       = int(os.environ.get("OR12_K", 20))
BURN_IN = 250
EPS     = 1e-9
CLASSES = ["above", "inside", "below"]


def main() -> None:
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    outs = {}
    for d, g in bars.groupby(bars["DateTime"].dt.date):
        o = day_outcome(g)
        if o is not None:
            outs[d] = o
    out_df = pd.DataFrame.from_dict(outs, orient="index")

    dr = bars.groupby(bars["DateTime"].dt.date).agg(H=("High", "max"),
                                                    L=("Low", "min"))
    adr20 = (dr["H"] - dr["L"]).rolling(20, min_periods=10).mean().shift(1)

    full_df, full_Xz, _ = build_features()
    mask = full_df.index.isin(out_df.index)
    df = full_df[mask].sort_index()
    Xz = full_Xz[mask]
    out_df = out_df.loc[df.index]
    adr20 = adr20.reindex(df.index)

    cls = out_df["class3"].to_numpy()
    is_trend = ((out_df["day_rng"] > 1.1 * adr20)
                & ((out_df["close_pos"] >= 0.75)
                   | (out_df["close_pos"] <= 0.25))).to_numpy()
    b = df["bucket"].to_numpy()
    ibatr = df["ib_atr"].to_numpy()
    n = len(df)

    # walk-forward loop
    rec = []
    for i in range(BURN_IN, n):
        past = np.arange(i)
        pool = past[b[past] == b[i]]
        if len(pool) < K + 5:
            continue
        d = np.abs(Xz[pool] - Xz[i]).__pow__(2).sum(axis=1)
        nn = pool[np.argsort(d)[:K]]

        # twin distribution (Laplace-smoothed)
        p_twin = np.array([(cls[nn] == c).sum() + 1.0 for c in CLASSES])
        p_twin /= p_twin.sum()
        twin_trend_frac = float(is_trend[nn].mean())

        # context prior: past same-bucket base rates
        p_ctx = np.array([(cls[pool] == c).sum() + 1.0 for c in CLASSES])
        p_ctx /= p_ctx.sum()

        # conditional prior: same bucket AND same IB-width tercile (past-fit)
        terc = np.quantile(ibatr[pool], [1/3, 2/3])
        my_t = int(np.digitize(ibatr[i], terc))
        pool_t = pool[np.digitize(ibatr[pool], terc) == my_t]
        if len(pool_t) >= 20:
            p_cond = np.array([(cls[pool_t] == c).sum() + 1.0 for c in CLASSES])
            p_cond /= p_cond.sum()
            trend_cond = float(is_trend[pool_t].mean())
        else:
            p_cond = p_ctx
            trend_cond = float(is_trend[pool].mean())

        y = CLASSES.index(cls[i])
        rec.append(dict(
            date=df.index[i], y=y,
            ll_twin=-np.log(p_twin[y] + EPS),
            ll_ctx=-np.log(p_ctx[y] + EPS),
            ll_cond=-np.log(p_cond[y] + EPS),
            hit_twin=int(np.argmax(p_twin) == y),
            hit_ctx=int(np.argmax(p_ctx) == y),
            hit_cond=int(np.argmax(p_cond) == y),
            conf_twin=float(p_twin.max()),
            twin_trend_frac=twin_trend_frac,
            trend_cond=trend_cond,
            is_trend=bool(is_trend[i]),
        ))

    r = pd.DataFrame(rec)
    m = len(r)
    print(f"walk-forward days scored: {m} (burn-in {BURN_IN}, K={K}, "
          f"neighbours strictly in the past)\n")

    print("[A] class3 (close above/inside/below IB) — OOS, live-computable:")
    print(f"    accuracy : twins {r.hit_twin.mean():.1%} | "
          f"bucket prior {r.hit_ctx.mean():.1%} | "
          f"bucket+IBwidth prior {r.hit_cond.mean():.1%}")
    print(f"    log-loss : twins {r.ll_twin.mean():.4f} | "
          f"bucket prior {r.ll_ctx.mean():.4f} | "
          f"bucket+IBwidth prior {r.ll_cond.mean():.4f}  (lower=better)")
    # paired bootstrap on log-loss difference twins vs conditional prior
    rng = np.random.default_rng(42)
    diffs = r.ll_cond.to_numpy() - r.ll_twin.to_numpy()
    boots = [diffs[rng.integers(0, m, m)].mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"    log-loss edge twins vs conditional prior: "
          f"{diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]"
          f"  ({'REAL' if lo > 0 else 'NOT significant'})")

    # high-confidence subset
    for thr in (0.45, 0.55):
        sub = r[r.conf_twin >= thr]
        if len(sub) > 30:
            print(f"    when twin-vote confidence >= {thr:.0%}: "
                  f"accuracy {sub.hit_twin.mean():.1%} on {len(sub)} days "
                  f"({len(sub)/m:.0%} of days)")

    print(f"\n[B] TREND-DAY early warning (base rate {r.is_trend.mean():.1%}):")
    q = pd.qcut(r.twin_trend_frac, 5, duplicates="drop")
    tbl = r.groupby(q, observed=True).agg(
        n=("is_trend", "size"), p_trend=("is_trend", "mean"),
        cond_prior=("trend_cond", "mean"))
    tbl["p_trend"] = (tbl["p_trend"] * 100).round(1)
    tbl["cond_prior"] = (tbl["cond_prior"] * 100).round(1)
    print(tbl.to_string())
    top = r[r.twin_trend_frac >= r.twin_trend_frac.quantile(0.8)]
    bot = r[r.twin_trend_frac <= r.twin_trend_frac.quantile(0.2)]
    print(f"    top-quintile twin-trend days:  P(trend)={top.is_trend.mean():.1%}"
          f" (n={len(top)})")
    print(f"    bottom-quintile:               P(trend)={bot.is_trend.mean():.1%}"
          f" (n={len(bot)})")


if __name__ == "__main__":
    main()
