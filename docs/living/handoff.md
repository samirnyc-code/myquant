# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 6, 2026  
**Current Versions:** SIM_v3.3 / GS_v4.5 / SHEET_v3.3  
**Rule:** Read this file first every session. It is the only source of truth for current state.

---

## What Is Active Right Now

The NT8 simulator and Sheets analysis pipeline are complete and working. All new development is Python-first. No new Sheets or NT8 features are being built unless explicitly scoped.

The Python WFA engine is the primary focus. It has not started. The prerequisite sequence is:

```
Sierra Charts scid data confirmed
        |
        v
Phase A: scid parser + 5M bar builder
        |
        v
Gate 1: Python bars vs SC export (bar_validation.md)
        |
        v
Gate 2: Sierra bars vs NT8/Rithmic bars (1 year on disk)
        |
        v
Phase B: Signal detector — port from MCSimulatorV5_5.cs
        |
        v
Signal validation gate: match C# output on 4-week test period
        |
        v
Phase C onward: simulator, optimizer, WFA engine
```

Nothing in Phase C or beyond starts until all gates above pass.

---

## Streamlit App (June 6, 2026)

Three-tab app with contract selector and file upload. All tabs share cached data loaded by `data_loader.py`.

| File | Purpose |
|------|---------|
| `app.py` | Entry point, contract selector, tab layout, Reload button; Upload Data expander lives inside Bar Analysis tab |
| `data_loader.py` | Contract registry; parameterised loaders for SC bars, SC ticks, NT bars; upload parsers; `bar_num_from_dt()` |
| `validation.py` | Bar Validation tab — SC vs NT comparison |
| `bar_analysis.py` | Bar Analysis tab — signal sim, charts, monthly breakdown, R sweep |
| `economic_calendar.py` | FOMC hardcoded 2015–2026; NFP/CPI via FRED API |
| `.streamlit/config.toml` | `maxUploadSize = 2000` (MB) |
| `filter_defaults.json` | Bar Validation persisted defaults — not in git |
| `ba_filter_defaults.json` | Bar Analysis persisted defaults — not in git |

**Contract registry (`data_loader.py` → `CONTRACTS` dict):**
- `"ESM6 — 2026"` → `ESM6.CME_BarData.txt` / `NinjaScript Output 03_06_2026 23_08.txt`
- `"ESH21 — 2021"` → `ESH21-CME.txt` / `NinjaScript Output 2021.txt` *(file not yet on disk)*
- Add new contracts by adding an entry to `CONTRACTS` — no other code changes needed
- Contract selector only shows contracts whose SC file exists on disk

**economic_calendar.py — current state:**
- FOMC dates hardcoded 2015–2026; 2026 confirmed from federalreserve.gov on 2026-06-04
- NFP (release_id=50) and CPI (release_id=10) fetched from FRED API; requires `FRED_API_KEY` in `.streamlit/secrets.toml`
- `get_economic_events(event_types: tuple, start, end)` returns DataFrame with DateTime (CT, tz-naive), EventType, Color

**Layout (tab-first design — as of this session):**
- Tabs (`📊 Bar Viewer | 🔍 Bar Validation | 📈 Bar Analysis`) are the first element after the page header
- All upload UI lives inside the Bar Analysis tab: `📁 Upload Data` expander (3 cols: Tick | OHLC | MC Signals), then `📡 Bar data source` expander (only shown when multiple sources available)
- Session state carries uploaded data across tabs; Bar Viewer and Bar Validation read from session state silently
- Reload button clears all upload state including `ba_signals`

**Upload Data expander (inside Bar Analysis tab):**
- Col 1: SC tick data (.txt) → `uploaded_sc_bars` + `uploaded_sc_ticks`
- Col 2: OHLC bar_export (.txt) → `uploaded_ohlc_bars`
- Col 3: MC Signals (.txt) → `ba_signals` — parsed by `bar_analysis.parse_signals()`
- Cache key = `name_size` — re-parses only when a different file is uploaded

**Bar data source selector:**
- Shown only when multiple bar sources are available (upload + disk)
- Options: SC Ticks (upload) | OHLC (upload) | SC Ticks (disk)
- Choice stored in `st.session_state["bar_source"]`; both Bar Viewer and Bar Analysis respect it

**Bar-level simulation (no tick data):**
- Falls back to `_simulate_one_bars()` when no tick data is available
- Uses OHLC H/L for fill detection; conservative (stop before target when both reachable in same bar)
- `>=` comparison on bar DateTime so fill is correctly on the NEXT bar after signal (not one bar late)

**Tab 1 — Bar Viewer**
- ‹/› prev/next buttons + date dropdown → 6 summary metrics → candlestick → collapsible 5-min bar table
- Bar numbers derived from `bar_num_from_dt(DateTime)` — correct even when bars are missing
- Incomplete days (< 81 bars) show a warning banner with first-bar time
- Uses `bar_source` session state to select between SC disk / uploaded bars

**Tab 2 — Bar Validation**
- Compares SC-built bars vs NT pre-built bars for selected contract
- NT timestamps converted Berlin CEST → CT, close→open (−7h −5min)
- Filters: NYSE holidays, DOW, session boundaries, economic events, Save as Default
- `build_comparison()` in `validation.py` now strips extra columns before join (fixes NullVol/Date overlap)

