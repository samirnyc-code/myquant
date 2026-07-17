---
title: MZpack Settings for Indian Market (NSE)
url: https://www.mzpack.pro/mzpack-settings-for-indian-market/
date: 2020-05-27 (updated 2021-03-05)
topic: platform-misc
research_relevance: low
---
## Summary
A configuration guide for using MZpack indicators on Indian NSE futures (NIFTY, BANKNIFTY), whose data providers do not supply historical bid/ask data. The workaround is the "Hybrid" order-flow calculation mode: UpDownTick calculation on historical data, BidAsk calculation on real-time data. It also gives lot-size dividers and ticks-per-level recommendations for NIFTY and BANKNIFTY, and notes mzBigTrade needs per-strategy fine-tuning (suggested on 10-tick charts for entry refinement). A downloadable BANKNIFTY–NIFTY workspace template is provided.

## Key concepts & definitions
- Hybrid orderflow calculation mode: "uses UpDownTick calculation for historical data and BidAsk calculation for real-time data" — needed where historical bid/ask is unavailable (v3.15.11+).
- Split / LastKnownSide modes: alternatives recommended for spread trades.
- Non-crypto volumes divider: divides reported volume by lot size so charts show lots, not units (v3.16.3+).
- Ticks per level: footprint/profile price aggregation setting, instrument-specific.

## Rules / thresholds / settings
- Non-crypto volumes divider: NIFTY = 75, BANKNIFTY = 20 (lot-size factors).
- Ticks per level: NIFTY = 40 (recommended for 240 Range chart with mzFootprint and 30-min chart with mzVolumeProfile); BANKNIFTY = 1500.
- Orderflow calc mode: Hybrid (spread trades: Split or LastKnownSide).
- Version requirements: Hybrid mode 3.15.11+, volumes divider / workspace template 3.16.3+.
- mzBigTrade: fine-tune per strategy; use on 10-tick charts for entry refinement.

## Order-flow signature described
None — configuration-only article.

## Relevance to our research
General background. The Hybrid mode caveat is a useful reminder that historical footprints built without true bid/ask data (UpDownTick inference) are lower fidelity — our NT8 tick reconstruction with real bid/ask avoids this.
