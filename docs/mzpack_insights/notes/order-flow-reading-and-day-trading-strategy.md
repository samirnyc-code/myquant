---
title: Order flow reading and day trading strategy
url: https://www.mzpack.pro/order-flow-reading-and-day-trading-strategy/
date: 2016-02-11
topic: strategies-backtesting
research_relevance: high
---
## Summary
Strategy article arguing that order flow is broader than tape/T&S/DOM reading — for day traders, "order flow on the chart" with a time scale is more practical. The framework pairs a 30-minute Market Profile chart (POC, IBH/IBL, VAH/VAL, single prints) with a 10-second chart for order-flow confirmation, targeting breakouts or reversals at significant levels. Two worked areas: a long at a retest of the prior day's single-print area confirmed by high DOM limit-order density plus a 2655-lot aggressive buy; and a long on a current-day POC breakout after buying initiative, marked by absent aggressive sellers and a massive 5000-lot buy trade.

## Key concepts & definitions
- Order flow on the chart: plotting order-book/executed-flow information on a time-scaled chart rather than raw tape/DOM watching.
- Market Profile levels used: POC, IBH/IBL, VAH/VAL, single-print areas.
- Dual-chart structure: 30-minute primary (levels) + 10-second secondary (order-flow confirmation).
- Two tradeable scenarios at significant levels: breakout or reversal.
- Multi-stage entry: level identification + DOM analysis + aggressive-trade confirmation (no single-indicator entries).

## Rules / thresholds / settings
- Area 1: prior-day single-print retest; DOM shows high density of limit orders; confirmation = 2655-lot aggressive buy → long.
- Area 2: current-day POC retest; no aggressive sellers present; 5000-lot buy trade; long entry "on POC breakout after some initiative to buy."
- Lot sizes are example prints, not configured thresholds. No stops/targets given.
- Indicators: mzMarketDepth, mzAggressiveTrade.

## Order-flow signature described
At the level: stacked/high-density limit orders on the defending side of the DOM, absence of opposing aggression, then a very large aggressive print in the trade direction — passive defense followed by initiative confirming the move.

## Relevance to our research
High: this is our POC/VP-retest touch-outcome problem with explicit confirmation features — DOM limit density (defended level), absence of opposing aggression, and large-print initiative — all computable analogs exist in our reconstructed footprint (except deep DOM history).
