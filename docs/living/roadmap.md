# Roadmap
**Status:** Living — update every session  
**Last Updated:** June 3, 2026  
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

## Active — June 4, 2026

- [ ] Run the full app cold-start (first cache build) end to end and confirm all 56 trading days load without errors
- [ ] Share the app with Thomas via ngrok — walk him through the date selector and chart
- [ ] Add a volume subplot below the candlestick (secondary y-axis or separate panel)
- [ ] Investigate whether more historical tick data exists (user expected 510 calendar days — only 65 days are in the current file)

---

## Bar Validation App — Backlog

These are scoped features for the validation module, in rough priority order.

| Feature | Notes |
|---------|-------|
| **Holiday exclusion** | Extend `KNOWN_HOLIDAYS` dict in `validation.py`. Add a toggle in the UI: "Exclude known holidays from mismatch count." 5/25 (Memorial Day + Whit Monday) already flagged. Need a full US market holiday calendar for the data range. |
| **Economic calendar overlay** | Flag FOMC, NFP, CPI, PPI dates on the By Date chart and Time-of-Day chart. Hypothesis: mismatch rate spikes around high-impact news because fast price movement amplifies feed-latency bar boundary differences. Several free API options: FRED (Federal Reserve, free), Econoday, Trading Economics. Could also hardcode a static calendar for the Apr–Jun 2026 window as a first pass. |
| **AI commentary (Claude API)** | Call the Anthropic API to generate a plain-English interpretation paragraph based on the comparison stats. Cache the result. Requires API key in environment. ~2s latency on first load. |
