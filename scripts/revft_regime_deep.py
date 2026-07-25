"""RevFT x REGIME — deep-dive on the saved per-trade table (no re-sim). 2026-07-25 (S85)

Reads data/regime/revft_regime_full_YYYYMMDD.parquet and slices every which way, with an
honest multiple-testing verdict. Focus: the REVERSAL thesis — RevFT is a fade, so it should
work when dealers dampen (MQ positive_gamma) and die when they amplify (negative_gamma).

    python scripts/revft_regime_deep.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
TRAIN_END = "2023-12-31"
EXITS = ["n1r", "n2r", "n3r", "neod", "w20eod", "w30eod", "w50eod", "w30_1r", "w30_2r", "w30_3r"]
NTEST = [0]  # multiple-testing counter


def stat(v):
    v = np.asarray(v, float)
    if len(v) == 0:
        return "n=0"
    gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    return f"n={len(v):5d}  tot=${v.sum():>10,.0f}  $/tr={v.mean():>6.1f}  PF={pf:4.2f}  win={100*(v>0).mean():4.1f}%"


def boot(v, n=3000):
    v = np.asarray(v, float)
    if len(v) < 25:
        return (np.nan, np.nan)
    rng = np.random.default_rng(11)
    m = [rng.choice(v, len(v), True).mean() for _ in range(n)]
    return (round(np.percentile(m, 2.5), 1), round(np.percentile(m, 97.5), 1))


def verdict(t, mask, col, name):
    """full report on one book + a pass/fail on the honest bar."""
    NTEST[0] += 1
    v = t.loc[mask, col]
    if len(v) < 25:
        print(f"  · {name:34s} {stat(v)}   [too small]"); return
    tr = t.Date <= TRAIN_END
    vtr, vho = t.loc[mask & tr, col], t.loc[mask & ~tr, col]
    ci = boot(v.values)
    yrs = {yr: t.loc[mask & (t.year == yr), col].sum() for yr in sorted(t.year.unique())}
    ypos = sum(1 for x in yrs.values() if x > 0)
    pass_ = (ci[0] > 0) and (vtr.mean() > 0) and (vho.mean() > 0) and (ypos >= len(yrs) - 1)
    flag = "  <== SURVIVES" if pass_ else ""
    print(f"  · {name:34s} {stat(v)}  CI[{ci[0]},{ci[1]}]{flag}")
    print(f"      train {stat(vtr)}   |  holdout {stat(vho)}")
    print("      yr " + " ".join(f"{y}:{x:>7,.0f}" for y, x in yrs.items()))


def main():
    t = pd.read_parquet(T)
    print(f"loaded {len(t)} trades, {t.Date.nunique()} days, {t.year.min()}-{t.year.max()}\n")
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    WT = (L & bull) | (S & bear); CT = (L & bear) | (S & bull)
    pos, neg = t.mq == "positive_gamma", t.mq == "negative_gamma"

    print("="*100); print("1. MQ GAMMA as the primary gate (reversal thesis)"); print("="*100)
    print("[fade native direction; positive_gamma should help, negative should hurt]")
    for tag, m in (("POSITIVE gamma", pos), ("NEGATIVE gamma", neg)):
        print(f"\n{tag}:")
        for col in ("n1r", "n2r", "neod", "w30eod"):
            verdict(t, m, col, f"{col}")

    print("\n"+"="*100); print("2. net_gex MAGNITUDE terciles within positive_gamma (deeper pin = stronger fade?)"); print("="*100)
    pv = t[pos].copy()
    if len(pv):
        q = pv.gex.quantile([1/3, 2/3]).values
        for lab, m in (("low +gex", pv.gex <= q[0]), ("mid +gex", (pv.gex > q[0]) & (pv.gex <= q[1])), ("high +gex (deep pin)", pv.gex > q[1])):
            idx = pv[m].index
            verdict(t, t.index.isin(idx), "neod", f"pos/{lab}/neod")

    print("\n"+"="*100); print("3. MQ gamma x phase-machine (combined gate)"); print("="*100)
    for tag, m in (("POS & with-trend", pos & WT), ("POS & counter-trend", pos & CT),
                   ("POS & neutral", pos & neu), ("NEG & with-trend", neg & WT),
                   ("NEG & counter-trend", neg & CT)):
        for col in ("neod", "w30eod", "n1r"):
            verdict(t, m, col, f"{tag}/{col}")
        print()

    print("="*100); print("4. best-single-book search across ALL exits x {pos, WT, pos&WT, CT, neg}"); print("="*100)
    gates = {"pos": pos, "neg": neg, "WT": WT, "CT": CT, "pos&WT": pos & WT, "pos&CT": pos & CT,
             "neu": neu, "neg&WT": neg & WT, "neg&neu": neg & neu, "pos&neu": pos & neu, "WTorNEU": WT | neu}
    grid = []
    for gname, gm in gates.items():
        for col in EXITS:
            v = t.loc[gm, col]
            if len(v) >= 40:
                grid.append((gname, col, len(v), v.sum(), v.mean(), boot(v.values)))
    grid.sort(key=lambda r: -r[4])
    print("top 12 by $/tr (min n=40):")
    for gname, col, n, tot, mu, ci in grid[:12]:
        print(f"  {gname:8s} {col:8s}  n={n:5d}  $/tr={mu:6.1f}  tot=${tot:>9,.0f}  CI[{ci[0]},{ci[1]}]")

    print("\n"+"="*100); print("5. idealized exits from MFE/MAE (upper bound on any trail/target)"); print("="*100)
    # best possible: if MFE reaches k*R before MAE hits stop. Bound only — not tradeable.
    for m, tag in ((pos, "POS gamma"), (WT, "with-trend"), (pos & WT, "POS&WT")):
        sub = t[m]
        if len(sub) < 40:
            continue
        for k in (1, 2, 3):
            hit = (sub.mfe >= k * sub.R).mean()
            print(f"  {tag:12s} P(MFE>={k}R)={hit*100:4.1f}%   median MFE/R={ (sub.mfe/sub.R).median():.2f}  median MAE/R={(sub.mae/sub.R).median():.2f}")

    print("\n"+"="*100); print(f"6. VERDICT — {NTEST[0]} books examined"); print("="*100)
    surv = [(g, c, t.loc[m, c].mean()) for g, m in gates.items() for c in EXITS
            if len(t.loc[m, c]) >= 40 and boot(t.loc[m, c].values)[0] > 0
            and t.loc[m & (t.Date <= TRAIN_END), c].mean() > 0
            and t.loc[m & (t.Date > TRAIN_END), c].mean() > 0]
    if surv:
        print("books with CI>0 AND both train & holdout positive:")
        for g, c, mu in sorted(surv, key=lambda r: -r[2]):
            print(f"  {g:8s} {c:8s}  $/tr={mu:.1f}")
    else:
        print("NONE of the examined books clear: bootstrap-CI>0 AND train>0 AND holdout>0.")
    print(f"\n(multiple-testing: ~{NTEST[0]}+ books searched on one 5yr sample — treat any single")
    print(" survivor as a hypothesis, not an edge, until confirmed on truly out-of-sample data.)")

    print("\n"+"="*100); print("7. ACTIONABLE RULES — year-by-year (vs base all/n1r = firm loser)"); print("="*100)
    notCT = WT | neu                     # drop the trend-fading trades
    actionable = [
        ("BASE all / n1r", pd.Series(True, t.index), "n1r"),
        ("ABL all / w30eod (exit only)", pd.Series(True, t.index), "w30eod"),
        ("ABL DROP-CT / n1r (gate only)", notCT, "n1r"),
        ("ABL NEG&notCT / n1r", neg & notCT, "n1r"),
        ("DROP-CT (WT|NEU) / w30eod", notCT, "w30eod"),
        ("DROP-CT (WT|NEU) / neod", notCT, "neod"),
        ("NEG-gamma day / w30eod", neg, "w30eod"),
        ("NEG & notCT / w30eod", neg & notCT, "w30eod"),
        ("NEG & notCT / neod", neg & notCT, "neod"),
        ("neg&neu / w30eod", neg & neu, "w30eod"),
        ("neg&neu / neod", neg & neu, "neod"),
    ]
    for name, m, col in actionable:
        verdict(t, m, col, name)
        print()

    print("\n"+"="*100); print("8. GAP / HOUR ablation on NATIVE entry (w30eod) — clean, vs the k=6-limit ablation"); print("="*100)
    GOOD = {"09", "10", "11", "12", "13"}
    for gname, gm in (("DROP-CT (WT|NEU)", notCT), ("NEG & notCT", neg & notCT)):
        print(f"\n{gname} / w30eod (native next-tick entry):")
        for name, mm in (("all", gm),
                         ("+gap-skip |gap|<=0.54", gm & (t.gap <= 0.54)),
                         ("+hours 09-13", gm & (t.hour.astype(str).isin(GOOD))),
                         ("+gap-skip +hours", gm & (t.gap <= 0.54) & (t.hour.astype(str).isin(GOOD)))):
            v = t.loc[mm, "w30eod"]
            print(f"  {name:26s} {stat(v.values)}")


if __name__ == "__main__":
    main()
