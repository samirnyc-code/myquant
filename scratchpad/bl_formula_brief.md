# Blind Spot FORMULA hunt — master brief (200-day panel)  [S75V, overnight]

## The mission
Find the formula that computes MenthorQ Blind Spots `bl_1..bl_10`. We now have ~200 days of
BL ground truth for 19 instruments + a same-day gamma-level cache for a ~35-ticker basket
(incl. SECTOR ETFs — the current lead hypothesis). Crack it, or rigorously bound what it can't be.

## Ground-truth data (READ THESE)
- **BL history (the TARGET):** `data/menthorq/<SYM>_mq_blindspots_history.csv`
  columns `date,bl_1..bl_10`. 200 sessions 2025-09-30..2026-07-17. SYM in:
  ES1! NQ1! RTY1! YM1! SPX NDX RUT SPY QQQ IWM AAPL MSFT NVDA AMZN GOOG META TSLA CL1! GC1!.
  NOTE bl_1..10 are in MQ's internal order (overlap-score rank), NOT sorted; sort for matching.
- **Basket gamma history (candidate INPUTS):** `scratchpad/bl_basket_gamma.json`
  = {sym: {session_date: {level_name: value}}}. Level names: Call Resistance, Put Support, HVL,
  Call Resistance/Put Support/HVL/Gamma Wall 0DTE, 1D Min, 1D Max, GEX 1..GEX 10.
  Basket incl: SPX SPY QQQ NDX IWM RUT DIA · XLK SMH XLF XLE XLV XLY XLI XLP XLU XLB XLC XLRE XLG ·
  VIX IBIT GLD USO TLT HYG · ES1! NQ1! RTY1! GC1! CL1! · AAPL MSFT NVDA AMZN GOOG META TSLA.
  (If a sym/date is missing it was empty from the API. Spot per day ~= (1D Min+1D Max)/2.)
- Live API if needed (frugal, ONE MQ() instance): `from mq_api import MQ; mq=MQ()`.
  `mq.blindspots(syms,dates)` (BL hist), `mq.per_strike(sym)` / `mq.matrix(sym)` (TODAY-ONLY
  per-strike surface), `mq.get('levels',base=QBOT,tickers=..,level_types='gamma_levels',dates=..)`.

## What MenthorQ documents (from their KB — treat as hints, verify everything)
- BL API output = "Blind Spots V2" = ranges from "highly correlated assets with strong OVERLAPS".
  BL1 = most overlap, BL10 = less. Not strength-ranked. Assets named: SPX/SPY, QQQ/NDX, IWM,
  Mag7, gold, VIX, crude, Bitcoin, and SECTOR ETFs ("major sector ETFs like gold and USO").
- Conversion is a FIXED per-pair ratio (QQQ->NQ = 41.26; SPY->ES ~ 10). "Never change the ratio."
- V1 (a different product) = single proxy copied by fixed ratio; NOT the API output.

## ESTABLISHED — do NOT redo, build on or challenge with the 200-day panel
1. **Exact reconstruction from published GAMMA LEVELS failed on 1 day:** BL's odd 2-decimals
   (7579.32) can't come from round gamma levels x clean ratio. => inputs are likely the
   per-strike surface, OR a conversion of ANOTHER asset's (odd-decimal) BL/levels.
2. **Cross-asset STRUCTURAL confluence CONFIRMED w/ power:** ES BL sit nearer pooled cross-asset
   {CR,PS,HVL,Gamma Wall 0DTE} (spot-ratio mapped) than random — 200-session z=+8.9, t~-11,
   81.5% of days. So BL DO track cross-asset structural gamma zones. (`scratchpad/bl_confluence_200d.py`)
3. **Cross-instrument BL is related but NOT a clean copy:** ES BL vs 10.08xSPY BL = 8pt median
   (0.12%); vs SPXx1.005 = 7.8pt; NQ vs QQQx41.37 = 36pt. ~4x better than random, not exact.
4. **REFUTED (1 day, ES+NQ):** momentum, gamma-magnitude selection, per-strike GEX sign-flips,
   Q-score, IV expected-move band, OI-minima, distance-rank index, beta-map, additive-basis.
5. **BL count/structure:** always 10. ES 5-above/5-below spot; NQ 7/3 — split is NOT fixed.

## Rules of engagement (STRICT)
- Every "match/fit" MUST beat a NULL (permuted BL, random points in the BL band, or matching
  against a DIFFERENT day's inputs). Report REAL vs NULL and a p-value/z, always.
- With 200 days x 10 BL and a big feature set, OVERFITTING is the enemy. TRAIN/TEST SPLIT or
  cross-validate: fit on one date range, report error on a held-out range. An in-sample-only fit
  is not evidence.
- A real formula must reproduce BOTH ES and NQ (and ideally SPY/QQQ) with the SAME mechanism.
- Exact reconstruction (residual ~0.00 to the penny, out-of-sample) = the prize. A tight-but-not-
  exact statistical mapping is a lesser (still valuable) result — report effect size honestly.
- Refuting a whole class cleanly (e.g. "sector ETFs add nothing beyond SPY/QQQ") is valuable.
- Write findings to `scratchpad/bl_formula_<yourangle>.md` and return a tight structured summary
  (hypothesis, method, REAL vs NULL w/ numbers, in/out-of-sample, verdict, best formula + residual).
