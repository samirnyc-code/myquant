"""
or12_outcome_agreement.py — THE payoff test for the first-12-bars matcher:
does a day's k nearest neighbours (same open-location bucket, matched on
IB shape + prior-day context ONLY) predict the rest of the day better than
chance?

Outcomes (computed strictly AFTER bar 12):
  class3    — where the day CLOSES relative to the IB: above IB High /
              inside IB / below IB Low  (3-class)
  ret_pts   — close-to-close rest-of-day move: dayClose - close of bar 12,
              normalized by IB range
  ext_up/dn — post-IB range extension beyond IB High / below IB Low, in IB units

Tests:
  1. Majority vote of the 5 NNs' class3 vs the day's class3 — accuracy
     compared against (a) always predicting the bucket's most common class,
     (b) 500 random draws of 5 same-bucket days (permutation control).
  2. Sign agreement: sign(mean NN ret) vs sign(day ret), vs same controls.
  3. Correlation of day ret with mean NN ret.

Caveat printed loudly: neighbours come from the FULL sample (past+future) —
fine for "is there signal", NOT a tradable backtest. Walk-forward comes later.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from or12_pattern_groups import build_features, BARS_PQ, N_BARS  # noqa: E402

K = 5
N_PERM = 500
SEED = 42


def day_outcome(g: pd.DataFrame) -> dict | None:
    g = g.sort_values("DateTime").reset_index(drop=True)
    if len(g) <= N_BARS + 3:          # need a real afternoon
        return None
    ib = g.iloc[:N_BARS]
    post = g.iloc[N_BARS:]
    ib_hi, ib_lo = ib["High"].max(), ib["Low"].min()
    ib_rng = ib_hi - ib_lo
    if ib_rng <= 0:
        return None
    c12 = float(ib["Close"].iloc[-1])
    day_close = float(post["Close"].iloc[-1])
    cls = ("above" if day_close > ib_hi else
           "below" if day_close < ib_lo else "inside")
    return dict(
        class3=cls,
        ret=(day_close - c12) / ib_rng,
        ext_up=max(float(post["High"].max()) - ib_hi, 0.0) / ib_rng,
        ext_dn=max(ib_lo - float(post["Low"].min()), 0.0) / ib_rng,
    )


def main() -> None:
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    outs = {}
    for d, g in bars.groupby(bars["DateTime"].dt.date):
        o = day_outcome(g)
        if o is not None:
            outs[d] = o
    out_df = pd.DataFrame.from_dict(outs, orient="index")

    full_df, full_Xz, _ = build_features()
    mask = full_df.index.isin(out_df.index)
    df = full_df[mask]
    Xz = full_Xz[mask]
    out_df = out_df.loc[df.index]

    b = df["bucket"].to_numpy()
    d2 = ((Xz[:, None, :] - Xz[None, :, :]) ** 2).sum(-1)
    d2[b[:, None] != b[None, :]] = np.inf
    np.fill_diagonal(d2, np.inf)
    nn = np.argsort(d2, axis=1)[:, :K]

    cls = out_df["class3"].to_numpy()
    ret = out_df["ret"].to_numpy()
    n = len(df)
    rng = np.random.default_rng(SEED)

    # ── 1. class3 majority vote ───────────────────────────────────────────────
    def majority(a):
        vals, cnt = np.unique(a, return_counts=True)
        return vals[cnt.argmax()]
    pred = np.array([majority(cls[nn[i]]) for i in range(n)])
    acc = float((pred == cls).mean())

    # bucket-most-common-class baseline
    bucket_mode = {bk: majority(cls[b == bk]) for bk in np.unique(b)}
    acc_mode = float(np.mean([bucket_mode[b[i]] == cls[i] for i in range(n)]))

    # permutation control: 5 random same-bucket days
    idx_by_bucket = {bk: np.where(b == bk)[0] for bk in np.unique(b)}
    perm_acc = np.empty(N_PERM)
    perm_sign = np.empty(N_PERM)
    for p in range(N_PERM):
        hits = sgn_hits = 0
        for i in range(n):
            pool = idx_by_bucket[b[i]]
            pick = rng.choice(pool, size=K, replace=False)
            pick = pick[pick != i][:K]
            hits += majority(cls[pick]) == cls[i]
            sgn_hits += (np.sign(ret[pick].mean()) == np.sign(ret[i]))
        perm_acc[p] = hits / n
        perm_sign[p] = sgn_hits / n

    # ── 2. sign agreement ─────────────────────────────────────────────────────
    nn_mean_ret = ret[nn].mean(axis=1)
    sign_acc = float((np.sign(nn_mean_ret) == np.sign(ret)).mean())

    # ── 3. correlation ────────────────────────────────────────────────────────
    corr = float(np.corrcoef(nn_mean_ret, ret)[0, 1])

    pval_acc = float((perm_acc >= acc).mean())
    pval_sign = float((perm_sign >= sign_acc).mean())

    print(f"n = {n} days | K = {K} same-bucket neighbours | {N_PERM} permutations")
    print("\n!! neighbours drawn from FULL sample (past+future) — signal test,")
    print("!! NOT a tradable backtest. Walk-forward version is the next step.\n")

    print("[1] Day CLOSE vs IB (above/inside/below), majority vote of 5 NNs:")
    print(f"    kNN accuracy        : {acc:.1%}")
    print(f"    bucket-mode baseline: {acc_mode:.1%}")
    print(f"    random-5 same bucket: {perm_acc.mean():.1%} "
          f"(sd {perm_acc.std():.1%})   p={pval_acc:.3f}")

    print("\n[2] Rest-of-day direction, sign(mean NN ret) vs sign(day ret):")
    print(f"    kNN sign accuracy   : {sign_acc:.1%}")
    print(f"    random-5 same bucket: {perm_sign.mean():.1%} "
          f"(sd {perm_sign.std():.1%})   p={pval_sign:.3f}")

    print(f"\n[3] corr(day rest-of-day ret, mean NN ret) = {corr:+.3f}")

    print("\nPer-bucket class3 base rates (context alone is already predictive):")
    tbl = pd.crosstab(df["bucket"], out_df["class3"], normalize="index")
    print((tbl * 100).round(1).to_string())


if __name__ == "__main__":
    main()
