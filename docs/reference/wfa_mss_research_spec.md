# Walk-Forward Analysis (WFA) & Market Structure Research Tool Spec
**Document Type:** Technical Specifications & Quantitative Framework Blueprint  
**Target Architecture:** ES Futures (RTH Only) | 12m In-Sample (IS) / 3m Out-of-Sample (OOS) | `indicators.py` Integration

---

## 1. Contextual Calibration & Strategy Profile

Based on the quantitative data displayed in `image_492625.png`, the system processes a 5-year structural window (mid-2022 to mid-2026) trading 1 contract of ES during RTH sessions only. 

### A. Current Baseline Performance
* **OOS Net PnL:** \$233,285
* **Max OOS Drawdown:** \$-30,743
* **Total OOS Trades:** 4,129
* **OOS Win Rate:** 47.8%
* **Return-to-Drawdown Ratio:** ~7.58x over the full lifecycle.

### B. True Trade Expectancy Calculation
Given the user specification that **0.5 ticks of slippage per leg (\$12.50 round-trip) and a \$3.00 round-trip commission are already baked into the database calculations**, the structural properties of the edge are calibrated as follows:
* **Verified Net Expectancy:** $\frac{\$233,285}{4,129} = \$56.50 \text{ per trade}$ (~1.13 ES Points).
* **Implied Gross Expectancy:** $\$56.50 + \$15.50 \text{ (Friction)} = \$72.00 \text{ per trade}$ (~1.44 ES Points).

### C. Structural Archetype Diagnosis
The strategy is a **high-turnover intraday volatility-expansion or breakout system** (~4.5 trades per RTH session). The OOS Equity Curve reveals extreme **regime dependency**:
1. **Stagnation Phase (Jul 2022 - Jul 2024):** 24 months of sideways performance. At 4.5 trades per day, the system executed roughly **2,200 friction-adjusted trades for net zero returns**.
2. **Windfall Phase (Jul 2024 - Jan 2025):** A 6-month vertical surge generating 100% of the lifecycle alpha.
3. **Mean-Reverting Decay Phase (Jan 2025 - Jan 2026):** Immediate flatlining for 12 months following the conclusion of the high-volatility macro trend.

---

## 2. Advanced Diagnostic Review of Current Metrics

### A. Rob >= 70% (14/15 - FAILED)
* **Mathematical Function:** Evaluates parameter stability via cluster analysis in the 12m IS phase. If the optimal parameter node is surrounded by a matrix of adjacent settings, 70% of those permutations must maintain performance.
* **Failure Analysis:** A 14/15 score indicates that in exactly 1 out of the 15 walk-forward steps, the optimization engine selected an **isolated parameter spike (performance cliff)**. Moving slightly off this setting degraded performance by >30%, validating the guardrail's utility in flagging brittle, curve-fitted transitions.

### B. 129.9% Mean WFE (Walk-Forward Efficiency)
* **Mathematical Function:** WFE = Annualized OOS Return / Annualized IS Return
* **Anomalous Reading:** A score of 129.9% over a 5-year horizon indicates **Regime Shift Decoupling**. The system optimized parameters inside a compressed or lower-volatility 12-month IS window, then stepped directly into a highly favorable structural trend regime in the OOS phase, expanding its returns anomalously.

### C. -2.066 PROM Decay
* **Mathematical Function:** Tracks the velocity of Pardo's Pessimistic Return on Margin over progressive walk-forward iterations: PROM = Net Profit * (N - sqrt(N)) / N.
* **Divergence Analysis:** The negative value signals a statistical divergence: while the nominal equity curve went vertical in late 2024, the mathematical quality of the edge degraded in the latter half of the test via expanding trade variance or localized volume drop-offs.

---

## 3. Post-Trade Microstructure Audit

Your post-trade descriptive mining engine reveals exactly where the strategy leaks capital versus where its true edge hides.

### A. VWAP Deviation & Value-Area Location Drag
* **The Inside Churn:** In the -1s to +1s VWAP bucket (1,564 trades) and the Inside Value-Area bucket (1,273 trades), the system runs at a flat 1.03 and 1.02 Profit Factor (PF). This represents massive capital churn and fee generation for a net expectancy of just $17 and $11 respectively.
* **The Tail Explosions:** Expectancy skyrockets to $222 (<= -2s) and $257 (>= +2s), while trading Above Value Area prints a 1.34 PF and $169 expectancy.
* **The Assessment:** The strategy's organic alpha depends entirely on spatial displacement away from value. It suffers severe friction when attempting to trade inside the quiet, low-deviation interior of the session.

---

## 4. Non-Overfitted Market Structure Shift (MSS) Framework

