---
title: "02/07/2019. Breakeven E-mini SP500 Trade"
url: https://www.mzpack.pro/02-07-2019-breakeven-e-mini-sp500-trade/
date: 2019-02-08
topic: trade-examples
research_relevance: high
---
## Summary
Annotated ES long that ended breakeven (published 2019-02-08). Setup: price tested a support zone (session VAL) with a huge positive COT Low of 1912 and a bar-delta flip from -2276 to +3834, read as institutional accumulation. DOM/tape signatures: multiple DOM support (green triangles), iceberg orders on the BID side (fuchsia contours), a buy initiative over 400 lots, and "predatory" sell trades met by huge DOM support on the bid. Entry on the pullback as liquidity migrated to the BID side; stop under the 2nd std deviation of the session VP, target at M30 session VWAP (R:R 2.5:1). Price returned to entry and the breakeven order triggered. Workspace "MZpack – Day Trading – ES – v1.4" referenced.

## Key concepts & definitions
- COT Low: MZpack cumulative-delta reading at the low; a huge positive COT Low (+1912) at support indicates buyers absorbing.
- Delta flip: prior-bar delta -2276 to +3834 next bar = accumulation signature.
- Iceberg orders: hidden refill on the BID side, shown as fuchsia contours by mzMarketDepth.
- Predatory sell trades: aggressive sells (red boxes) that get met with big/average DOM support on the bid side without price breaking.
- Liquidity migration: Offer/Bid delta declining = liquidity concentrating on the bid side (demand).
- Indicators used: mzFootprint (8 Range chart), mzMarketDepth (DOM, 10-tick), mzBigTrade, mzVolumeProfile (1-min and 30-min), mzVolumeDelta.

## Rules / thresholds / settings
- Signal sizes cited: COT Low +1912; delta -2276 → +3834; buy initiative >400 lots.
- Entry: on the pullback when Offer/Bid delta declines (liquidity migrating to bid).
- Stop: under the 2nd standard deviation of the session Volume Profile.
- Target: M30 session VWAP; R:R 2.5:1.
- Charts: 8 Range (footprint), 10-tick (DOM), 1-min + 30-min VP confluence. No individual indicator parameter settings disclosed.

## Order-flow signature described
At session VAL: aggressive/"predatory" sells hitting the bid meet multiple resting DOM support and bid-side icebergs (refills); bar delta flips strongly positive; a >400-lot buy initiative fires; Offer/Bid liquidity delta declines as depth migrates to the bid. Classic absorption + defended-level footprint with hidden (iceberg) buyers.

## Relevance to our research
The single richest example in this batch: it combines absorption at an extreme (big sells, no downside progress, delta flip), iceberg/refill detection on the bid, defended-level DOM support, and VP-based stop/target placement (2nd std dev, session VWAP) — directly on-point for our touch-outcome and iceberg studies.
