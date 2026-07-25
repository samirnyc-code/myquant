# 0015d — f2EL Fade × EMA Context — 2026-07-25
**Series:** MC Setup Research Notes · Note 0015c companion
**Confidence:** EVOLVED THROUGH THREE FEATURES — read §Correction FIRST. The original "strong
down-move through the EMA" feature is DEAD (a stale-cross artifact). The surviving candidate is
**"price ABOVE the EMA at the fade = failed reclaim"** (lookback-free, PF 2.78, holdout>train, but
perm-p 0.06 / n=25 / year-concentrated → borderline, NOT confirmed). §1–§K-sweep below are the dead
original for the record.

## ⚠️ CORRECTION (Samir's recency point) — the real feature is a FAILED EMA RECLAIM
Samir: "of course it matters how many bars ago — a strong cross 20 bars ago on 5M is meaningless if
we already crossed back." Correct. The original `cross_str` took the MAX-strength down-cross anywhere
in a K-bar window → at large K it tagged fades with **stale/already-reversed** crosses. The K-sweep
"inversion" (§K-sweep) was that bad-feature artifact, not proof the idea is noise.

Rebuilt recency-aware (`revft_fade_ema_recency.py`): anchor on the most-recent INTACT down-cross, make
recency the axis. That exposed the down-cross was the wrong feature *and wrong direction* — the best
fades are where price is **ABOVE** the EMA at entry (the failed long RECLAIMED the EMA then failed = a
failed-breakout-above-the-MA short), which has **no lookback K at all**:

| f2EL fade at entry | n | $/tr | PF | perm-p |
|---|---|---|---|---|
| **price ABOVE EMA (failed reclaim)** | 25 | **+295** | **2.78** | **0.060** |
| price BELOW EMA (weak bounce) | 87 | −11 | 0.94 | — |

train PF 1.91 → holdout PF 4.29. **But borderline:** perm-p 0.06 (not <0.05), n=25, year-concentrated
(2022 +$4.1k / 2025 +$6.1k carry it; 2023/2024 negative). Down-cross recency/strength: all perm-p>0.3,
dead. Stale strong cross (recency>10) PF 0.81 — confirms Samir's point (stale = useless).

**NQ CROSS-INSTRUMENT TEST → DOES NOT CONFIRM → THREAD RETIRED (`revft_fade_nq.py`).**

| test | above-EMA (reclaim) | below-EMA | perm-p |
|---|---|---|---|
| ES, original 4pt stop | PF 2.78 | 0.94 | 0.06 |
| ES, ADR-normalized stop | PF 1.79 | 1.20 | **0.30** |
| NQ, ADR-normalized stop | **PF 0.62 (inverts)** | 0.94 | 0.53 |

Two kills: (1) **stop-dependent on ES** — swapping the ES-specific 4pt stop for an ADR-scaled one drops
perm-p 0.06→0.30 (ns); a real edge shouldn't hinge on one stop size. (2) **inverts on NQ** — above-EMA
fades are *worse* (PF 0.62 vs 0.94). Caveat: the f2EL fade itself is a loser on NQ (PF 0.88, ES-tuned
geometry), so NQ isn't a perfectly clean test of the feature — but ES stop-dependence + NQ inversion
together are decisive.

**FINAL VERDICT: retire the entire fade-EMA thread.** Every form failed under rigor — down-cross
strength (K-unstable / stale-cross artifact) and failed-reclaim (ES stop-dependent, NQ inverts). No
robust EMA-context edge for the fade. Do NOT wire into the indicator. Book B remains the one validated
result of the RevFT arc (0015/0015b). Samir's recency correction was right and produced a better
feature; it just didn't survive — a clean negative, not a mistake.

---
_Below: the DEAD original down-cross feature, kept for the record._

