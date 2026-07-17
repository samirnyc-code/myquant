---
title: Using Iceberg Orders and DOM Pressure Pattern In Day Trading
url: https://www.mzpack.pro/using-iceberg-orders-and-dom-pressure-pattern-in-day-trading/
date: 2021-10-01
topic: core-concepts
research_relevance: high
---
## Summary
Defines iceberg orders and DOM pressure as detected/visualized by the mzBigTrade indicator, and describes a reversal trade built from them. An iceberg is a limit order whose main size is hidden from the order book and requires real-time algorithmic analysis to detect; icebergs typically appear on reversals of local trends. DOM pressure is the behavior of liquidity in the path of a market order: liquidity being added or removed at the best bid/ask right after matching. The article's trade example is a "reversal order flow cluster" — heavy sell market orders absorbed by buy icebergs plus DOM pressure — bought on breakout with a stop below the cluster. Methodology advice: analyze the big picture first, then drill into order flow and microstructure.

## Key concepts & definitions
- Iceberg order: "a special limit order. The main size of an iceberg order is not shown in the order book." Hidden size cannot be determined without real-time algorithmic analysis. Typically appear "on reversals of local trends." Drawn with a fuchsia contour in mzBigTrade.
- DOM Pressure: "the behavior of liquidity on the way of a market order"; emerges when market orders match with limit orders in the depth-of-market. Drawn as a triangle.
- Positive DOM pressure: "adding the liquidity on the best Bid or Ask price right after matching" — represents "resistance to the trend."
- Negative DOM pressure: "removing the liquidity on the best Bid or Ask price right after matching."
- Reversal order flow cluster: "a huge group of sell orders with buy iceberg orders, along with dom pressure."

## Rules / thresholds / settings
None given — no numerical parameters or thresholds. Trade logic only: buy at the breakout point of the reversal cluster; place stop-loss "just below the first reversal cluster." Tool: mzBigTrade.

## Order-flow signature described
At a local low: a burst of large aggressive sell market orders hitting the bid, met by buy iceberg orders (hidden limit refills, fuchsia contour) and positive DOM pressure (liquidity being replenished at the best bid right after each match, shown as triangles). Price fails to progress lower despite the selling — then the entry is on breakout above the cluster.

## Relevance to our research
Directly informs our iceberg/refill detection and absorption-at-extremes work: the described signature is exactly "sell effort into no downside progress with limit refill" — the canonical absorption + iceberg defended-level pattern; positive DOM pressure maps to our defended-level refill metric.
