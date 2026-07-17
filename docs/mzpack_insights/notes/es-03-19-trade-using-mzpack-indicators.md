---
title: ES 03-19 Trade using MZpack Indicators
url: https://www.mzpack.pro/es-03-19-trade-using-mzpack-indicators/
date: 2019-02-03
topic: trade-examples
research_relevance: medium
---
## Summary
Annotated ES long (author: Konstantin) on M5 + 400-tick charts using mzBigTrade, mzVolumeProfile and mzVolumeDelta. Price was stopped in the 2696.00–2697.00 zone on M5; a Negative Delta Cluster formed after several SELL Big Trades (selling that exhausted without progress). On the 400-tick chart, a Big Positive Delta (~1.1K) appeared in the Volume Profile after the negative cluster — the reversal trigger for the LONG. The position was closed near POC and VWAP confluence.

## Key concepts & definitions
- Price-stop zone: 2696.00–2697.00 on M5 — support where selling failed to break lower.
- Negative Delta Cluster after several SELL Big Trades: institutional selling pressure that exhausted at the zone.
- Big Positive Delta (~1.1K) after the negative cluster: delta flip / reversal trigger.
- Exit at POC + VWAP confluence.

## Rules / thresholds / settings
- Entry: LONG when a Big Positive Delta (~1.1K) prints on the 400-tick VP after a Negative Delta Cluster + several SELL Big Trades at a price-stop zone.
- Exit: near POC and VWAP.
- Zone: 2696.00–2697.00. No other indicator parameters, stop rules, or numeric settings given.

## Order-flow signature described
Repeated large sell prints and a negative delta cluster into a support zone with no downside progress (absorption/exhaustion), then a single large positive delta print flipping control — long fires from the failed-seller zone and runs to POC/VWAP.

## Relevance to our research
Same absorption-then-delta-flip template as the ES scalping post: delta into no-progress at a defined zone, reversal to POC — maps to our absorption-at-extremes signature and POC-retest outcome study.
