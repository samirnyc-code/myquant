# Roadmap
**Status:** Living — update every session  
**Last Updated:** June 7, 2026  
**Rule:** This is the only source of truth for what gets built and in what order.  
**Rule:** Phases are sequential within each track. Do not start a phase until its prerequisite passes.

---

## Track 1 — NT8 / Sheets (current system, maintenance mode)

These phases are complete. New work in this track only if explicitly scoped.

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Infrastructure, versioning, RAW_IMPORT, MASTER, COLUMN_MAP | ✅ Complete |
| 1 | Analysis tab v1 (BTC breakout setup, 3CC) | ✅ Complete |
| 2 | Saved Runs comparison tab | ✅ Complete |
| 3 | PB Trade Simulator (NT8) | ✅ Complete (SIM_v3.3) |
| 4 | Analysis tab v2 (PB setups, filter optimizer) | ✅ Complete |
| 5 | BTC/STC setup | ✅ Complete |
| 6 | MCChartMarker indicator | ✅ Complete (V1.0) |

**Deferred (post-Python):**
- Vertical legend panel in MCChartMarker
- Multi-year MASTER selector
- TOD 13-bucket expansion
- Stress test tab
- Visuals tab (equity curve, drawdown)
- Rocket Trade setup

---

## Track 2 — Python WFA Engine (primary focus)

All phases are sequential. No phase starts until its prerequisite gate passes.

| Phase | Description | Prerequisite | Status |
|-------|-------------|-------------|--------|
| A | Data layer: scid parser, 5M bar builder, parquet storage | scid format confirmed | Not started |
| — | Gate 1: Python bars vs SC export | Phase A | Blocking |
| — | Gate 2: Sierra bars vs NT8/Rithmic bars (1yr on disk) | Gate 1 | Blocking |
| B | Signal detector: port MC logic from MCSimulatorV5_5.cs | Gates 1+2 | Not started |
| — | Signal gate: match C# output on 4-week test period | Phase B | Blocking |
| C | Strategy simulator: signals + params → trade log (SIM_v3.3 schema) | Signal gate | Not started |
| D | Optimizer: grid search, PROM objective, parameter surface | Phase C | Not started |
| E | WFA engine: rolling windows, WFE, OOS equity curve, eval profile | Phase D | Not started |
| F | Window stability scanner: IS/OOS size grid, std dev WFE matrix | Phase E | Not started |
| G | Streamlit UI: all results, interactive, exportable | Phase E | Not started |

**After Phase E (optional):**
- Massive.io crosscheck: purchase, parse, run same WFA, compare conclusions

**See:** `python_wfa_spec.md` for full detail on each phase.

---

## Track 3 — Validation Framework (runs alongside Track 2)

These are not build phases — they are analytical obligations that run as Track 2 produces data.

| Layer | Description | When |
|-------|-------------|------|
| 1 | Basic edge: expectancy, profit factor, sample size, binomial test | After Phase C |
| 2 | Consistency: year-by-year, SQN, Z-score of runs | After Phase C |
| 3 | Walk-forward: WFE, % profitable OOS windows, equity curve | After Phase E |
| 4 | Monte Carlo: trade sequence shuffle, bootstrap sampling | After Phase E |
| 5 | Slippage/commission sensitivity: base + stress cases | After Phase C |
| 6 | Lopez de Prado: Deflated Sharpe, multiple testing adjustment | After Phase E |

**See:** `strategy_validation_framework.md` for full protocol.

---

## Open Questions (blocking design decisions)

| Question | Blocks | Status |
|----------|--------|--------|
| scid exact binary struct | Phase A | Confirm from ACSIL docs |
| SC session boundaries (08:30 or 09:30 CT?) | Phase A | ✅ Confirmed 08:30–15:15 CT from ESM6 tick data |
| Rollover handling in scid files | Phase A | Continuous or quarterly? |
| Regime classifier TF (5M vs higher) | Phase D | Design decision before optimizer runs |
| New signal while in trade (same direction) | Phase C | Ignore / scale in / reset — undecided |
| Max concurrent positions | Phase C | 1 / 2 / unlimited — undecided |
| Max daily loss rule | Phase C | Hard stop $ / no limit — undecided |

**See:** `open_questions.md` for full detail and options on each.

---

## Active — June 7, 2026

### Done (committed)
- [x] Bar Validation module built and working
- [x] NYSE holiday exclusion via exchange-calendars
- [x] Economic event filter: FOMC/NFP/CPI — Skip full day or Window ±N min
- [x] FRED API wired; FOMC 2015–2026 hardcoded and confirmed
- [x] All filters in single ⚙️ Filters expander with Save as Default
- [x] Commentary toggle (show/hide all explanatory text)
- [x] Session Boundaries: first N bars + last N min sliders
- [x] Day of Week filter (Mon–Fri include checkboxes)
- [x] Charts always show full dataset; excluded zones shaded with grey overlay
- [x] Bar Viewer: ‹/› prev/next navigation, bar numbers on candlestick, collapsible bar table
- [x] Summary strip: Trading Days, Max Drawdown added
- [x] **Bar Analysis tab** — full signal simulation engine, per-day charts, signal table, optimal R sweep
- [x] **Contract selector** — multi-contract registry in data_loader.py; selector auto-hides missing files
- [x] Bar numbers derived from time (not index) — correct on incomplete days
- [x] **File upload** — 📁 Upload Data expander; SC tick → 5-min bars + ticks; OHLC bar_export; feeds all three tabs
- [x] Setup Analysis table (per-setup CC3/CC4 breakdown, dynamic columns)
- [x] Monthly Breakdown: equity curve + drawdown + OLS trend + setup% chart
- [x] Winner/Loser filter on daily chart
- [x] Optimal R sweep: 1D and T1×T2 2D heatmap
- [x] Stop multiplier sweep (0.25×–2.00×)

### Coded, NOT YET TESTED — do not commit until tested in running app
- [ ] **2-leg simulation engine** — `_simulate_one_multileg`, `_simulate_one_bars_multileg`, `simulate_trades` multileg path, `compute_summary` multileg, `_EMPTY_TRADE` multileg fields
- [ ] **Trade type column layout** — replaces Instrument & Sizing / Execution / 2-Leg sections; Instrument shared above; `st.radio("ba_trade_mode")`; 3 columns (Single Leg / 2-Leg / 3-Leg placeholder); `disabled=True` on inactive columns; derive block outputs plain-named vars
- [ ] **T1 and T2 chart lines** — T1 dotted teal + "T1 X.XXR" annotation; T2 dashed teal + "T2 X.XXR" annotation; single-leg shows bold R label only

### Near-term backlog
- [ ] 3-Leg column: build after 2-leg is tested and committed
- [ ] Add ESH21 2021 tick data file when clean data available
- [ ] Add ESM1 2021 and ESH2/ESM2 2022 contracts to registry when files ready
- [ ] Share app + data files with Thomas: upload both data files to Google Drive, run ngrok
- [ ] Add volume subplot to Bar Viewer candlestick chart

---

## Bar Validation App — Backlog

| Feature | Notes |
|---------|-------|
| **AI commentary (Claude API)** | Call Anthropic API to generate plain-English interpretation based on comparison stats. Cache result. Requires API key in env. ~2s latency on first load. |
