---
title: What is DELTA RATE in mzFootprint Indicator?
url: https://www.mzpack.pro/what-is-delta-rate-in-mzfootprint-indicator/
date: 2023-02-26
topic: footprint
research_relevance: medium
---
## Summary
Short explainer of the Delta Rate metric in mzFootprint: "the rate of delta change... measured in the chosen time interval (milliseconds) or tick interval." The indicator also shows the price interval that accompanied the delta change, and displays only one maximal (by modulo/absolute value) Delta Rate value per bar in the Statistics Grid and on the chart. High Delta Rate readings flag intense one-sided market-order activity — stop ranges triggering, reversals, or breakouts. Presented as a recognition tool rather than a rule-based trading signal.

## Key concepts & definitions
- Delta Rate: "the rate of delta change. This rate is measured in the chosen time interval (milliseconds) or tick interval."
- Display: the accompanying price interval is shown; "only one maximal (by modulo) value of Delta Rate is shown for the bar in the Statistics Grid and on the chart."
- High sell/negative Delta Rate = "intensive selling (a lot of sell market orders have been matched with buy limit orders)."
- High Delta Rate indicates: a range of stops triggering, reversals, or breakout.

## Rules / thresholds / settings
None given — no formulas with values, numerical thresholds, or default parameter settings. The measurement interval (ms or ticks) is user-chosen but no defaults stated.

## Order-flow signature described
A burst of one-sided aggression compressed in time: rapid delta change over a short ms/tick window, paired with a price interval traversed — the intrabar analog of a stop run or initiative breakout.

## Relevance to our research
Delta Rate is essentially our intrabar delta-burst / Vol-per-sec feature; it supports using delta velocity (not just bar delta) to separate stop runs from absorption at level touches, complementing the stop-run red flag in the Mirror Levels article.
