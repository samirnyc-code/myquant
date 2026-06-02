# Python WFA Research Tool — Specification
**Status:** Architecture — Living  
**Last Updated:** June 2, 2026  
**Project:** myquant  
**Prerequisite:** Bar validation gates 1 and 2 must pass before Phase C begins  
**Framework:** Pardo — *The Evaluation and Optimization of Trading Strategies* (2nd ed.)  
**Also see:** `strategy_validation_framework.md` for full testing protocol

---

## Purpose

Python-based walk-forward analysis engine for MC signal setups on ES 5M RTH. Replaces the NT8 tick engine (too slow for multi-year runs) and Google Apps Script (6-min timeout, no WFA). Validates 5 independent setups (1cc–5cc) using the Pardo framework.

**Trading platform remains NT8/Rithmic.** Sierra Charts is the data source for research only.

---

## Non-Negotiables (Pardo)

Violating any one of these invalidates results:

1. Strategy logic is fixed before any optimization runs. Optimizer finds parameter values, not logic.
2. Scan ranges defined before optimization runs. Not widened because results were disappointing.
3. Objective function chosen before optimization runs. Not swapped after seeing outputs.
4. OOS windows are never used to make design decisions. Using OOS results to change anything converts those windows to IS data.
5. Regime classifier rules fixed before optimization runs.
6. Reoptimization cadence in live use equals the OOS window length from WFA. Not arbitrary. Not triggered by drawdown.

---

## Data Stack

**Primary:** Sierra Charts scid files (via Delani) — see `data_sources.md`  
**Secondary crosscheck:** Massive.io (optional, purchase deferred) — see `data_sources.md`  
**Live trading:** NT8 / Rithmic — unchanged  
**Bar validation:** Must pass both gates in `bar_validation.md` before Phase C

---

## Architecture

```
Sierra Charts scid files
        |
        v
Phase A: Data Layer
  scid parser → 5M RTH OHLCV bars → validated_bars.parquet
        |
        v  [Gate 1 + Gate 2 must pass — see bar_validation.md]
        |
        v
Phase B: Signal Detector
  Port MC logic from MCSimulatorV5_5.cs → signals.parquet
        |
        v  [Signal validation gate must pass]
        |
        v
Phase C: Strategy Simulator
  signals + parameters → trade log matching SIM_v3.3 schema
        |
        v
Phase D: Optimizer
  Grid search → best parameter set per IS window
        |
        v
Phase E: WFA Engine
  Rolling IS/OOS windows → WFE → OOS equity curve
        |
        v
Phase F: Window Stability Scanner
  Grid of IS/OOS size combinations → empirically justified window sizing
        |
        v
Phase G: Streamlit UI
  All results, interactive, exportable
```

---

## Phase Specs

### Phase A — Data Layer
**Prerequisite:** scid format confirmed from Sierra Charts ACSIL docs

- Parse Sierra Charts scid binary files
- Build 5M RTH OHLCV bars (session-aware, rollover-aware)
- Store as parquet
- Cross-validate: see `bar_validation.md` Gates 1 and 2

**Also build:** NT8 tick parser for Gate 2 bar comparison (1 year of Rithmic tick data on disk)

### Phase B — Signal Detector
**Prerequisite:** Phase A + both validation gates passed

- Port MC signal logic exactly from `MCSimulatorV5_5.cs` — no interpretation
- Output schema: `date, time, bar_index, direction, cc_count, mc_high, mc_low, mc_bar_count, signal_bar_close`
- Validation gate: run on 4-week test period shared with NT8. Signal count, dates, times, MC high/low must match C# exactly.
- **Blocking condition:** WFA engine will not run until this gate is passed and logged.

### Phase C — Strategy Simulator
**Prerequisite:** Phase B validation gate passed

- Given signals + parameters, generate trade log
- Match SIM_v3.3 CSV schema exactly
- Slippage: 1 tick entry + 1 tick exit per leg (conservative)
- Commission: configurable (default $4.50/side)
- Multi-leg positions: P1–P5 per signal

### Phase D — Optimizer
**Prerequisite:** Phase C complete

