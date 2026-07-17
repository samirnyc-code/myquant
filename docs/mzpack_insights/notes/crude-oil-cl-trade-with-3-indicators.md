---
title: Crude Oil (CL) Trade With 3 Indicators
url: https://www.mzpack.pro/crude-oil-cl-trade-with-3-indicators/
date: 2019-01-22
topic: trade-examples
research_relevance: high
---
## Summary
Annotated CL 02-19 trade example using mzBigTrade, mzVolumeDelta, and mzFootprint on M5 and M3 charts. Two Big Trades (sizes 347 and 110) print during a decline; despite Big Trade sell volume exceeding Big Trade buy volume, price stops falling. The author drills into M3 footprint microstructure to validate that the cluster of Big Trades acts as a support area, implying institutional buying absorbing the selling. The setup is a reversal long off Big-Trade-defined support.

## Key concepts & definitions
- Big Trade: a large (institutional-sized) single transaction detected by mzBigTrade.
- Big Trades can cluster at a price zone and function as a support area even when their net direction (sell > buy volume) looks bearish.
- Multi-timeframe workflow: M5 for signal detection, M3 + footprint for microstructure confirmation.
- Indicators: mzBigTrade (large-trade detection), mzVolumeDelta (buy/sell imbalance), mzFootprint (per-price order flow detail).

## Rules / thresholds / settings
- Big Trade sizes observed: 347 contracts, then 110 contracts (example values, not configured thresholds).
- Timeframes: M5 (context/signal), M3 (footprint confirmation).
- No explicit indicator parameter settings, entry price, stop, or target given.

## Order-flow signature described
Sequence of Big Trades printing into a decline; aggregate Big Trade sell volume > buy volume yet price stops — effort (selling) without result (no further downside). The Big Trades zone then holds as support on the M3 footprint.

## Relevance to our research
Direct example of absorption at an extreme: heavy aggressive selling into a level with no downside progress, with the large-print cluster defining a defended level. Maps onto our large-trade/absorption and defended-level touch-outcome studies.
