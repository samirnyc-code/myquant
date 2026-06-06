# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 7, 2026  
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

**Tab 3 — Bar Analysis — section layout (expander order, as of June 7):**
1. `📁 Upload Data` — tick / OHLC / signals upload (collapsed)
2. `📡 Bar data source` — only when choice exists (collapsed)
3. `⚙️ Filters` — date range, DOW, econ events, CC3/CC4 (collapsed)
4. `📶 Signals` — signal scatter map (collapsed)
5. `⚙️ Trading Parameters` — instrument, trade mode radio, column inputs (collapsed)
6. `📋 Summary` — 4 rows × 6 metrics incl. Max Drawdown + Trading Days (**expanded**)
7. `🔍 Optimal R Sweep` or `🔍 T1×T2 Sweep` — directly under Summary (collapsed)
8. `🔍 Stop Multiplier Sweep` — 0.25×–2.00× of original stop (collapsed)
9. `📅 Monthly Breakdown` — monthly table + equity/DD chart + setup% chart (collapsed)
10. `📊 Setup Analysis` — per-setup breakdown table (collapsed)
11. Unfilled / filtered signal expanders (collapsed)
12. `📈 Daily Chart` — nav controls, date picker, chart + signal markers (**expanded**)
13. Signal Table for day expander + All Signals expander (collapsed)
14. `🔍 Bar Data Mismatch Analysis` (collapsed)

Only Summary and Daily Chart are expanded by default. All others collapsed.

---

## Trade Type Column Layout (tested June 7, 2026)

Inside `⚙️ Trading Parameters` expander:

1. `st.radio("Trade Mode", ["Single Leg", "2-Leg"], key="ba_trade_mode")` — horizontal, persisted in session state. **Do not use st.button for mode switching** — buttons reset on any widget rerun; radio does not.
2. Three columns: **Single Leg** | **2-Leg** | **3-Leg** (placeholder)

**Single Leg column:**
- Mode radio: `AIAO | BE Stop` (`key="ba_sl_mode"`)
  - AIAO: standard all-in-all-out, one target
  - BE Stop: T1 moves stop to break-even (`t1_action="be_only"`, `contracts_t1=0`); needs Target 1 R input (`key="ba_t1_r_sl"`) and Target 2 R (`key="ba_target_r_sl"`)
- Keys: `ba_contracts_sl`, `ba_target_r_sl`, `ba_entry_slip_sl`, `ba_exit_slip_sl`, `ba_stop_offset_sl`, `ba_commission_sl`
- Commission default: ES = $3, MES = $1 (from `INSTRUMENTS[inst]["default_commission"]`)

**2-Leg column:**
- Leg 1: `ba_contracts_t1`, `ba_t1_r`, `ba_t1_action_radio` → `t1_action = "exit" | "be_only"`
- Leg 2: `ba_contracts_t2`, `ba_target_r_ml`
- Execution: `ba_entry_slip_ml`, `ba_exit_slip_ml`, `ba_stop_offset_ml`, `ba_commission_ml`
- If `t1_r >= target_r_ml`: `_ml_invalid = True` flag; warning shown; column stays visible; derive block falls back to single-leg

**Derive block (3-way after columns):**
- `_is_ml and not _ml_invalid` → 2-leg multileg path
- `_is_sl and ba_sl_mode == "BE Stop"` → `use_multileg=True`, `t1_action="be_only"`, `contracts_t1=0`
- else → single-leg AIAO

All paths alias to: `target_r`, `entry_slip`, `exit_slip`, `stop_offset`, `commission`, `contracts`, `t1_r`, `t1_action`, `contracts_t1`, `contracts_t2`, `use_multileg`.

**Trade mode key:** `ba_trade_mode` = `"Single Leg" | "2-Leg"`

---

## Multileg (2-leg) Simulation (tested June 7, 2026)

**Key functions in `bar_analysis.py`:**

- `_simulate_one_multileg(sig_dt, direction, signal_price, stop_csv, day_ticks, target_r, t1_r, t1_action, entry_slip, exit_slip, stop_offset, tv1, tv2, manual_fill=None)` — tick-level 2-leg sim
- `_simulate_one_bars_multileg(...)` — bar-level fallback, same signature
- Both implement Phase 1 (T1/Stop) and Phase 2 (T2/BE stop) simulation loops

**Per-leg tick values:**
- `tv1 = tick_value * contracts_t1` (Leg 1 dollar value per tick)
- `tv2 = tick_value * contracts_t2` (Leg 2 dollar value per tick)
- `tv_total = tv1 + tv2` — used for risk dollar, MAE/MFE dollar, slippage dollar

**t1_action modes:**
- `"exit"` — Leg 1 exits at T1; BE stop set for Leg 2; commission = 2×
- `"be_only"` — T1 just moves stop to BE; full position continues; `contracts_t1 = 0`; commission = 1×

**Result dict includes:** `Leg1ExitReason`, `Leg1ExitPrice`, `Leg1GrossPts`, `Leg1GrossPnL`, `Leg2ExitReason`, `Leg2ExitPrice`, `Leg2GrossPts`, `Leg2GrossPnL`, `Target1` (T1 price), `Target` (T2 price)

**`_EMPTY_TRADE`** includes all multileg fields with NaN defaults.

**`simulate_trades` signature:**
```python
def simulate_trades(
    signals, ticks_by_date, target_r,
    entry_slip, exit_slip, stop_offset,
    tick_value, contracts, commission,
    overrides=None, bars_by_date=None,
    multileg=False, t1_r=1.0,
    t1_action="exit",
    contracts_t1=1, contracts_t2=1,
) -> pd.DataFrame:
```