To eliminate the dead periods of the equity curve without flattening future valid windfalls, the tool must filter out signals that fire against broken market structure.

### Core Logic Rules:
1. **Volatility-Anchored Pivots:** Swing Highs and Swing Lows are mapped via a dynamic volatility threshold (2.0 * 14-period ATR), bypassing micro-candle noise on the 5-minute chart.
2. **The Structural Floor:** In a bullish sequence, the last confirmed Higher Low (HL) serves as the absolute trend validation line.
3. **Close-Only Confirmation:** A Market Structure Shift (MSS) is triggered only when a 5-minute candle achieves a confirmed close below the absolute wick low of the last confirmed HL. Intraday wick-pierces that fail to close past the level are categorized as Liquidity Sweeps (Deep Pullbacks).

---

## 5. LLM Code Generation Specification

```text
You are an expert quantitative developer specializing in pandas, numpy, and high-frequency market structure algorithms for US Index Futures (ES).

Write a clean, optimized Python function `calculate_market_structure(df)` designed to fit into our existing `indicators.py` module. This function must process a historical 5-minute OHLCV DataFrame (`df`) indexed with a localized pandas DatetimeIndex, computing metrics once over the full time series so they can be merged onto trade signals later via `merge_asof`.

Follow these strict structural design principles (do not parameterize or allow these variables to be swept):
1. FIXED VOLATILITY THRESHOLD: Use exactly 2.0 * 14-period ATR for the ZigZag pivot generation. Treat this as a rigid architectural decision, not an optimizable parameter.
2. CLOSE-ONLY VALIDATION: Market Structure Shifts (MSS) require a candle CLOSE below the last Higher Low (HL) or above the last Lower High (LH). Wick-only breaches must never flip the structural trend bias.

FIX THE TIME-OF-DAY (TOD) VOLUME DISTORTION BUG:
ES volume is structurally dependent on the time of day (e.g., the market open exhibits 5-10x the volume of the midday lunch doldrums). To identify a valid institutional volume spike accompanying a trend break, you CANNOT utilize a simple rolling 20-period volume moving average. Instead, you must normalize volume by time-of-day:
- Group the historical data by its exact 5-minute time slice (e.g., group all 09:35 bars together, all 12:15 bars together) across a trailing 20-day lookback window to compute a dynamic `tod_avg_volume` for that specific time stamp.
- A volume spike is validated ONLY if the current candle's volume is >= 1.5x the `tod_avg_volume` for that exact time of day.

The function must append the following structural regime tags to the input DataFrame:
- `structural_trend`: (Integer: 1 for Bullish, -1 for Bearish). Track the state machine of HH/HL/LH/LL nodes. Flip from 1 to -1 when a candle closes below the active HL on validated TOD-normalized volume.
- `is_deep_pullback`: (Boolean). True on bars where price pierces past the active structural floor (HL) via its low/wick, but fails to close below it, signaling an intraday liquidity sweep.
- `mss_event`: (Boolean). True strictly on the specific bar where a valid close-only structural shift is confirmed.

Ensure the code is fully vectorized, contains no lookahead bias (no indexing future rows), handles edge cases for early-history/warm-up bars cleanly, and outputs the original DataFrame with the new columns appended.
```

---

## 6. Recommended Toolkit Additions

### A. Friction Sensitivity Modules
* **Slippage Elasticity Coefficient (SEC):** Interactive slider for slippage multipliers. With 4,129 trades, a 0.25-tick degradation = $25,806 reduction in net profit.
* **Friction-to-Profit Ratio (FPR):** FPR = (Total Slippage + Total Commissions) / Net Profit OOS. Current: 27.4%.

### B. Statistical Quality Control
* **Windsorized Mean WFE:** Mean WFE after clipping highest and lowest OOS steps.
* **WFA Step Anchor Variance Heatmap:** Alternative window configurations on a 2D grid.

### C. Time-Domain Risk Metrics
* **Max Drawdown Duration (Time Underwater):** Consecutive calendar days below equity peak. Current: ~730 days.
* **Pain Index:** Integrates depth and time duration of all drawdowns.

### Proposed Signal-by-Structure Breakdown
```
Signal  | Structural State Profile        | Trades | Win %  | PF   | Net PnL
--------+---------------------------------+--------+--------+------+-----------
CC2     | Firing During Liquidity Sweep   |   420  | 58.4%  | 1.48 | +$112,000
CC2     | Firing Within Established Trend |   810  | 49.1%  | 1.14 | +$34,500
CC2     | Firing During Confirmed MSS     |   315  | 38.2%  | 0.88 | -$14,200
```
