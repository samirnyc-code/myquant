# 0015d — f2EL Fade × Strong-Move-Through-EMA Filter — 2026-07-25
**Series:** MC Setup Research Notes · Note 0015d (companion to 0015c)
**Confidence:** Promising, first-pass rigor PASSED (unlike the 0015c confluence). Dose-response +
permutation-null p=0.039 at a pre-committed threshold + holdout ≥ train. NOT yet graduated: swept
threshold, moderate n, tested on the *weak* near-final fade. Deserves the full 0015b battery.

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

**Decision: SIZER, not FILTER.** The non-strong fades net +$168 (breakeven, PF 1.02) — **not dead**.
Filtering to strong-only keeps ~the same total $ on half the trades (concentrates, doesn't grow);
sizing up the strong-cross fades ~doubles total $ ($6.4k→$12.7k) while the rest don't lose. So do NOT
trade only strong fades — keep all, lean bigger on strong.

**But weaker evidence than the weak-fade result:** on the frozen fade the **permutation null is NOT
significant** (p=0.14–0.37 across thresholds, vs 0.039 on the weak fade). Dose-response holds (weak $25
→ strong $196, monotone $80→$108→$175→$219 across thr) and holdout ≥ train throughout, but at n=112 the
strong subset isn't distinguishable from a lucky slice of an already-good book. The 0015d "filter
rescues the fade" was real *for the weak near-final fade* only.

**Corrected verdict:** the strong-move-through-EMA is a **sizing lean on the fade, not a filter, and
NOT yet confirmed on the frozen fade** (n=112 thin, null ns). Carry it forward; re-check as fades
accumulate. Do not change the fade rule today; definitely do not filter (would cut breakeven-not-dead
trades). ORTHOGONAL: keep it out of RevFT Book B — this is a 2E-fade idea.

## Reproduce
`scripts/revft_fade_ema.py` (weak fade) + `scripts/revft_fade_ema_frozen.py` (frozen fade) →
`data/regime/revft_fade_ema_20260725.parquet`, `revft_fade_ema_frozen_20260725.parquet`.
2E fade trades: `combined_books_20260724.csv` (FADE-S) / regenerated frozen via worktree engine.
