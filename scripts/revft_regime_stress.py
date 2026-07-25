"""RevFT x regime — STRESS BATTERY (is it a real edge?). 2026-07-25 (S85).

Mirrors the S83 2E book's 10-test battery (docs/research_notes/R2E_system_config_v1.md), adapted
for RevFT and reading the per-trade table data/regime/revft_regime_full_20260725.parquet (no re-sim;
costs are per-trade additive, stops/gates are columns, so cost/param/neighborhood stress is analytic).

Books under test (native next-tick entry, from note 0015):
  A = DROP-CT (WT|NEU) / wide-0.30xADR + hold-EOD
  B = NEG-gamma & DROP-CT / wide-0.30xADR + hold-EOD   (headline)

Runs the tests that need no external data:
  N1 LABEL-PERMUTATION NULL  — is the regime/gamma gate informative, or a lucky subset?
  N2 GAMMA TRAIN/TEST INVERSION — the exact trap that killed the 2E gamma label.
  #1 ROLLING OOS (quarters)   — stability across time (rule is param-free, no re-derivation).
  #2 COST STRESS              — $10 RT + 2t both sides (analytic per-trade).
  #3 PESSIMISTIC FILLS        — extra slip + random X% fill-failure (MC).
  #5 ENGINE INVARIANCE        — re-gate with pt_old instead of pt_new.
  #6 BLOCK-BOOTSTRAP DD       — 5-trade blocks, honest maxDD + worst flat stretch.
  #7 PARAM NEIGHBORHOOD       — stop-mult {0.20,0.30,0.50} x exit {EOD} x gate — plateau vs peak.
  #8 LOYO + TAIL JACKKNIFE    — drop each year; remove top-N winners.
Blocked (need external data / live): #4 Databento, #9 NT8 live-fills, #10 cross-instrument/out-of-period.

    python scripts/revft_regime_stress.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
TRAIN_END = "2023-12-31"
COMM, SLIP1 = 5.0, 12.5          # what the parquet already charged: $5 RT + 1 tick one-side
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def maxdd(v):
    eq = np.cumsum(v); return float((eq - np.maximum.accumulate(eq)).min())


def line(tag, v):
    v = np.asarray(v, float)
    if not len(v):
        print(f"  {tag:30s} n=0"); return
    print(f"  {tag:30s} n={len(v):5d}  tot=${v.sum():>9,.0f}  $/tr={v.mean():6.1f}  PF={pf(v):4.2f}  maxDD=${maxdd(v):>8,.0f}")


def main():
    t = pd.read_parquet(T).sort_values(["Date"]).reset_index(drop=True)
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    WT = (L & bull) | (S & bear); notCT = WT | neu
    neg = t.mq == "negative_gamma"
    A = notCT; B = neg & notCT
    tr = t.Date <= TRAIN_END
    print(f"loaded {len(t)} trades  |  Book A (DROP-CT) n={A.sum()}  |  Book B (NEG&DROP-CT) n={B.sum()}\n")
    print("BASELINES (w30eod):"); line("A DROP-CT", t.loc[A, "w30eod"]); line("B NEG&DROP-CT", t.loc[B, "w30eod"])
    line("all (no gate)", t.w30eod)

    # ===== N1 LABEL-PERMUTATION NULL =====
    print("\n===== N1 LABEL-PERMUTATION NULL (2000x; permute reg+mq across trades, re-gate) =====")
    print("H0: regime/gamma labels carry no info -> gate picks a random subset -> $/tr ~ base.")
    reg = t.reg.values; mq = t.mq.values; dirv = t.dir.values; w = t.w30eod.values
    isL = dirv == "L"
    NP = 2000
    for bookname, use_mq in (("A DROP-CT", False), ("B NEG&DROP-CT", True)):
        real = t.loc[(B if use_mq else A), "w30eod"].mean()
        null = np.empty(NP)
        for i in range(NP):
            rp = RNG.permutation(reg)
            wt = ((isL & (rp == "BULL")) | (~isL & (rp == "BEAR")) | (rp == "NEUTRAL"))
            m = wt
            if use_mq:
                mp = RNG.permutation(mq); m = wt & (mp == "negative_gamma")
            null[i] = w[m].mean() if m.any() else 0.0
        p = (null >= real).mean()
        print(f"  {bookname:16s} real $/tr={real:6.1f}   null mean={null.mean():5.1f} "
              f"[p2.5={np.percentile(null,2.5):5.1f}, p97.5={np.percentile(null,97.5):5.1f}]   "
              f"empirical p(null>=real)={p:.4f}  {'*** informative' if p < 0.05 else 'NOT sig'}")

    # ===== N2 GAMMA TRAIN/TEST INVERSION (the 2E killer) =====
    print("\n===== N2 GAMMA TRAIN/TEST INVERSION CHECK =====")
    print("2E's pos/neg gamma label INVERTED (train PF 2.07 / test 0.91) -> was killed. RevFT must not.")
    for tag, m in (("neg&notCT", B), ("pos&notCT", (t.mq == 'positive_gamma') & notCT)):
        vtr, vte = t.loc[m & tr, "w30eod"], t.loc[m & ~tr, "w30eod"]
        print(f"  {tag:12s}  train PF={pf(vtr):.2f} (${vtr.mean():.1f}/tr)   test PF={pf(vte):.2f} (${vte.mean():.1f}/tr)"
              f"   {'INVERTED' if (pf(vtr)>1.1 and pf(vte)<1.0) else 'stable'}")
    # gamma lift within notCT, both halves
    for half, m in (("train", tr), ("test", ~tr)):
        vn = t.loc[notCT & neg & m, "w30eod"].mean(); vp = t.loc[notCT & (t.mq=='positive_gamma') & m, "w30eod"].mean()
        print(f"  {half}: neg-gamma lift over pos-gamma (within DROP-CT) = ${vn-vp:.1f}/tr  (neg {vn:.1f} vs pos {vp:.1f})")

    # ===== #1 ROLLING OOS QUARTERS =====
    print("\n===== #1 ROLLING OOS (calendar quarters; param-free rule, no re-derivation) =====")
    t["q"] = pd.PeriodIndex(pd.to_datetime(t.Date), freq="Q").astype(str)
    for bookname, m in (("A DROP-CT", A), ("B NEG&DROP-CT", B)):
        g = t[m].groupby("q").w30eod.sum()
        green = (g > 0).mean()
        print(f"  {bookname:16s} quarters={len(g)}  green={green*100:.0f}%  median=${g.median():,.0f}  worst=${g.min():,.0f}  best=${g.max():,.0f}")

    # ===== #2 COST STRESS =====
    print("\n===== #2 COST STRESS ($10 RT + 2t BOTH sides vs $5 RT + 1t one-side) =====")
    # parquet charged COMM(5)+SLIP1(12.5). New: COMM 10 + 2t*2sides=4t=$50. extra = (10-5)+(50-12.5)=42.5
    extra = (10.0 - COMM) + (4 * 12.5 - SLIP1)
    for bookname, m in (("A DROP-CT", A), ("B NEG&DROP-CT", B)):
        v = t.loc[m, "w30eod"].values; v2 = v - extra
        print(f"  {bookname:16s} base PF={pf(v):.2f} ${v.sum():,.0f}  ->  stressed PF={pf(v2):.2f} ${v2.sum():,.0f} (${v2.mean():.1f}/tr)  {'FAIL' if pf(v2)<1.1 else 'PASS'}")

    # ===== #3 PESSIMISTIC FILLS =====
    print("\n===== #3 PESSIMISTIC FILLS (extra 1t slip + randomly drop X% of fills, 1000 MC) =====")
    for bookname, m in (("A DROP-CT", A), ("B NEG&DROP-CT", B)):
        v = t.loc[m, "w30eod"].values - 12.5     # +1 tick adverse slip
        for pct in (0.10, 0.25):
            tots = [RNG.choice(v, int(len(v)*(1-pct)), replace=False).sum() for _ in range(1000)]
            print(f"  {bookname:16s} +1t slip, drop {int(pct*100)}%:  median tot=${np.median(tots):,.0f}  worst-5%=${np.percentile(tots,5):,.0f}  ($/tr base w/slip={v.mean():.1f})")

    # ===== #5 ENGINE INVARIANCE (pt_old) =====
    print("\n===== #5 ENGINE INVARIANCE (re-gate DROP-CT with pt_old instead of pt_new) =====")
    if (t.reg_old != "na").any():
        bo, be, no = t.reg_old == "BULL", t.reg_old == "BEAR", t.reg_old == "NEUTRAL"
        WTo = (L & bo) | (S & be); notCTo = WTo | no
        line("A pt_new", t.loc[A, "w30eod"]); line("A pt_old", t.loc[notCTo, "w30eod"])
        line("B pt_new", t.loc[B, "w30eod"]); line("B pt_old", t.loc[neg & notCTo, "w30eod"])
    else:
        print("  pt_old column absent")

    # ===== #6 BLOCK-BOOTSTRAP DD =====
    print("\n===== #6 BLOCK-BOOTSTRAP maxDD (5-trade blocks, 5000 paths) =====")
    for bookname, m in (("A DROP-CT", A), ("B NEG&DROP-CT", B)):
        v = t.loc[m, "w30eod"].values; nb = len(v) // 5
        dds = np.empty(5000)
        for i in range(5000):
            starts = RNG.integers(0, len(v) - 5, nb)
            path = np.concatenate([v[s:s+5] for s in starts])
            dds[i] = maxdd(path)
        print(f"  {bookname:16s} realized maxDD=${maxdd(v):,.0f}   bootstrap worst-5%=${np.percentile(dds,5):,.0f}  worst-1%=${np.percentile(dds,1):,.0f}")

    # ===== #7 PARAM NEIGHBORHOOD =====
    print("\n===== #7 PARAM NEIGHBORHOOD (stop-mult x gate; all should stay positive = plateau) =====")
    print(f"  {'gate':14s} {'w20eod':>9s} {'w30eod':>9s} {'w50eod':>9s} {'neod':>9s}")
    for bookname, m in (("DROP-CT", A), ("NEG&DROP-CT", B)):
        vals = [t.loc[m, c].sum() for c in ("w20eod", "w30eod", "w50eod", "neod")]
        print(f"  {bookname:14s} " + " ".join(f"${x:>8,.0f}" for x in vals))

    # ===== #8 LOYO + TAIL JACKKNIFE =====
    print("\n===== #8 LEAVE-ONE-YEAR-OUT + TAIL JACKKNIFE =====")
    for bookname, m in (("A DROP-CT", A), ("B NEG&DROP-CT", B)):
        sub = t[m]
        print(f"  {bookname}: full ${sub.w30eod.sum():,.0f}")
        loyo = {y: sub[sub.year != y].w30eod.sum() for y in sorted(sub.year.unique())}
        print(f"     LOYO (drop each yr): min=${min(loyo.values()):,.0f} (all still +? {all(x>0 for x in loyo.values())})")
        sv = np.sort(sub.w30eod.values)[::-1]
        for n in (5, 10, 20):
            print(f"     remove top-{n} winners: ${sub.w30eod.sum() - sv[:n].sum():,.0f}")

    print("\n===== BLOCKED (need external data / live) =====")
    print("  #4 Databento clean-tick cross-check · #9 NT8 signal-diff + forward MES fills ·")
    print("  #10 cross-instrument (NQ/MES RevFT export) + out-of-period ES 2010-2020.")


if __name__ == "__main__":
    main()
