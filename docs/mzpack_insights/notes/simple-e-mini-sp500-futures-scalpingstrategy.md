---
title: Simple E-mini SP500 futures scalping strategy
url: https://www.mzpack.pro/simple-e-mini-sp500-futures-scalpingstrategy/
date: 2018-02-17
topic: strategies-backtesting
research_relevance: high
---
## Summary
The most complete strategy article in the set: a two-level ES scalping framework on NinjaTrader 8 combining dynamic volume-based day levels with microstructure confirmation. Level 1 (5-minute chart) registers signals from touches/tests/retests of dynamic day levels (POC, VAL/VAH, VWAP and deviations) and market-limit order executions. Level 2 (20-tick chart) requires microstructure confirmation: well-defined S/R, DOM pressure "clusters," and meaningful-size iceberg orders. Trade management focuses on minimizing average MAE via quick breakeven stops, reduced targets, and market exits on opposite signals or deteriorating microstructure. Suggested improvements: liquidity-migration analysis, trade-density filtering (mzFootprint TradesNumber), and full automation.

## Key concepts & definitions
- Dynamic volumes-based day levels: dynamic POC, VAL/VAH, VWAP and its deviations, recalculated intraday.
- Level-1 signals: (a) touch/test/re-test of a dynamic day level; (b) market-limit order executions at the level.
- Level-2 confirmations (20-tick chart): well-defined support/resistance, DOM pressure clusters, iceberg orders of meaningful size.
- MAE minimization: reduce average Maximum Adverse Excursion as the core risk metric.
- Trade density: mzFootprint TradesNumber type (trades-per-bar/level) proposed as an entry/exit filter.

## Rules / thresholds / settings
- Timeframes: 5-minute bars (context) + 20-tick bars (entry/microstructure).
- Exits: market exit on opposite signals or "signs of undesired microstructural activity"; decrease profit targets to cut losses; move stop to breakeven quickly.
- No numeric values for level distances, iceberg size, or DOM pressure given.

## Order-flow signature described
At a dynamic day level: limit executions absorbing market orders, DOM pressure clustering on the defending side, and icebergs (refilling hidden size) at the level — the microstructure picture that validates the touch as defended before entry.

## Relevance to our research
Directly mirrors our program: VP-level (POC/VAH/VAL/VWAP) touch outcomes gated by iceberg/refill and DOM-pressure confirmation, with MAE as the evaluation metric — a ready-made design for our level-touch backtest harness.
