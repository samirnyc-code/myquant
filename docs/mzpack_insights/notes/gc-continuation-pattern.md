---
title: GC. Continuation Pattern
url: https://www.mzpack.pro/gc-continuation-pattern/
date: 2018-07-24
topic: trade-examples
research_relevance: medium
---
## Summary
GC (gold) continuation-pattern example built around spoofing detection with mzMarketDepth, confirmed by mzBigTrade. Spoofing is defined as flashed fake liquidity near the best bid/ask that will never be filled, placed by intraday algorithms to pressure one side. Spoofing #1 pressures the highs and triggers stop-losses; Spoofing #2 aligned with continuation selling confirms the short entry. The author stresses that all pieces of the setup are required for a confident short.

## Key concepts & definitions
- Spoofing: "a big amount of flashed liquidity near best bid or best ask which will never be filled. Fake liquidity is placed by some intra-day algorithm" to pressure buyers or sellers.
- Two-stage spoof setup: first spoof creates pressure/stop-run at the high; second spoof confirms selling continuation.
- Confluence requirement: "we need all pieces of that setup to make a confident short trade."
- Indicators: mzMarketDepth (liquidity/spoof identification), mzBigTrade (order-flow confirmation).

## Rules / thresholds / settings
None given — no size thresholds for spoof liquidity, no entry/stop/target parameters.

## Order-flow signature described
DOM signature: large liquidity flashed near best bid/ask that pulls before being hit (never filled), repeated on the continuation side, combined with big-trade prints confirming aggressive selling.

## Relevance to our research
Relevant background for DOM pressure and fake-vs-real liquidity: distinguishing pulled/spoofed size from genuinely defended (refilled/iceberg) levels is the inverse of our iceberg-refill detection problem.
