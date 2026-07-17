---
title: ES 03-19 Scalping using MZpack Indicators
url: https://www.mzpack.pro/es-03-19-scalping-using-mzpack-indicators/
date: 2019-02-07
topic: trade-examples
research_relevance: medium
---
## Summary
Short annotated ES scalp (author: Konstantin) using M5, 400-tick and 20-tick charts with mzBigTrade, mzVolumeProfile, mzVolumeDelta and mzMarketDepth. On the M5, price halted after a Negative Delta Cluster near VWAP. On the 400-tick chart, two Big Positive Delta prints (~1.2K) appeared in the Volume Profile after the negative cluster — this reversal signature triggered the LONG. The position was closed after price stalled near the VAH.

## Key concepts & definitions
- Negative Delta Cluster: a cluster of net-selling delta in the volume profile; here it stopped price near VWAP (selling that failed to make progress).
- Big Positive Delta: large positive delta prints (~1.2K contracts) appearing after the negative cluster = buyers taking over; entry trigger.
- Multi-timeframe execution: M5 for context, 400-tick for signal, 20-tick for micro reading.
- VAH used as scalp target/exit area.

## Rules / thresholds / settings
- Entry: LONG after 2 Big Positive Delta (~1.2K each) appear in the VP following a Negative Delta Cluster near VWAP.
- Exit: close when price stops near VAH.
- No explicit indicator input parameters, stop rules, or numeric settings beyond the 1.2K delta reference.

## Order-flow signature described
Selling delta clusters into VWAP that fail to push price lower (effort vs. no result), then large positive delta prints flipping control to buyers — the reversal fires from the failed-seller zone and runs to VAH.

## Relevance to our research
Effort-vs-result absorption at a VP/VWAP level followed by delta flip — matches our absorption-at-extremes signature and VAH/VAL touch-outcome framing.