**`compute_summary` signature:**
```python
def compute_summary(results, commission, is_multileg=False, t1_action="exit"):
```

**Chart — T1 and T2 lines:**
- T1: dotted teal line (`dash="dot"`) from entry to exit timestamp; label "T1 X.XXR"
- T2: dashed teal line (`dash="dash"`); label "T2 X.XXR" (or `"X.XXR"` in bold for single-leg)
- Both drawn via `fig.add_shape` + `fig.add_annotation` in `make_analysis_chart`

---

## Simulation Engine (`bar_analysis.py`)

- `parse_signals(raw)` — parses MC signal export; called from `app.py` now (not inside `show_bar_analysis`)
- `_simulate_one()` — tick-level single-leg sim; stop-order fill, MAE/MFE, slippage tracking
- `_simulate_one_bars()` — bar-level fallback; `>=` on DateTime to get correct next bar
- `_simulate_one_multileg()` — tick-level 2-leg sim (2-phase)
- `_simulate_one_bars_multileg()` — bar-level 2-leg fallback (2-phase, conservative)
- `simulate_trades()` — dispatches to tick or bar sim; single-leg or multileg path
- `compute_summary()` — returns dict with n_trades, win_pct, PF, exp, MAE/MFE R, max_dd, trading_days
- `_show_monthly_breakdown()` — equity curve + OLS trend line + DD bars + setup% chart (dynamic signal types)
- `_show_mismatch_analysis()` — collapsed by default

**Hover behavior (Daily Chart):**
- Signal/entry/exit bars use `fill="toself"` + `hoveron="fills+points"` + center marker for reliable hover
- `<extra></extra>` removes trace-name badge; `font_size=15` in hoverlabel
- `hoverinfo="skip"` on visual markers (circle-open, x)

---

## Data files (not in git — keep in `data/raw/`)
- `ESM6.CME_BarData.txt` (~3GB SC ticks, 2026)
- `NinjaScript Output 03_06_2026 23_08.txt` (NT 5M bars, 2026)
- `NinjaScript Output 2021.txt` (NT 5M bars, 2021 — needed for ESH21 contract)
- `NinjaScript Signals 2021.txt` (MC signals 2021 — upload via Bar Analysis Upload Data panel)

**Run:** `pkill -f "streamlit run"` then `.venv/bin/streamlit run app.py`

---

## Sweep Tools (tested June 7, 2026)

Three sweep expanders live directly under Summary:

### 1. Optimal R Sweep (single-leg) / T1×T2 Sweep (2-leg)
- Auto-switches based on trade mode
- **1D (single-leg):** sweeps R from 0.50 to Max R in 0.25 steps; columns: R, Win%, PF, Net PnL, DD $, PnL/DD, Exp $
- **2D (2-leg):** sweeps all valid (T1, T2) combos where T1 < T2, up to Max T1 / Max T2; produces heatmap + ranked top-20 table
- Both have a `Max R` number input (default 3.0)
- Results stored in `st.session_state["ba_sweep_df"]` (1D) or `st.session_state["ba_t1t2_df"]` (2D)

**2D ranked table highlighting:**
- `_apply_best_green()` highlights best value per metric column in `#1a9850` (heatmap RdYlGn max green)
- Highlight logic: `_hl_max` for all except DD $ (`_hl_min`); threshold gates (PF > 1.0, Net PnL > 0, PnL/DD > 0, Exp $ > 0, Win % > 0)
- T1 and T2 cells on the rank-1 row are also highlighted green (`_hl_rank1_t1t2` applied after `_apply_best_green`)

### 2. Stop Multiplier Sweep
- Sweeps 10 stop sizes: `[0.25, 0.33, 0.50, 0.66, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]` × original signal stop
- 1.00× = baseline (original stop); < 1.00× = tighter; > 1.00× = wider
- Target scales proportionally (T R is preserved relative to the new stop distance)
- `_apply_stop_mult(signals, mult)`: modifies `StopPrice` in a copy using vectorized long/short masks before passing to `simulate_trades`
- Results stored in `st.session_state["ba_stop_sweep_df"]`; line chart: Net PnL + PF vs Stop Mult

---

## Pending / Not Yet Tested (June 7)

Both items verified June 7 — nothing pending.

---

## Next Session — Scale-In Trades & 3-Leg Exits

### Scale-in concept
- After entering at the signal price, price pulls back toward the stop before continuing
- We add contracts at pullback (PB) levels between 0.25R and 1R of the original stop distance
- **PB levels** use the same multipliers as the stop sweep: 0.25, 0.33, 0.50, 0.66, 0.75, 1.00 × original stop distance from signal price
- Each scale-in has its own entry price, contributing to a blended average entry

### 3-leg trade structure
A 3-leg trade = original entry + 2 scale-ins. Target adjustment logic:
- **Scale-in 1 fires:** T1 target is recalculated (based on new blended average entry or new risk)
- **Scale-in 2 fires:** T1 target is recalculated again; T2 target is recalculated for the first time
- **BE mode** is also a target mode for scale-in trades (instead of moving target forward, move stop to break-even at the scale-in price)

### Implementation notes for next session
- Scale-in fills follow the same stop-order logic as the initial entry (price must trade through the PB level)
- Need to decide: does "R" after scale-ins reference the original risk (signal→stop) or the new blended risk?
- Stop sweep mults already exist (0.25×–2.00×) — PB level sweep will likely use a similar parameter
- `_simulate_one_multileg` is the foundation; scale-in adds a 3rd phase before the exit phases
- The 3-Leg column in Trading Parameters is already reserved (`"*Coming soon*"` caption) — fill it in

---

## Commit status

✅ Committed June 7, 2026.

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
9. **NEVER commit and push code the user has not tested. Syntax check is not a test.**
