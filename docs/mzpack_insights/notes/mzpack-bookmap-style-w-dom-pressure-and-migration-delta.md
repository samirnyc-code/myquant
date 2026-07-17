---
title: MZpack Bookmap Style w DOM Pressure and Migration Delta
url: https://www.mzpack.pro/mzpack-bookmap-style-w-dom-pressure-and-migration-delta/
date: 2019-08-30
topic: core-concepts
research_relevance: medium
---
## Summary
Shows a Bookmap-style NT8 chart built from mzMarketDepth (liquidity heatmap plus an "Overall Liquidity Migration" mini-chart, computed here as OfferBid delta) and mzBigTrade (DOM pressure from Level 2 data). Two reversal-indicating signals are illustrated: a resistance level visible on the liquidity-migration mini-chart, and a concrete DOM pressure print — 99 lots of DOM pressure at the bid side (green triangle) against a 211-lot sell order. Both are read as resistance usable "to determine a reversal pattern." A downloadable ETH chart template is included.

## Key concepts & definitions
- Overall Liquidity Migration mini-chart: bars on an additional mini-chart representing migration of resting liquidity; example uses OfferBid delta calculations (mzMarketDepth feature).
- DOM Pressure: "uses Level 2 data for analysis and shows pressure by limit orders in the DOM against the direction of the trade" (mzBigTrade feature).

## Rules / thresholds / settings
No indicator parameter values given. One concrete signal example: "99-Lot of DOM pressure at bid side (green triangle) against 211-Lot sell order" — i.e., limit-side replenishment nearly half the size of the aggressive order. Trade logic: both signal types indicate resistance → use to identify a reversal pattern.

## Order-flow signature described
A large aggressive sell order (211 lots) hits the bid, and instead of the bid collapsing, limit buyers press back with 99 lots of DOM pressure at the bid (green triangle) — passive defense against the trade's direction. Concurrently the liquidity-migration mini-chart shows a resistance level, i.e., resting liquidity shifting against the move.

## Relevance to our research
Relevant to defended-level and iceberg/refill detection: the 99-vs-211-lot example is a quantifiable refill-ratio signature (passive replenishment vs aggressive volume) we can replicate; liquidity-migration delta is a DOM-pressure feature candidate, though we lack deep historical DOM (see Databento note).
