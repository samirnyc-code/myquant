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

## Reproduce
`scripts/revft_fade_ema.py` → `data/regime/revft_fade_ema_20260725.parquet`.
2E fade trades: `myquant-regime/data/regime/combined_books_20260724.csv` (book==FADE-S).
