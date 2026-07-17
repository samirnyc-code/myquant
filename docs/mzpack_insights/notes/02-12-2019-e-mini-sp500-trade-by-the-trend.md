---
title: "02/12/2019. E-mini SP500 – Trade by The Trend"
url: https://www.mzpack.pro/02-12-2019-e-mini-sp500-trade-by-the-trend/
date: 2019-02-12
topic: trade-examples
research_relevance: medium
---
## Summary
Annotated ES long trade taken with the trend (author: Mikhail). Macro context on a 30-minute chart: uptrend, price above daily VWAP at the VAH. Order-flow trigger: a 150-lot aggressive buy initiative from inside the day's opening range followed by consecutive aggressive BUY prints; microstructural confirmation on a 10-tick chart (a 172-lot buy following a 172-lot sell, steady bid-side support). Entry from the first standard deviation of the day's range; exit signaled by volume/trade-count exhaustion plus negative COT-high readings near the 7-day high. A workspace file "MZpack – Trade by The Trend – ES" is provided.

## Key concepts & definitions
- Trend-following entry requires three layers: macro context (30M chart, price above daily VWAP at VAH), order-flow events (aggressive buy initiatives), and microstructural confirmation (10-tick chart).
- "Aggressive buy initiative": large market buy from inside the opening range (150 lot here).
- COT-high (MZpack's cumulative-delta-at-highs reading): first significant negative COT-high used as an exhaustion/exit signal.
- Bid-side support on the fine (10-tick) chart confirms buyer control after a large sell is matched by an equal-size buy (172 lots each way).

## Rules / thresholds / settings
- Entry: from the 1st standard deviation of the day's range, with trend and above daily VWAP/VAH.
- Stop loss: under the daily VWAP.
- Take profit: near the 7-day high; risk-reward 2.5:1.
- Exit signals: exhaustion of volume and trade count + first significant negative COT-high; a substantial negative COT-high = close 1/2 of position.
- Sizes cited as signals: 150-lot aggressive buy; 172-lot buy vs 172-lot sell. No indicator parameter settings given.

## Order-flow signature described
Large aggressive buy prints (150 lot) initiating from inside the opening range, followed by consecutive aggressive buys; on the 10-tick chart a large sell (172) immediately absorbed/answered by an equal-size buy (172) with steady resting support on the bid side. Exhaustion at the target shows falling volume/trade count and negative delta at new highs (negative COT-high).

## Relevance to our research
Maps to CVD divergence at extremes (negative COT-high at highs = delta divergence exit) and to defended levels (equal-size buy answering a large sell with persistent bid support). The VWAP/VAH/std-dev structure parallels our VP-touch outcome framework.
