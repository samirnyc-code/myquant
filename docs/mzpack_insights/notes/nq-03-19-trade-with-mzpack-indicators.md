---
title: NQ 03-19 Trade with MZpack Indicators
url: https://www.mzpack.pro/nq-03-19-trade-with-mzpack-indicators/
date: 2019-02-06
topic: trade-examples
research_relevance: medium
---
## Summary
Annotated NQ (Nasdaq, March 2019 contract) short using M15, M5 and 20-tick charts with mzBigTrade, mzVolumeProfile, mzMarketDepth and mzVolumeDelta. On M15, price met resistance at the VAH after a long-side volume-delta expansion. The M5 gave the key signal: sell volume delta greater than long (buy) volume delta near the VAH — buying weakening despite elevated price. Short executed on the 20-tick chart; covered near VAL after price stalled with sell delta still exceeding buy delta.

## Key concepts & definitions
- VAH resistance test: price reaches Value Area High after a buy-delta expansion.
- Volume delta divergence: sell-side delta exceeding buy-side delta at/near VAH while price is elevated = institutional rejection of higher prices; the short trigger.
- Execution timeframe: 20-tick chart for entry; M15 for context; M5 for signal.
- Exit at VAL when price stops (sell delta still dominant, target reached).

## Rules / thresholds / settings
- Entry condition: Sell Volume Delta > Long Volume Delta near VAH (after prior buy-delta expansion into the level).
- Exit condition: close near VAL after price is stopped while Sell Volume Delta > Long Volume Delta.
- No numeric parameters, thresholds, or indicator settings given.

## Order-flow signature described
Delta divergence at resistance: price holds at/near VAH but net delta turns and stays sell-dominant — sellers overwhelming responsive buyers at the top of value; the move rotates value-area edge to edge (VAH to VAL).

## Relevance to our research
Direct CVD/delta divergence at a VP edge and a full VAH-to-VAL value-area rotation — informs our CVD-divergence signature and VP-touch outcome labeling (rejection at VAH → traverse to VAL).
