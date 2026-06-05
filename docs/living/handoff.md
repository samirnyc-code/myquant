# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 5, 2026  
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

## Streamlit App (June 5, 2026)

Three-tab app with contract selector. All tabs share cached data loaded by `data_loader.py`.

| File | Purpose |
|------|---------|
| `app.py` | Entry point, contract selector, tab layout, Reload button |
| `data_loader.py` | Contract registry; parameterised loaders for SC bars, SC ticks, NT bars; `bar_num_from_dt()` |
| `validation.py` | Bar Validation tab — SC vs NT comparison |
| `bar_analysis.py` | Bar Analysis tab — signal sim, charts, R sweep |
| `economic_calendar.py` | FOMC hardcoded 2015–2026; NFP/CPI via FRED API |
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

**Tab 1 — Bar Viewer**
- ‹/› prev/next buttons + date dropdown → 6 summary metrics → candlestick → collapsible 5-min bar table
- Bar numbers derived from `bar_num_from_dt(DateTime)` — correct even when bars are missing
- Incomplete days (< 81 bars) show a warning banner with first-bar time
- Candlestick shading: grey vrects for excluded session zones

**Tab 2 — Bar Validation**
- Compares SC-built bars vs NT pre-built bars for selected contract
- NT timestamps converted Berlin CEST → CT, close→open (−7h −5min)
- Filters: NYSE holidays, DOW, session boundaries, economic events, Save as Default

**Tab 3 — Bar Analysis**
- Upload MC signals file (space-delimited: `Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop`)
- Same filters as Bar Validation plus: CC3/CC4 type filter, first-trade-of-day toggle
- Trading params: instrument (ES/MES), contracts, entry/exit slippage (ticks), stop offset, target R, commission
- Entry sim: stop-order fill logic, first tick AFTER signal bar close must tick through signal price, slippage applied post-fill
- Signal table: SE Price / Fill Price / Entry Price (w/slip) columns; MAE/MFE in pts and R; cumulative PF; Exit Type (Target/Stop/EOD)
- Summary strip: 3 rows × 6 metrics including MAE R / MFE R
- Per-day chart: candlestick + signal markers + stop/target/BE lines + PnL annotations
- Optimal R sweep (0.50–5.00, 0.25 steps): table with gold bold highlights on best per metric + line chart
- ‹/› nav fixed (no key on selectbox); contract switch resets date/chart state automatically

**Data files (not in git — keep in `data/raw/`):**
- `ESM6.CME_BarData.txt` (~3GB SC ticks, 2026)
- `NinjaScript Output 03_06_2026 23_08.txt` (NT 5M bars, 2026)
- `NinjaScript Output 2021.txt` (NT 5M bars, 2021 — needed for ESH21 contract)
- `NinjaScript Signals 2021.txt` (MC signals 2021 — upload via Bar Analysis file uploader)

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
