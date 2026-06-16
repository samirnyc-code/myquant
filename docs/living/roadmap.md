# Roadmap
**Status:** Living — update every session  
**Last Updated:** June 16, 2026 (Session 12)  
**Rule:** This is the only source of truth for what gets built and in what order.  
**Rule:** Phases are sequential within each track. Do not start a phase until its prerequisite passes.

**Session 12 note:** Track 4 (Massive) is now primary and the only active track. Track 2 (SC/SCID) is paused. See `docs/living/handoff.md` Session 12 section for full detail.

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
| A | Data layer: scid parser, 5M bar builder, parquet storage | scid format confirmed | 🔄 In progress — parser built, cache working; bar timestamp direction (open vs close) still pending |
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
- Massive.io crosscheck: run same WFA on massive.io data, compare WFA conclusions to SC results
- Note: massive.io bar validation (Track 4) runs in parallel now and may retire the SC path if it succeeds first

**See:** `python_wfa_spec.md` for full detail on each phase.

---

## Track 4 — Massive.io Independent Validation Tab (new, active)

Completely independent from Track 2 SC gates. New Streamlit tab.

| Phase | Description | Prerequisite | Status |
|-------|-------------|-------------|--------|
| M1 | API client: `fetch_massive_trades()`, `fetch_massive_aggs()`, local parquet cache | API key | ✅ Code built; API confirmed (URL/auth/sort); futures endpoint paths pending first live call |
| M2 | NT tick-to-import converter: `scripts/fetch_for_nt.py` → `ES_MAS MM-YY.Last.txt` | API key | ✅ Code built + file format confirmed working |
| M3 | ES_MAS custom instrument + one contract month in NT; import ticks; run OHLCExporter | M2 + API key | ✅ Confirmed working end-to-end with AAPL test data (Session 11) |
| M4 | `massive.py` tab: tick-built vs agg vs NT ES_MAS vs NT native (four-way compare) | M1 + M3 | ✅ Built — all 3 comparisons wired + NT native slot added |
| M5 | Simulation in massive tab: run signal sim on App bars using MCSignals | M4 pass | Not started |
| M6 | Reversal setup: review NT CSV + strategy logic, add to massive tab | M5 + reversal data | Not started |

**See:** `bar_validation.md` Track 2 section for detailed architecture.

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
| ~~scid exact binary struct~~ | Phase A | ✅ Resolved June 9 — 56B header + 40B record, int64 µs since 1899-12-30 |
| SC session boundaries (08:30 or 09:30 CT?) | Phase A | ✅ Confirmed 08:30–15:15 CT from ESM6 tick data |
| ~~Rollover handling in scid files~~ | Phase A | ✅ Resolved June 9 — quarterly files, one per contract |
| **SCID bar timestamp (open or close?)** | Gate 1 | Unconfirmed — verify by comparing bar 1 SCID vs NT TXT |
| Regime classifier TF (5M vs higher) | Phase D | Design decision before optimizer runs |
| New signal while in trade (same direction) | Phase C | Ignore / scale in / reset — undecided |
| Max concurrent positions | Phase C | 1 / 2 / unlimited — undecided |
| Max daily loss rule | Phase C | Hard stop $ / no limit — undecided |

**See:** `open_questions.md` for full detail and options on each.

---

## Active — June 14, 2026

### Done (committed)
- [x] **SCID disk loader** — `build_scid_quarter_map()`, `load_scid_ticks_chunked()`, quarter selector UI; 12 contracts on disk
- [x] **Parquet cache** — `save/load/clear_scid_cache()`; auto-loads on app restart; snappy-compressed ticks + meta.json
- [x] **Source selector before tabs** — fix for render-order bug (Tab1 was reading stale `bar_source`)
- [x] **Bar viewer upload-only** — no disk fallbacks; no 2026 data unless explicitly loaded
- [x] **OHLC timestamp auto-detect** — median-hour heuristic (>14 = Berlin, ≤14 = CT); fixes missing 15:15 bar
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
- [x] **2-leg scale-in simulation engine** — `simulate_trades(multileg=True)`, `compute_summary(is_multileg=True)`, PB/T1/T2 chart annotations
- [x] **Scale-In Sweep (PB × T1 × T2)** — 432-combo grid, heatmap slices, ranked table
- [x] **PDF export** — Bar Analysis + Portfolio tabs; `matchMedia('print')` + `Plotly.relayout()` for chart resize; counter forces re-render on every click
- [x] **Portfolio tab** (`portfolio.py`) — per-setup 2-leg sim, equity curves, DD chart, breakdown table, T1×PB×T2 sweep, save/compare runs, PDF export, Save as Defaults

### Near-term backlog (Session 12, Massive track — top priority)
- [ ] **Migrate Bar Analysis filters to the shared panel** — `ba_`-prefixed filter widgets in `bar_analysis.py` still independent from `validation.get_filters("shared")`; should read from the same Data-tab panel as Massive's comparison
- [ ] **Optimize by calendar month, not by contract** — user request, not yet designed: Bar Analysis needs to slice/optimize across arbitrary calendar-month ranges independent of which contract was front-month
- [ ] **Re-download ~50 missing trading days** in `data/flatfiles_cache/` (2021–2022 heavy) — listed in handoff.md Session 12 section
- [ ] Root-cause the tick-cache validation discrepancy (98.6%/1,587 vs 100%/243 extra bars between the two measurement methods)
- [ ] Live-test RevFTSignals end-to-end with a real second signal file
- [ ] Live-test the alt-path mismatch table with a real divergent trade (none seen yet in spot checks)
- [ ] NT `OHLCExporter` buffer-loss fix (flush-to-disk periodically) — drafted, reverted per user instruction; revisit only if asked
- [ ] **"Clear all cached data" needs two confirmation popups** — explain what it does (deletes Parquet cache files, not just session state) and what's needed to get the data back (rebuild via Massive tab / re-upload). Currently a single button, no confirmation at all.

### Near-term backlog (Track 2 — SC/SCID, paused)
- [ ] **Verify SCID bar timestamp** — upload Q1/2024 SCID + matching NT TXT, compare bar 1 open time; apply -5min fix if SCID uses close time (see Q14 in open_questions.md)
- [ ] **End-to-end Bar Validation** — test with Q1/2024 SCID + matching NT TXT; confirm SC vs NT comparison produces valid diff stats
- [ ] **Verify PDF equity chart resize** — `Plotly.relayout()` from iframe may be blocked by browser; test in running app
- [ ] **Verify 2-leg P&L math** — spot-check blended entry, T2 price, per-leg PnL against manual calc
- [ ] 3-Leg column: build after 2-leg math verified
- [ ] Add ESH21 2021 tick data file when clean data available
- [ ] Add ESM1 2021 and ESH2/ESM2 2022 contracts to registry when files ready
- [ ] Share app + data files with Thomas: upload both data files to Google Drive, run ngrok
- [ ] Add volume subplot to Bar Viewer candlestick chart
- [ ] **Track 4 — first live ES futures fetch** — API key in hand; confirm futures endpoint paths, fetch ESM6 ticks, run `fetch_for_nt.py`, import into NT, run OHLCExporter, validate Comparisons 1 & 2 in app
- [ ] **Reversal setup** — review NT signal CSV + strategy logic before any code (arriving next week)

---

## Bar Validation App — Backlog

| Feature | Notes |
|---------|-------|
| **AI commentary (Claude API)** | Call Anthropic API to generate plain-English interpretation based on comparison stats. Cache result. Requires API key in env. ~2s latency on first load. |
