---
title: What Is COT And How To Use It In Day Trading?
url: https://www.mzpack.pro/what-is-cot-and-how-to-use-it-in-day-trading/
date: 2018-06-14
topic: core-concepts
research_relevance: high
---
## Summary
Concept article defining MZpack's intraday "COT" (Commitment Of Traders — not the CFTC report): cumulative bid/ask delta anchored at the moment price makes a new high (COT High) or new low (COT Low). COT measures the buy/sell balance reaction after a new price level is reached. In an uptrend the guidance is to watch COT Low and bar delta, with COT High staying neutral or slightly negative; a growing negative COT High while price holds at the highs signals strong support by buy limit orders.

## Key concepts & definitions
- COT (here): cumulative bid/ask Delta "starting from the moment when the price makes new high or repeats previous one" — reveals buy/sell balance after a new level is reached. Two variants: COT High and COT Low.
- Rejection read: if a new high is rejected, COT High turns negative and falls.
- Absorption read: price staying at the highs while COT High grows more negative (in absolute value) = aggressive selling absorbed by buy limit orders ("strong support by buy limit orders").

## Rules / thresholds / settings
- Uptrend rule: "look mainly at COT Low and bar Delta"; "COT High must be neutral or slightly negative."
- No numeric thresholds or settings given.

## Order-flow signature described
Price pins at/near the high; cumulative delta from the moment of the new high goes increasingly negative yet price does not fall — sellers hitting into passive buyers, i.e., limit-order absorption at the extreme.

## Relevance to our research
High: COT High/Low is exactly our anchored-CVD-at-extreme absorption metric (delta into no-progress). A cumulative delta anchored at each new high/low touch is directly computable from our reconstructed ES footprint for level-touch outcome features.
