---
title: Backtesting MZpack Strategies: Two Paths to Validating Your Edge
url: https://www.mzpack.pro/backtesting-mzpack-strategies-two-paths-to-validating-your-edge/
date: 2026-07-15
topic: strategies-backtesting
research_relevance: medium
---
## Summary
Describes two workflows for backtesting MZpack order-flow strategies in NinjaTrader. Path 1 uses Strategy Analyzer with Tick Replay (reconstructed historical trade + best bid/ask), suitable for footprints, delta, volume profiles, and big trades. Path 2 uses Market Replay (Playback) recordings, required for anything needing full order-book depth (iceberg detection, DOM pressure/support, mzMarketDepth) because NinjaTrader does not store historical depth. Also covers configuration pitfalls that produce empty footprints or corrupted data.

## Key concepts & definitions
- Backtesting: validating strategy logic against historical data; MZpack strategies run "tick-by-tick basis using NinjaTrader's tick stream" — tick data required for meaningful results.
- Tick Replay: reconstructs historical trade and best bid/ask data so order-flow strategies can run in Strategy Analyzer.
- Market Replay (Playback): recording/replay of live sessions; the only path when full DOM depth is needed.
- DOM-dependent features (icebergs Hard/Soft, DOM pressure/support) cannot be backtested from plain historical tick data.

## Rules / thresholds / settings
- Enable Tick Replay globally: Tools – Options – Market Data – Show Tick Replay.
- Activate the "Backtesting" parameter (on/off toggle) in strategy settings.
- Calculation mode: BidAsk for futures; UpDownTick for forex/crypto/stocks.
- Enable "Reconstruct tape: timestamps only" under Orderflow settings for consistent big-trade matching between historical and live.
- Start with short date ranges (Tick Replay is resource-intensive).
- No numerical thresholds given.

## Order-flow signature described
None (methodology article). Pitfall signatures: empty footprints or missing trades mean Tick Replay is disabled or tick data unavailable; corrupted data files come from cloud-syncing NinjaTrader folders — use local storage.

## Relevance to our research
General background, but validates our approach: our free footprint reconstruction from NT8 ticks corresponds to their Tick Replay path, and confirms DOM-based signatures (iceberg Hard/Soft, DOM pressure) are fundamentally unavailable from historical tick data — only tape-based iceberg detection is backtestable.
