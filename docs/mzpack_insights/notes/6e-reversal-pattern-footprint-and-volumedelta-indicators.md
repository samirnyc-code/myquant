---
title: 6E Reversal Pattern: Footprint and VolumeDelta Indicators
url: https://www.mzpack.pro/6e-reversal-pattern-footprint-and-volumedelta-indicators/
date: 2018-12-19
topic: footprint
research_relevance: high
---
## Summary
6E reversal-pattern article that is notable for its precise metric definitions: Bar Delta %, Delta Change, number of trades, dynamic value-area levels (dVAL/dPOC), and absorption support zones. The strategy is built from serial signals that must complete a pattern sequence, with an entry defined as a time-price opportunity; volatility filters such as ATR are suggested for day-reversal patterns. The fetched content was truncated ("READ MORE"), so full setup steps and entry/exit rules were not retrievable.

## Key concepts & definitions
- Bar Delta % = Bar Delta / Bar Volume.
- Delta Change = current bar delta minus prior bar delta.
- Number of trades = number of ticks in a bar (trade-count/density proxy).
- dVAL / dPOC: Dynamic Value Area Low / Dynamic Point of Control — recomputed on each tick, so their historical path can be traced.
- Absorption support zone: "built from one or more consecutive levels of absorptions."
- Time-price opportunity: the combination of price and time in which the entry order should be placed.
- Serial signals: multiple sequential order-flow signals required to complete the pattern before entry.

## Rules / thresholds / settings
- Filter suggestion: use volatility indicators like ATR as a filter for day reversal patterns.
- No numeric thresholds given in the retrievable portion; article truncated.

## Order-flow signature described
Reversal built on consecutive per-price absorption levels forming a support zone, tracked against dynamic profile levels (dPOC/dVAL), with bar-delta%/delta-change metrics quantifying the flow shift. (Full signature truncated in source.)

## Relevance to our research
High: gives concrete formula definitions (Bar Delta %, Delta Change, tick-count density) and the "consecutive absorption levels = support zone" construction — directly reusable as features in our absorption and defended-level detection. Content partially truncated; worth re-fetching the full article if needed.
