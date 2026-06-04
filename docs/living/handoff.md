# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 4, 2026 (evening)  
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

## Streamlit App (June 3–4, 2026)

Two-tab app. Both tabs share cached data loaded by `data_loader.py`.

| File | Purpose |
|------|---------|
| `app.py` | Entry point, tab layout, Reload button in header row |
| `data_loader.py` | Loads SC tick data + NT 5M bars, `get_market_holidays()` |
| `validation.py` | All comparison logic and views for the Bar Validation tab |
| `economic_calendar.py` | Economic event dates — FOMC hardcoded, NFP/CPI via FRED API |
| `filter_defaults.json` | Persisted filter defaults (Save as Default button) — not in git |

**economic_calendar.py — current state:**
- FOMC dates hardcoded 2015–2026; 2026 confirmed from federalreserve.gov on 2026-06-04
- NFP (release_id=50) and CPI (release_id=10) fetched from FRED API; requires `FRED_API_KEY` in `.streamlit/secrets.toml`
- PPI was added then removed — not in scope
- `_fetch_fred_dates` deduplicates: first release per calendar month only (FRED returns initial + revision dates)
- `get_economic_events(event_types: tuple, start, end)` returns DataFrame with DateTime (CT, tz-naive), EventType, Color
- Used by `validation.py` economic event filter expander

**Tab 1 — Bar Viewer**
- ‹/› prev/next buttons + date dropdown → 6 summary metrics → candlestick → collapsible 5-min bar table
- "Show bar numbers" toggle: labels bars 1, 4, 7… (every 3rd, always labels last bar) at bar lows
- Candlestick shading: grey vrects for excluded session zones — reads `excl_first_n`/`excl_last_min` from session state set by Bar Validation tab

**Tab 2 — Bar Validation**
- Compares SC-built bars vs NT pre-built bars (`NinjaScript Output 03_06_2026 23_08.txt`, not in git)
- NT timestamps converted Berlin CEST → CT, close→open (−7h −5min)
- **Single ⚙️ Filters expander** containing all controls:
  - Exclude NYSE holidays + Show commentary toggles (top row)
  - Display: ignore volume, shade excluded zones
  - Session Boundaries: first N bars slider (0–12), last N min slider (0–90)
  - Day of Week: Mon–Fri include checkboxes
  - Economic Events: FOMC/NFP/CPI, Skip full day or Window ±N min
  - Save as Default button → writes `filter_defaults.json`, restored on next load
- Summary row 1: Matched Bars / Trading Days / OHLC Exact Match % / Holiday Bars Excl. / Event Bars Excl.
- Summary row 2: SC Only / NT Only / Vol Mismatches / Open Bars Excl. / Close Bars Excl. / DOW Bars Excl.
- Charts always show full post-holiday dataset; excluded zones shaded with grey overlay (overlay bar trace approach — `add_vrect` unreliable on categorical axes)
- Commentary toggle: hides all `_info()` and commentary blocks when off
- Known findings: Open has most mismatches (boundary noise), H/L nearly perfect, volume expected to differ

**Data files — share via Google Drive with Thomas:**
- `data/raw/ESM6.CME_BarData.txt` (~3GB)
- `data/raw/NinjaScript Output 03_06_2026 23_08.txt`

**To share app with Thomas:** `ngrok http 8501` → send URL

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
