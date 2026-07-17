---
title: ImbalanceMomentum Strategy
url: https://www.mzpack.pro/imbalancemomentum-strategy/
date: 2022-09-24
topic: strategies-backtesting
research_relevance: low
---
## Summary
A brief work-in-progress announcement of a custom strategy built with the MZpack API for NinjaTrader 8, described as "a pretty simple strategy." It signals on bar close from stacked Imbalance and/or Absorption zones and enters with limit orders placed relative to those support/resistance zones. Stop loss goes under the zone or under the signal bar. No parameters, thresholds, or backtest results are given; the post ends with "More stuff need to be done…".

## Key concepts & definitions
- ImbalanceMomentum: bar-close signal strategy; "opens long or short on bar close depending on stacked Imbalance And/Or Absorption zones occurred."
- Entries: "limit orders placed relatively to these support/resistance zones."
- Risk: "The stop loss order can be placed under the zone or under the signal bar."

## Rules / thresholds / settings
None given — no numerical parameters, imbalance/absorption thresholds, or performance metrics.

## Order-flow signature described
Only referenced abstractly: stacked imbalance zones and absorption zones acting as support/resistance; no tape/footprint detail provided.

## Relevance to our research
Low direct value, but the design pattern (limit entries at stacked-imbalance/absorption zones, stop under the zone) mirrors the harness structure of our level-touch R/R tests.