- Grid search (brute force first, genetic search later if needed)
- Objective function: PROM (Pessimistic Return on Margin) default. Sharpe, net profit available.
- Performance floors: min 30 trades per IS window, min net P&L configurable, max drawdown configurable
- Store full parameter surface per IS window — enables plateau analysis
- Plateau detection: flag sets where all neighbors within ±1 step also meet performance floors

### Phase E — WFA Engine
**Prerequisite:** Phase D complete

- Rolling windows (not anchored)
- Step size = OOS window size
- WFE = (annualized OOS net P&L) / (annualized IS net P&L) × 100%
- Minimum 10 walk-forwards (Pardo minimum). Target 20–40.
- Contamination guard: OOS results are write-once. Any parameter change after reading OOS requires full re-run with new run ID.
- Output: evaluation profile (mean ± std dev of all metrics across OOS windows)

**WFE thresholds (Pardo):**

| WFE | Interpretation |
|-----|---------------|
| < 25% | Suspect — unsound or overfit |
| 50–60% | Robust — minimum acceptable |
| > 100% | Valid — OOS can exceed IS |

**OOS profitable windows:** ≥ 60% minimum

### Phase F — Window Stability Scanner
**Prerequisite:** Phase E complete

- IS candidates: 6, 9, 12, 18 months
- OOS candidates: 25%, 30%, 35% of each IS window
- 4 × 3 = 12 configurations per setup
- For each: mean WFE, std dev WFE, % profitable OOS windows, total OOS trade count
- Primary sort: std dev WFE ascending (most consistent = empirically justified)
- Secondary sort: mean WFE descending
- **This is the empirical justification for window sizing per Pardo — not opinion, not convention**

### Phase G — Streamlit UI
**Prerequisite:** Phase E complete (F can run in parallel)

- Setup selector (1cc–5cc, long/short/both)
- WFA configuration panel
- Window stability matrix heatmap
- OOS equity curve + drawdown curve
- WFE per window bar chart
- Evaluation profile panel (mean ± std dev per metric)
- Parameter surface viewer
- Export to CSV

---

## Pardo Validation Checklist (run before any WFA result is published)

- [ ] Signal detector output matches C# reference on shared test period
- [ ] Strategy logic unchanged since scan ranges were defined
- [ ] Scan ranges defined before first optimization run
- [ ] Objective function defined before first optimization run
- [ ] IS window covers all 4 market types across full WFA history
- [ ] Each IS window generates ≥ 30 trades
- [ ] ≥ 10 walk-forwards completed
- [ ] OOS windows never used to make design decisions
- [ ] WFE ≥ 50% (minimum for robust strategy)
- [ ] ≥ 60% of OOS windows profitable
- [ ] Degrees of freedom consumed documented
- [ ] Slippage: 1 tick entry + 1 tick exit minimum

---

## Technology Stack

| Component | Library |
|-----------|---------|
| Data manipulation | pandas, numpy |
| Bar construction | pandas resample with custom session boundaries |
| Storage | parquet via pyarrow |
| Grid search | itertools.product + pandas vectorized scoring |
| UI | Streamlit |
| Charts | Plotly |
| Environment | Python 3.11+, Claude Code for build sessions |

---

## Massive.io Crosscheck (optional — after Phase E)

After WFA produces results on Sierra data, purchase Massive.io and run the same WFA on Massive bars. Compare:
- Signal agreement rate
- WFE per window — do conclusions hold?
- % profitable OOS windows

If conclusions hold on both providers, confidence in the strategy is materially higher. If they diverge, investigate whether the divergence is in bar construction, rollover handling, or a genuine data dependency.

---

## Open Questions

| Question | Status |
|----------|--------|
| scid exact binary struct | Confirm from ACSIL docs before Phase A |
| SC rollover handling | Continuous or quarterly? Gap adjustment method? |
| RTH session boundaries | 08:30 or 09:30 CT? Confirm with SC session template |
| Regime classifier TF | 5M native or higher TF (30M, 60M)? Design decision before Phase D |
| Genetic search | Needed or grid search sufficient? Revisit after Phase D |
| Massive.io purchase | Deferred until Phase E complete |