**Idea (Samir):** only take the f2EL fade (FADE-S, a short of a failed counter-trend long in a bear)
when a **strong move THROUGH the 20-EMA** precedes it — a forceful bear thrust that broke the EMA,
then the failed long we fade. Price-action filter, not the RevFT-conditioning that 0015c refuted.

**Feature (pre-committed to limit over-search):** `cross_str` = strength of the most recent DOWNSIDE
EMA cross in the prior K=10 bars, in ATR14 units = (swing-high before the down-cross − swing-low
after) / ATR, over `[fb-K, fb)`, strictly causal. Secondary `pen_atr` = deepest close/low below EMA
/ATR. Test bed: FADE-S entries from `combined_books_20260724` (n=249; that fade is ~breakeven here,
so the question is whether the filter RESCUES it). `scripts/revft_fade_ema.py`.

## Results
Base FADE-S: n=249, −$7.7/tr, PF 0.98.

**Tercile of cross_str (no threshold):** weak −$45/tr (PF 0.90) · mid −$195 (0.60) · **STRONG +$165
(PF 1.50)**. Strong end unambiguous; mid<weak is a minor non-monotonicity.

**Threshold sweep + permutation-null + train/holdout:**

| filter | n | $/tr | PF | perm-p | train | holdout |
|---|---|---|---|---|---|---|
| ≥1.5 ATR | 131 | +54 | 1.15 | 0.17 | +37 | +76 |
| **≥2.0 ATR (pre-committed)** | 114 | **+126** | 1.36 | **0.039** | +112 | +143 |
| ≥2.5 ATR | 74 | +251 | 1.85 | 0.012 | +286 | +202 |
| ≥3.0 ATR | 44 | +323 | 1.98 | 0.019 | +358 | +273 |

**Year-by-year (≥2.5, n=74):** 2022 +$6.8k · 2023 +$1.3k · 2024 +$2.1k · 2025 +$3.4k solidly positive;
2021/2026 are ±1-trade tails. **Secondary pen_atr FAILS** at every threshold (holdout negative,
perm-p>0.3) — the mechanistically-matched feature (cross *strength*) works while "deep below EMA"
does not, which argues against data-mining.

## Why this passed where 0015c failed
- **Monotone dose-response:** $/tr rises $54→$126→$251→$323 with the threshold — a gradient, not one
  lucky cutoff.
- **Permutation null at a pre-committed round threshold** (≥2.0 ATR, p=0.039) — the strong-cross
  subset beats a random same-size subset of fades. (Swept-best p=0.012 is optimistic; quote 2.0.)
- **Holdout ≥ train** at every threshold ≥2.0.
- **Feature discriminance:** cross-strength works, penetration-depth doesn't — matches the mechanism.

## Verdict & next
Filtering the fade to "only after a ≥2.0-ATR thrust through the EMA" turns the breakeven f2EL into
**+$126/tr, PF 1.36**, keeping ~46% of fades (114/249). Trade-off: ~halves fade count.
**Promote to the full 0015b battery** (cost stress, block-boot DD, engine invariance, LOYO) and
**re-run on the frozen f2EL** (spec PF 1.35) to see if it stacks or overlaps — the base here is the
weak near-final fade. Lean on the pre-committed 2.0 threshold + the dose-response, not the 2.5/3.0
peaks. If it holds on the frozen fade, it lifts both the 2E three-book and the combined portfolio.

## FROZEN-fade re-run — the deciding test (FILTER vs SIZER)  `revft_fade_ema_frozen.py`
Regenerated the frozen f2EL WITH bars (replay detect_entries_causal + pt_new + the run_books FADE
branch): **n=112, +$57.5/tr, PF 1.31** (reconciles to wf_dataset n≈141 / PF 1.28). Unlike the weak
combined_books fade, the frozen base is **already profitable**, which changes the answer.

Tercile: weak (n=46) +$25/tr PF 1.12 · mid (n=30) −$59 PF 0.69 · STRONG (n=36) +$196 PF 2.12.

