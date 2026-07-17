---
title: Overall Liquidity Migration Feature In mzMarketDepth Indicator
url: https://www.mzpack.pro/overall-liquidity-migration-feature-in-mzmarketdepth-indicator/
date: 2019-01-17
topic: core-concepts
research_relevance: medium
---
## Summary
Feature explanation (not a trade methodology) of the "Overall Liquidity Migration" plot in mzMarketDepth. It aggregates how resting liquidity migrates across DOM levels and plots totals at the bottom of the chart. Two display modes are offered (separate Offer/Bid totals, or their delta), plus a Cumulate option to accumulate migration bar-to-bar. An example interprets a Migration Delta of about -1200 lots.

## Key concepts & definitions
- Overall Liquidity Migration: visual plot of total liquidity movement across market-depth levels.
- OfferBid mode: two lines — total migration on Offer and total migration on Bid.
- OfferBidDelta mode: one line/candles — total Offer migration minus total Bid migration.
- Cumulate option: migrations accumulate bar-to-bar instead of resetting each bar.
- Interpretation: negative migration delta = liquidity removed from ask side or added to bid side.

## Rules / thresholds / settings
- Example value only: Migration Delta ≈ -1200 lots. No entry/exit rules or configured thresholds given.

## Order-flow signature described
DOM-level signature: net migration of resting orders between bid and ask sides; a strongly negative delta indicates the passive book shifting supportive of the bid (ask pulled and/or bid stacked).

## Relevance to our research
Background for DOM-pressure features: a cumulative bid/ask liquidity-migration delta is a candidate feature for detecting defended levels and pulling/stacking behavior, though we lack historical deep DOM data (Databento thread).
