# Technical Specification: Market Structure Shift (MSS) Engine
**Document Type:** Software Architecture & Prompt Blueprint for LLM Code Generation  
**Target Timeframe:** 5-Minute Intraday Charts (ES Futures / RTH Only)  
**Primary Objective:** Programmatically map structural pivots (HH/HL/LH/LL), track Market Structure Shifts (MSS), and algorithmically isolate deep pullbacks from true trend breaks without curve-fitting.

---

## 1. Algorithmic Framework Rules

To eliminate noise on a 5-minute chart, market structure must be mapped using a volatility-adjusted, rule-based approach rather than simple candle-to-candle highs and lows.

### A. Core Architectural Definitions
1. **Swing High / Swing Low Nodes:** Established only when a spatial or volatility threshold is met, preventing micro-noise from triggering false trend breaks.
2. **The Structural Floor:** In a bullish trend, the last confirmed **Higher Low (HL)** is marked as the systemic floor.
3. **Market Structure Shift (MSS):** Triggered **only** when a 5-minute candle achieves a **confirmed close** below the absolute wick low of the last confirmed Higher Low ($HL$). Intraday wicks that pierce the level but snap back do *not* constitute a trend break.

---

## 2. LLM Code Generation Instructions (System Prompt)

Copy and paste the block below directly into an LLM to generate the python/pandas code required to integrate this module into your backtesting workbench.

```text
You are an expert quantitative developer specializing in pandas and high-frequency intraday market structure algorithms. 

Write a clean, optimized Python function `calculate_market_structure(df, atr_multiplier=2.0)` to parse a 5-minute OHLCV DataFrame (`df`) and append market structure metadata to each row. 

Follow these strict algorithmic steps:

### Step 1: Volatility-Adjusted Pivot Detection
1. Calculate a standard 14-period Average True Range (ATR) on the 5-minute chart.
2. Implement a modified ZigZag algorithm where a Swing Low or Swing High node is anchored ONLY when price reverses by more than `(atr_multiplier * ATR)` from the previous peak/trough.
3. Track and classify these anchored nodes sequentially into a state machine: Higher High (HH), Higher Low (HL), Lower High (LH), and Lower Low (LL).

### Step 2: Track Active Structural Boundaries
1. For every row, log the exact price value of the `last_confirmed_HL` (if the macro state is bullish) or `last_confirmed_LH` (if the macro state is bearish).
2. Maintain a state variable `structure_trend` which defaults to `1` (Bullish) when breaking HHs, and switches to `-1` (Bearish) upon an MSS event.

### Step 3: Identify Market Structure Shifts (MSS) vs. Deep Pullbacks
Apply a multi-variable logic gate on every bar where price crosses the `last_confirmed_HL`:
1. **Condition - True MSS (Trend Break):** 
   - A 5-minute candle must CLOSE below the `last_confirmed_HL`.
   - The volume of that breaking candle must be >= 1.5x the rolling 20-period volume moving average (Volume Spike Validation).
   - If both are true, set `mss_triggered = True` and flip `structure_trend = -1`.
2. **Condition - Deep Pullback (Liquidity Sweep):**
   - If price pierces below the `last_confirmed_HL` via its low/wick, but the candle CLOSE remains above the `last_confirmed_HL`, or if the close is below but on low volume (< 1.5x average), classify this bar as `deep_pullback = True`.

### Output Requirements:
The function must return the original DataFrame with the following columns appended seamlessly:
- `structural_trend` (1 for Bullish, -1 for Bearish)
- `active_floor` (Float: price of active HL tracking)
- `is_deep_pullback` (Boolean)
- `mss_event` (Boolean: True only on the exact candle a valid trend break is confirmed)

Ensure the code avoids lookahead bias (no referencing future rows) and is optimized for speed using vectorization where possible or tight, efficient looping over the pivot states.
```