**Tab 3 — Bar Analysis — section layout (all collapsible expanders):**
1. `📁 Upload Data` — tick / OHLC / signals upload
2. `📡 Bar data source` — only when choice exists
3. Filters + trading params (date range, DOW, econ events, CC3/CC4, instrument, slippage, target R, commission)
4. `📋 Summary` — 4 rows × 6 metrics incl. Max Drawdown + Trading Days
5. `📅 Monthly Breakdown` — monthly table (dynamic setup% columns) + equity/DD chart + setup% vs Net PnL chart
6. `📊 Setup Analysis` — per-setup (CC3/CC4/…) breakdown table; add setups appear automatically
7. `---` divider then unfilled/filtered signal expanders
8. Winner/Loser filter radio (outside Daily Chart expander)
9. `📈 Daily Chart` — nav controls, date picker, bar chart + signal markers
10. Signal Table (day) expander + All Signals expander
11. Optimal R sweep expander
12. `🔍 Bar Data Mismatch Analysis` — collapsed by default

**Simulation engine (`bar_analysis.py`):**
- `parse_signals(raw)` — parses MC signal export; called from `app.py` now (not inside `show_bar_analysis`)
- `_simulate_one()` — tick-level single-leg sim; stop-order fill, MAE/MFE, slippage tracking
- `_simulate_one_bars()` — bar-level fallback; `>=` on DateTime to get correct next bar
- `simulate_trades()` — dispatches to tick or bar sim; supports `bars_by_date` param for fallback
- `compute_summary()` — returns dict with n_trades, win_pct, PF, exp, MAE/MFE R, max_dd, trading_days
- `_show_monthly_breakdown()` — equity curve + OLS trend line + DD bars + setup% chart (dynamic signal types)
- `_show_mismatch_analysis()` — collapsed by default

**Hover behavior (Daily Chart):**
- Signal/entry/exit bars use `fill="toself"` + `hoveron="fills+points"` + center marker for reliable hover
- `<extra></extra>` removes trace-name badge; `font_size=15` in hoverlabel
- `hoverinfo="skip"` on visual markers (circle-open, x)

**Data files (not in git — keep in `data/raw/`):**
- `ESM6.CME_BarData.txt` (~3GB SC ticks, 2026)
- `NinjaScript Output 03_06_2026 23_08.txt` (NT 5M bars, 2026)
- `NinjaScript Output 2021.txt` (NT 5M bars, 2021 — needed for ESH21 contract)
- `NinjaScript Signals 2021.txt` (MC signals 2021 — upload via Bar Analysis Upload Data panel)

**Run:** `pkill -f "streamlit run"` then `.venv/bin/streamlit run app.py`

---

## Current Versions

| Component | Version | Notes |
|-----------|---------|-------|
| NT8 Simulator | SIM_v3.3 | Multi-leg, OnBarClose, PB66 + EB stop |
| Apps Script | GS_v4.5 | ETH bucket, pre-filters, export fixes |
| Google Sheet | SHEET_v3.3 | |

---

## Data Status

| Source | Status | Notes |
|--------|--------|-------|
| Sierra Charts scid (Delani) | Available | Primary research data. scid parser not yet built. |
| NT8/Rithmic tick data | Available | 1 year on disk. Used for Gate 2 bar validation. |
| ESM6 CME tick data (.txt) | Available | 56 trading days (2026-03-31 to 2026-06-03). Used by Streamlit viewer. Not in git. Share via Google Drive. |
| NT 5M bar data (.txt) | Available | April 1 – June 3 2026. Used by Bar Validation tab. Not in git. Share via Google Drive. |
| Massive.io | Not purchased | Optional crosscheck. Deferred until Phase E complete. |

See `data_sources.md` for full detail.

---

## Known Issues (NT8/Sheets — not blocking Python work)

| Issue | File | Fix |
|-------|------|-----|
| `saveRun` TOD labels wrong | GS_v4.5 | Update `['Early','Mid','Late','End']` → `['Early','Lunch','Late','ETH Full']` |
| ETH signals in dataset | SIM_v3.3 | Add RTH trading hours template to sim |

---

## Pending Items — NT8/Sheets (low priority, post-Python)

| Item | Notes |
|------|-------|
| MCChartMarker vertical legend panel | NT8 OnRender panel showing 5 slots with full metrics |
| Multi-year MASTER selector | See MultiYear_MASTER_Architecture.md |
| TOD 13-bucket expansion | 08:30–15:15, 13 × 30-min buckets |
| Per-leg entry/stop offset ticks | Frontrun offset for PB entries |
| Intra-MC PB fills | Phase 2 — remove MCEnded gate |
| Opposing MC cancels PB position | Bear MC cancels open long PB |
| PBLevelExpiryBars | Cancel unfilled legs after N bars post-MC-end |
| RecalcRiskOnStopMove | New stop → new StopDistPts → recalc targets |

---

## Rules for New Chat

1. Never write code until explicitly instructed
2. Always ask: entire file rewrite or old/new snippets?
3. Never invent NT8 APIs — check NT8 docs in project files first
4. Preserve existing architecture unless instructed otherwise
5. No fluff, no affirmations, be direct and technical
6. Read `NT8_NinjaScript_LessonsLearned.md` before writing any NT8/SharpDX code
7. Always search project knowledge and past chats before answering questions about prior decisions
8. Read `docs/README.md` index before adding any new doc — no duplicates, no orphans
