---
title: How to use order book in scalping?
url: https://www.mzpack.pro/how-to-use-order-book-in-scalping/
date: 2023-09-24
topic: core-concepts
research_relevance: low
---
## Summary
A short introductory piece on using the order book (DOM) for scalping. Defines the order book, then gives five operational steps: understand the tool, identify price levels with significant liquidity or large buyer/seller imbalance, monitor changes (large orders placed or removed), read order-flow imbalances, and supplement with technical aids (cumulative delta, volume profile, footprint charts). References mzMarketDepth but gives no configuration details, and closes with a risk warning that scalping is high-risk.

## Key concepts & definitions
- Order book: "displays all the buy and sell orders for a particular security. It shows the quantity of orders at different price levels and the liquidity at each level."
- Scalping: requires "fast execution and tight risk management" (no formal definition given).
- Watch for: levels with "significant amount of liquidity" or "large imbalance between buyers and sellers"; "large orders being placed or removed"; levels where "more buy or sell orders" exist.
- Supporting tools: cumulative delta, volume profile, footprint charts; MZpack's mzMarketDepth.

## Rules / thresholds / settings
None given — no numerical parameters, thresholds, or settings.

## Order-flow signature described
Only generically: liquidity concentrations and buy/sell order imbalances at price levels; large resting orders appearing/disappearing as a monitoring cue.

## Relevance to our research
General background; DOM-pressure reads described here require live depth data we do not have historically, so it mostly reinforces the boundary between tape-derivable and DOM-dependent signatures.
