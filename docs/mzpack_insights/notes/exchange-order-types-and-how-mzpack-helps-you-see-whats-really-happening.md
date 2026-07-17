---
title: Exchange Order Types (and How MZpack Helps You See What's Really Happening)
url: https://www.mzpack.pro/exchange-order-types-and-how-mzpack-helps-you-see-whats-really-happening/
date: 2026-01-06
topic: core-concepts
research_relevance: medium
---
## Summary
A primer on exchange order types (market, limit, stop-market, stop-limit, marketable/aggressive limit, icebergs) and time-in-force rules, then maps each behavior to the order-flow signature it leaves and the MZpack indicator that visualizes it. Defines sweeps, stop runs, diagonal imbalance, and absorption at a conceptual level, and introduces DOM pressure/DOM support as measured by mzBigTrade. No numerical thresholds.

## Key concepts & definitions
- Market order: demands immediate execution, consumes liquidity at best bid/ask and possibly deeper; "You get filled quickly, but price is uncertain — especially during volatility."
- Limit order: provides liquidity; "It may not fill — your priority depends on price level and queue position."
- Stop order (stop-market): converts to market at the stop level; "can execute through slippage."
- Stop-limit: triggers at stop price then submits a limit; "better control than stop-market, but you risk not getting filled in fast moves."
- Marketable (aggressive) limit: limit placed through the spread for immediate execution; institutions use it to "reduce worst-case slippage."
- TIF: DAY (expires at session end); GTC (until canceled); IOC ("fill what you can immediately, cancel the rest"); FOK ("must fill completely immediately or cancel").
- DOM pressure: liquidity added/removed at best price during execution. DOM support: liquidity in the tail post-execution, associated with Market-Limit activity (both measured by mzBigTrade).

## Rules / thresholds / settings
None given — no numerical thresholds or configurable parameters in this article.

## Order-flow signature described
- Sweeps: "trades that consume liquidity across multiple price levels" — initiative market orders or triggered stops.
- Stop runs: "sudden bursts of aggressive buying/selling and fast delta expansion."
- Diagonal imbalance: "one-side dominance across adjacent price levels (often initiative behavior)."
- Absorption: "aggressive pressure meets passive liquidity and fails to continue, often followed by rejection."
- Iceberg: hidden limit liquidity, detected live/replay.
- Indicator mapping: mzBigTrade (sweeps, icebergs, DOM pressure/support, Tape and Stacked Tape presentations); mzFootprint (bid/ask volume, delta, imbalance, absorption per bar); mzVolumeDelta / mzDeltaDivergence (price vs. delta disagreement); mzMarketDepth (resting limits, historical DOM blocks, DOM imbalance, liquidity migration); mzVolumeProfile (volume concentration, thin travel zones, POC/Value Area).

## Relevance to our research
General background taxonomy, but useful glossary: its stop-run vs. absorption distinctions and the DOM pressure/support definitions clarify which signatures are tape-derivable (usable in our tick reconstruction) vs. DOM-dependent (not available historically).
