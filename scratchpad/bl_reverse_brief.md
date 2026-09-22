# Blind Spot (BL) reverse-engineering — shared brief for agents

## Goal
Reverse-engineer how MenthorQ computes Blind Spot levels `bl_1..bl_10` from data we own.
MenthorQ's API exposes BL for the **current EOD only** (confirmed: no history route, all
date/range params ignored). So the ONLY way to get BL history for backtesting is to derive a
formula from the one day of ground truth we captured. Your job: find that formula, or rigorously
refute a class of hypotheses.

## Ground truth (date = 2026-07-17, the last trading day)
ES1! spot ≈ 7494.75. NQ1! spot ≈ 28768.25.

ES1! blind spots:
  bl_1=7579.32 bl_2=7427.49 bl_3=7566.74 bl_4=7484.72 bl_5=7835.74
  bl_6=7471.50 bl_7=7246.19 bl_8=7279.90 bl_9=7603.29 bl_10=7615.64

NQ1! blind spots:
  bl_1=29090.25 bl_2=28504.10 bl_3=29463.36 bl_4=29228.17 bl_5=28892.27
  bl_6=28327.97 bl_7=29300.79 bl_8=27936.18 bl_9=29048.15 bl_10=29489.09

Cached at: scratchpad/bl_groundtruth_raw.json

## Data you own
- Gamma-level history (EOD) for the FULL correlated universe, as JSONL, one dict per line under
  key `item` with `item.date` and `item.levels[]` where each level has
  `level_type=="gamma_levels"` and `level_values=[{name,value,gex}]`. Names include:
  Call Resistance, Put Support, HVL, 1D Min, 1D Max, Call Resistance/Put Support/HVL/Gamma Wall 0DTE,
  GEX 1..GEX 10 (each with a signed `gex`).
  Files: data/menthorq/{SYM}_mq_levels_history_raw.jsonl for SYM in
  ES1!, NQ1!, RTY1!, GC1!, CL1!, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA.
  (SPX file exists too but its latest date is 2026-07-15, NOT 7/17 — beware.)
- Live API client: `scripts/mq_api.py` -> `from mq_api import MQ; mq=MQ()`. Methods:
  mq.levels(sym) [today gamma], mq.blindspot_levels(sym), mq.per_strike(sym), mq.matrix(sym),
  mq.metrics(sym), mq.vol_insights(sym), mq.get('tickers/{sym}/candles', interval=..,from_..).
  NOTE: MQ() spins up headless Playwright to grab a Bearer token (~30-60s). Reuse ONE instance.
  Be frugal with live calls. Everything gamma is TODAY-only via API but we have history in JSONL.

## What is already established (do NOT re-derive; build on or challenge)
1. Dense-pool artifact: mapping ALL ~204 correlated gamma levels into ES by spot-ratio and taking
   nearest match to each BL gives median err ~1.5pt — but RANDOM price points score the same
   (~1.5pt). Pool density, NOT signal. Any nearest-match claim MUST beat a permutation/random null.
2. Structural-only pool (Call Resistance/Put Support/HVL/Gamma Wall) mapped by spot-ratio:
   real median err 2.15pt vs null 4.28pt => ~2x enrichment. Real but weak, one day.
3. Additive-basis map is NOT better than ratio map (and is meaningless across mixed scales).
4. BLs do NOT track gamma magnitude |gex| — the biggest gamma walls are 15-27pt from any BL.
5. Structural: exactly 5 BL below spot and 5 above, for ES. (Check if NQ is also 5/5.)

## Mapping convention used so far
level_in_ES = asset_gamma_level * (ES_spot / asset_spot), where asset_spot=(1D Min+1D Max)/2.

## Rules
- Every "match" claim must beat a null (permute BL, or random points in the BL band, or match
  against a DIFFERENT day's gamma levels). Report REAL vs NULL, always.
- A real formula must reproduce BOTH ES and NQ ground truth with the SAME mechanism. Cross-check.
- The 2-decimal precision of BL values (e.g. 7579.32) is a fingerprint — exact reconstruction
  of those decimals from round gamma levels + a clean ratio would be near-proof.
- Be skeptical and adversarial. Refuting a hypothesis cleanly is as valuable as confirming one.
- Write findings to scratchpad/bl_findings_<yourangle>.md and return a tight structured summary.
