---
title: A Question On Overall Liquidity Migration
url: https://www.mzpack.pro/a-question-on-overall-liquidity-migration/
date: 2019-01-28
topic: core-concepts
research_relevance: high
---
## Summary
Q&A post (author: Mikhail) answering a user question about the mzMarketDepth indicator's Liquidity Migration plot types: colors changed when switching Plot type even though bid/offer amounts were unchanged. The answer: the indicator is correct — the two plot types encode different quantities. "OfferBid" plots the migration side directly (red line = migration on offer; offer migration is resistance to upward movement), while "OfferBidDelta" plots Offer Migration minus Bid Migration, with color determined by sign relative to zero. The post also describes a spoofing-like signature: sharp offer pressure at the end of a swing rejected within about 5 seconds.

## Key concepts & definitions
- Liquidity Migration: movement of resting buy/sell orders across price levels within the order book (DOM).
- DOM (Depth of Market): visual representation of order quantities at various price levels.
- OfferBid plot type: red line = migration on the offer; positive offer migration = resistance to price moving up (and symmetrically for bid).
- OfferBidDelta plot type: Offer Migration − Bid Migration; positive values = offer-side pressure, negative = bid-side pressure (color by sign vs zero).
- Spoofing signature: temporary large orders creating sharp one-sided DOM pressure that vanishes almost immediately.

## Rules / thresholds / settings
- Spoofing scenario timing: sharp pressure on the offer at the end of a swing with rapid rejection lasting "no more than 5 seconds."
- No other threshold settings or parameters detailed.

## Order-flow signature described
End-of-swing DOM signature: a sudden spike of offer-side liquidity (pressure against further upside) that is pulled/rejected within ~5 seconds — flagged as potential spoofing rather than genuine supply. Genuine migration shows as sustained offer- or bid-side dominance in the OfferBid/OfferBidDelta plots.

## Relevance to our research
Directly relevant to DOM-pressure features: defines a computable liquidity-migration delta (offer − bid migration) and a concrete spoof filter (sub-5-second pull) — useful for separating real defended levels/icebergs from fake DOM pressure at extremes.