| mode (≥2.0 ATR) | n | total $ | $/tr | PF |
|---|---|---|---|---|
| base (all fades) | 112 | +6,440 | +58 | 1.31 |
| FILTER strong-only | 58 | +6,272 | +108 | 1.60 |
| the REST (weak/mid) | 54 | **+168** | +3 | 1.02 |
| SIZER 2×strong + 1×rest | — | **+12,712** | — | — |

**The real framing is conviction vs sample size, not FILTER vs SIZER.** Both FILTER and SIZER put the
risk on the strong-cross fades; they differ only in what you do with the weak ones (drop vs downweight).
The numbers make the case for concentrating attractive: FILTER strong-only keeps **97% of the profit
($6,272 of $6,440) on half the trades at PF 1.60 vs 1.31** — on a risk-per-slot basis (the fade shares
prop margin/DD with 2EL/2ES) that is a *better* use of a risk slot, not a worse one. My earlier "don't
filter, you'd lose the breakeven dollars" was wrong: you'd barely lose any dollars.

**The one real blocker is that the split is not statistically confirmed.** On the frozen fade the
**permutation null is NOT significant** (p=0.14–0.37 across thresholds, vs 0.039 on the weak fade), on
n=112 (36 strong). Dose-response holds (weak $25 → strong $196; monotone $80→$108→$175→$219 across thr)
and holdout ≥ train throughout — but at this n the strong subset can't be distinguished from a lucky
slice of an already-good book. So the asymmetry: if the split is REAL, concentrating (filter or heavy
size) is clearly right; if it's NOISE, you've halved a thin, 13%-win, tail-dependent book and made
realized results noisier for nothing.

## LOOKBACK-K SWEEP — the deciding robustness test — FAILED
Samir asked whether K=10 is arbitrary. Re-ran strong(cs≥2.0)-vs-rest across K∈{5,8,10,15,20}:

| K | strong n | strong PF | rest PF | perm-p |
|---|---|---|---|---|
| 5 | 18 | **0.85** | 1.39 | 0.64 |
| 8 | 52 | 1.69 | 1.00 | 0.22 |
| 10 | 58 | 1.60 | 1.02 | 0.26 |
| 15 | 68 | **1.13** | 1.57 | 0.71 |
| 20 | 75 | 1.28 | 1.35 | 0.54 |

**The effect exists only at K=8–10 and INVERTS at K=5/15/20** (at those lookbacks the *weak* crosses are
the better fades). A real "forceful break through the EMA" edge should not care whether it's measured
over 8 or 15 bars. Perm-null never clears at any K (best p=0.22). This is the classic
lucky-window/noise signature — the same one that killed the RevFT→2E confluence (0015c) across *its*
windows.

**Verdict (downgraded): the fade-EMA signal is most likely NOT a real edge.** The K=10 dose-response +
holdout that looked good were riding a lookback sweet spot that doesn't generalize. Do NOT filter, do
NOT size on it. Keep the cross_str *metric* only as an **exploratory chart annotation / forward-watch**
(indicator viz + the chart `docs/living/revft_fade_ema_crosses_20260725.png`), not a rule. If it were
real it would survive the K-sweep and a cross-instrument (NQ) re-run — neither is met.
ORTHOGONAL to RevFT Book B (untouched; Book B remains the validated result).

## Residual value / if revisited
- **Cross-instrument (NQ)** would be the only way to resurrect it — more fades + independent sample. But
  given the K-instability on ES, the prior is low.
- The `cross_str` visualization is still useful to *eyeball* fade context live; just don't trade on it.

## Reproduce
`scripts/revft_fade_ema.py` (weak fade) + `scripts/revft_fade_ema_frozen.py` (frozen fade) →
`data/regime/revft_fade_ema_20260725.parquet`, `revft_fade_ema_frozen_20260725.parquet`.
2E fade trades: `combined_books_20260724.csv` (FADE-S) / regenerated frozen via worktree engine.
