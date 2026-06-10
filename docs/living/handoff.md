# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 10, 2026 (session 7)
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
Gate 2: Sierra bars vs NT8/Rithmic bars — ROOT CAUSES FOUND (see Session 7 below)
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

## Streamlit App (June 8, 2026)

Four-tab app with contract selector and file upload. All tabs share cached data loaded by `data_loader.py`.

| File | Purpose |
|------|---------|
| `app.py` | Entry point, contract selector, tab layout, Reload button; Upload Data expander lives inside Bar Analysis tab |
| `data_loader.py` | Contract registry; parameterised loaders for SC bars, SC ticks, NT bars; upload parsers; `bar_num_from_dt()` |
| `validation.py` | Bar Validation tab — SC vs NT comparison |
| `bar_analysis.py` | Bar Analysis tab — signal sim, charts, monthly breakdown, R sweep |
| `portfolio.py` | Portfolio tab — per-setup 2-leg simulation, equity curves, sweep, saved runs, PDF export |
| `economic_calendar.py` | FOMC hardcoded 2015–2026; NFP/CPI via FRED API |
| `.streamlit/config.toml` | `maxUploadSize = 2000` (MB) |
| `filter_defaults.json` | Bar Validation persisted defaults — not in git |
| `ba_filter_defaults.json` | Bar Analysis persisted defaults — not in git |
| `pf_defaults.json` | Portfolio per-setup params persisted defaults — not in git |
| `pf_saved_runs.json` | Portfolio saved run comparison store — not in git |

**Contract registry (`data_loader.py` → `CONTRACTS` dict):**
- `"ESM6 — 2026"` → `ESM6.CME_BarData.txt` / `NinjaScript Output 03_06_2026 23_08.txt`
- `"ESH21 — 2021"` → `ESH21-CME.txt` / `NinjaScript Output 2021.txt` *(file not yet on disk)*
- Add new contracts by adding an entry to `CONTRACTS` — no other code changes needed
- Contract selector only shows contracts whose SC file exists on disk

**economic_calendar.py — current state:**
- FOMC dates hardcoded 2015–2026; 2026 confirmed from federalreserve.gov on 2026-06-04
- NFP (release_id=50) and CPI (release_id=10) fetched from FRED API; requires `FRED_API_KEY` in `.streamlit/secrets.toml`
- `get_economic_events(event_types: tuple, start, end)` returns DataFrame with DateTime (CT, tz-naive), EventType, Color

**Layout (tab-first design):**
- Tabs (`📊 Bar Viewer | 🔍 Bar Validation | 📈 Bar Analysis | 📊 Portfolio`) are the first element after the page header
- **Source selector runs BEFORE `st.tabs()`** — critical for render-order correctness. Tab1 (Bar Viewer) needs `bar_source` to be set before it renders. If selector was inside Tab3, it would be one render cycle stale.
- Upload UI lives inside the Bar Analysis tab: `📁 Upload Data` expander (3 cols: Tick | OHLC | MC Signals)
- `📡 Bar data source` expander only shown when multiple sources available (inside Tab3, collapsed), but the actual `bar_source` session state key is set before tabs
- Session state carries uploaded data across tabs; Bar Viewer and Bar Validation read from session state silently
- Reload button clears all upload state including `ba_signals`, `bar_source`, and `bar_source_radio`

**Radio widget key guard:** `key="bar_source_radio"` persists across rerenders. After disk SCID load, `st.session_state.pop("bar_source_radio", None)` is called before `st.rerun()` to prevent stale "SC Ticks (disk)" value overriding the new source.

**Upload guard:** The `else` branch of the tick file uploader (empty uploader) only clears `uploaded_sc_*` keys if `uploaded_sc_key` does NOT start with `"scid_"`. This prevents the auto-loaded SCID cache from being evicted on every rerender when the uploader widget is empty.

**Tab 3 — Bar Analysis — section layout (expander order, as of June 9):**
1. `📁 Upload Data` — tick / OHLC / signals upload (collapsed)
2. `📡 Bar data source` — only when choice exists (collapsed)
3. `⚙️ Filters` — date range, DOW, econ events, CC3/CC4 (collapsed)
4. `📶 Signals` — signal scatter map (collapsed)
5. `⚙️ Trading Parameters` — instrument, trade mode radio, column inputs (collapsed)
6. `📋 Summary` — 4 rows × 6 metrics incl. Max Drawdown, **PnL/DD**, Trading Days (**expanded**)
7. `🔍 Optimal R Sweep` (single-leg) OR `🔍 T1×T2 Sweep` + `🔍 Scale-In Sweep (PB × T1 × T2)` (2-leg) (collapsed)
8. `🔍 Stop Multiplier Sweep` (collapsed)
9. `📅 Monthly Breakdown` (collapsed)
10. `📊 Setup Analysis` (collapsed)
11. Unfilled / filtered signal expanders (collapsed)
12. `📈 Daily Chart` (**expanded**)
13. Signal Table + All Signals expanders (collapsed)
14. `🔍 Bar Data Mismatch Analysis` (collapsed)

Only Summary and Daily Chart are expanded by default.

---

## Trade Mode — 2-Leg Scale-In (implemented June 8, 2026)

### Model

E1 enters at signal price. Phase 1 scans **simultaneously** for three events:
- **Stop hit** → E1 stops out, trade over
- **T1 hit** (before PB fills) → E1 exits at profit, trade over (no scale-in)
- **PB fills** (before T1) → E2 adds to position, proceed to Phase 2

Same-bar priority (conservative): **Stop > T1 > PB**. If T1 and PB both reachable on same bar, T1 wins.

Phase 2 (after E2 fills): combined position scans for T2 or original stop.

### Key Prices

| Price | Formula |
|-------|---------|
| T1 | `E1_entry + T1_r × risk_pts` |
| PB trigger | `E1_entry − PB_r × risk_pts` (negative R, for long) |
| E2 fill | `pb_trigger + entry_slip × tick_size` |
| Blended entry | `(E1_price × tv1 + E2_price × tv2) / tv_total` |
| Blended risk | `abs(blended_entry − original_stop)` |
| T2 | `blended_entry + T2_r × blended_risk` |

Stop stays at **original level** after E2 fills.

### ExitReason values (2-leg)

| ExitReason | Meaning |
|------------|---------|
| `T1_only` | T1 hit before PB → E1 profit, no scale-in |
| `Stop` | E1 stopped out in Phase 1 |
| `EOD` | Session end without T1, stop, or PB fill |
| `E1E2+Target` | Combined position hit T2 |
| `E1E2+Stop` | Combined position stopped out |
| `E1E2+EOD` | Combined position held to session end |

### Commission / Slippage correctness

`T1_only` and `Stop` (Phase 1 before PB fills) charge only `contracts_t1` commission and slippage — E2 never traded. `E1E2+*` results charge `contracts_t1 + contracts_t2`.

This is enforced in both `_build` (via `_e2_filled` flag → uses `_tv_active`) and `simulate_trades` (checks `Leg2ExitReason != "NoFill"`).

### Session state keys (2-leg UI)

| Key | Widget | Type |
|-----|--------|------|
| `ba_contracts_t1` | E1 Contracts | int |
| `ba_t1_r_sel` | T1 dropdown (0.50R–3.00R) | str label |
| `ba_contracts_t2` | E2 Contracts | int |
| `ba_ml_pb_sel` | E2 Pullback dropdown | str label |
| `ba_t2_r_sel` | T2 dropdown (0.50R–3.00R) | str label |
| `ba_entry_slip_ml` | Entry slip (ticks) | float |
| `ba_exit_slip_ml` | Exit slip (ticks) | float |
| `ba_stop_offset_ml` | Stop offset (ticks) | int |
| `ba_commission_ml` | Commission ($/contract) | float |

**Critical**: the simulation setup block (line ~3703) reads T2 and PB from selectbox label keys (`ba_t2_r_sel`, `ba_ml_pb_sel`), NOT the old numeric keys. Must use `_r_lbls.index(label)` to convert. If you add new inputs, follow this pattern or values will silently default.

### Chart — 2-Leg annotations

- T1: dotted teal line, label "T1 X.XXR"
- T2: dashed teal line, label "T2 X.XXR"
- PB level: orange dash-dot horizontal line from entry to E2 fill bar, label "PB"
- E2 fill: filled orange circle at `(E2FillTime, E2FillPrice)` with hover

### Trade table — 2-Leg extra columns

`PB Lvl`, `E2 Fill`, `E2 Time` — shown when `PBLevel` column is present in results. Shows "—" for T1_only / Stop / EOD trades where E2 never filled.

### Result dict fields added (2-leg specific)

```python
"PBLevel":    float(pb_trigger) or nan
"E2FillPrice": e2_entry if E2 filled else nan
"E2FillTime":  pd.Timestamp(bar["DateTime"]) if E2 filled else pd.NaT
```

---

## Scale-In Sweep (PB × T1 × T2)

Lives in `_show_optimal_r()` under the `elif multileg:` branch, after the T1×T2 sweep expander.

**Function:** `_run_ml_scalein_sweep(signals, ticks_by_date, ..., pb_vals, t1_vals, t2_vals)`

**Default ranges:** PB: 8 values (−0.25R to −1.50R) · T1: 6 values (0.50R–2.00R) · T2: 9 values (0.50R–3.00R) = 432 combos

**UI controls inside expander:**
- 3 columns: PB range (Shallowest/Deepest), T1 range (Min/Max), T2 range (Min/Max)
- Combo count shown live before running
- Heatmap slices by selected T1 (PB on Y, T2 on X)
- Ranked top-20 table shows all T1 values

**Session state guard:** if `ba_si_sweep_df` exists but lacks `T1_R` column (stale from old 2-param format), it is discarded and user must re-run.

**Matches UI simulation exactly** — both use `filtered_signals`. Exception: sweep ignores ratchet (always `ratchet_r=0`) and `first_trade_only` post-filter.

---

## Summary Row 4 — Metrics

`Slippage | Commission | Total Cost | Max Drawdown | PnL/DD | Trading Days`

PnL/DD = `net_total / abs(max_dd)`. Shows "—" when no drawdown.

Slippage ticks for multileg: derived as `round(slippage_total_usd / tick_value)` — correct because it reflects the actual per-trade dollar amounts (which already account for whether each leg traded).

---

## Simulation Engine (`bar_analysis.py`)

- `_simulate_one_bars_multileg()` — bar-level 2-leg scale-in. Phase 1: simultaneous scan for T1/stop/PB. Phase 2: T2 from blended entry.
- `_EMPTY_TRADE` includes: `PBLevel`, `E2FillPrice`, `E2FillTime`, `SameBarConflict`
- `compute_summary()` — `net_total` uses `filled["NetPnL"].sum()` (correct, per-trade commission applied in `simulate_trades`)

---

## Sweep Tools

### 1. Optimal R Sweep (single-leg) / T1×T2 Sweep (2-leg)
- Auto-switches based on trade mode
- **1D (single-leg):** R from 0.50 to Max R in 0.25 steps
- **2D (2-leg):** all valid (T1, T2) combos where T1 < T2
- Results: `ba_sweep_df` (1D), `ba_t1t2_df` (2D)

### 2. Scale-In Sweep (2-leg only)
- PB × T1 × T2 — 432 combos by default, configurable via range controls
- Results: `ba_si_sweep_df`

### 3. Stop Multiplier Sweep
- 10 stop sizes: 0.25×–2.00× original stop
- Results: `ba_stop_sweep_df`

---

## SCID Data System (Session 6 — June 10, 2026)

### Architecture Decision — 1-Second OHLCV (locked)

**Previous approach:** tick SCID files (individual trades) — deleted June 10, 2026 (108 GB).  
**New approach:** 1-second OHLCV bars stored in SCID format.

**Rationale:**
- 5-minute bar simulation with conservative same-bar priority (Stop > T1 > PB) is too coarse — same-bar conflicts are frequent with tight stops
- Tick data (108 GB, weeks to download) is impractical
- 1-second bars (~210 MB/quarter, ~14 GB total) give simulation granularity sufficient to eliminate same-bar ambiguity while remaining practical to download and store
- 1-minute bars are NOT sufficient — ES 1-min range frequently spans both stop and target simultaneously

**Simulation design (to be built):**
- 5-minute bars: built from 1-second bars for charting/display only
- Simulation engine: scans 1-second bars sequentially within each 5-minute signal window to detect stop/target/PB hits in order

**Data to download:** Configure Sierra Chart to store 1-second OHLCV for all ES quarterly contracts (ESZ09–ESM26). Request historical data from SC.

### SCID Disk Loader

**Data directory:** `C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data`  
**Defined as:** `SCID_DATA_DIR` in `data_loader.py`

**Key functions in `data_loader.py`:**
- `build_scid_quarter_map()` — scans SCID_DATA_DIR for `ES*.scid`, samples timestamps, returns `{quarter: path}`
- `load_scid_ticks_chunked(path, quarters, progress)` — optimised loader: integer UTC pre-filter (eliminates ~65% ETH records before tz_convert), integer RTH check (no strftime), 2M-record chunks. Returns RTH DataFrame: DateTime, Price, Volume
- `resample_ticks_to_bars(ticks)` — resamples to 5-min OHLCV bars
- `build_bars_from_cache(quarters)` — builds 5-min bars one quarter at a time (no OOM); use for >16 quarters

**TODO when 1-second data arrives:**
- `load_scid_ticks_chunked` currently uses `records["Close"]` as tick price — correct for ticks, but for 1-second bars must aggregate OHLC properly (first Open, max High, min Low, last Close per 5-min window)
- `resample_ticks_to_bars` needs updating to resample 1-second OHLCV → 5-min OHLCV (not tick prices)
- Simulation engine needs new 1-second scan path

### Parquet Cache

One Parquet file per calendar quarter — built once via `scripts/build_scid_cache.py`, loaded instantly thereafter.

**Location:** `SCID_DATA_DIR/_scid_cache/{quarter}.parquet` + `last_selection.json`  
**Cache functions in `data_loader.py`:**
- `save_scid_cache(ticks, quarters)` — writes per-quarter Parquet files (snappy)
- `save_last_selection(quarters)` — updates last_selection.json (startup auto-load target)
- `load_scid_cache()` → reads last_selection.json, loads those quarters; legacy ticks.parquet fallback
- `load_quarters_from_cache(quarters)` → loads specific quarters from per-quarter Parquet
- `build_bars_from_cache(quarters)` → bars only, one quarter at a time (OOM-safe for large ranges)
- `list_cached_quarters()` → sorted list of cached quarter strings
- `clear_scid_cache()` — rmtree the `_scid_cache` dir (use with caution — cache takes time to rebuild)

**UI note:** "Unload" button in the SCID expander clears session state only — does NOT delete Parquet files.

**Auto-load on startup:** At top of `main()` in `app.py`, before any tabs render:
```python
if "uploaded_sc_bars" not in st.session_state:
    _cached_ticks, _cache_meta = load_scid_cache()
    if _cached_ticks is not None:
        _cached_bars = resample_ticks_to_bars(_cached_ticks)
        st.session_state["uploaded_sc_ticks"]  = _cached_ticks
        st.session_state["uploaded_sc_bars"]   = _cached_bars
        st.session_state["uploaded_sc_key"]    = f"scid_{','.join(_cache_meta['quarters'])}"
        st.session_state["bar_source"] = "sc_upload"
        st.session_state.pop("bar_source_radio", None)
```

**Session state keys (SCID):**

| Key | Content |
|-----|---------|
| `uploaded_sc_bars` | 5-min bar DataFrame (from SCID or uploaded tick file) |
| `uploaded_sc_ticks` | raw tick DataFrame |
| `uploaded_sc_key` | starts with `"scid_"` for disk/cache loads, else filename |
| `scid_loaded_label` | human-readable label shown in the UI |
| `scid_load_summary` | stats string (n ticks, date range) |
| `scid_quarter_map` | result of `build_scid_quarter_map()` |

### SCID Binary Format (Confirmed)

| Field | Type | Detail |
|-------|------|--------|
| Header | 56 bytes | Fixed header block |
| Record size | 40 bytes | `s_IntradayRecord` |
| `DateTime` | int64 | Microseconds since 1899-12-30 00:00:00 UTC |
| OHLC | float32 × 4 | Open, High, Low, Close |
| NumTrades | int32 | |
| TotalVolume | int32 | |
| BidVolume | int32 | |
| AskVolume | int32 | |

**Timestamp conversion:**
```python
SC_EPOCH = pd.Timestamp("1899-12-30")
dt_utc = SC_EPOCH + pd.to_timedelta(raw_int64_microseconds, unit="us")
dt_ct  = dt_utc.tz_localize("UTC").tz_convert("America/Chicago").tz_localize(None)
```

**Bar timestamp — CONFIRMED (Session 7):** In NinjaTrader with `Calculate.OnBarClose`, `Time[0]` is the bar **close** time. Empirically verified: NT's 15:35 Berlin bar prices match SC's 08:30 CT bar prices exactly (same O/H/L/C within back-adjustment). This confirms the −5 min shift is correct for NT TXT exports.

SC SCID timestamp behaviour: SCID bar timestamps appear to use bar **open** time (08:30:00 for the first RTH bar). The SCID loader does NOT apply a −5 min shift. This was not changed in Session 7 — verify if ever unclear by comparing first SCID bar DateTime to known SC bar open.

### OHLC NT Parser — Dual-Format Support (Session 7)

`parse_ohlc_from_upload()` in `data_loader.py` auto-detects format from first 512 bytes of the file.

**Format 1 — NT CSV** (comma-separated, has header, open times):
```
DateTime,Open,High,Low,Close,Volume
2025-01-02 08:30:00,6238.50,6241.25,6222.00,6222.25,12345
```
- Detected when first line contains `,` and not `;`
- Parses `DateTime` column as-is — already bar **open** time, NO −5 min shift needed
- Tolerant: tries strict format first, falls back to `pd.to_datetime`

**Format 2 — NT TXT** (semicolon-separated, no header, close times):
```
23/12/2024 15:35:00;6269.50;6279.00;6268.00;6273.50;12345
```
- Tries `DD/MM/YYYY HH:MM:SS` first; falls back to `MM/DD/YYYY` if >50% fail
- Detects Berlin vs CT via median hour heuristic (`> 14` → Berlin)
- Berlin path: `tz_localize("Europe/Berlin", ambiguous="infer", nonexistent="shift_forward")` → tz_convert → strip tz → −5 min
- CT path: dt_parsed − 5 min (fast; no DST lookup; preferred)

**Why CT is preferred over Berlin:** `tz_localize("Europe/Berlin")` on 29 K rows requires DST checking for every timestamp — very slow on Windows. The new MyOHLCReader.cs outputs `Time[0]` directly (CT), so Berlin path is legacy only.

**Key invariant:** After parsing, `DateTime` is always the bar **open** time in CT, tz-naive.

---

## Session 7 — Gate 2 Investigation (June 10, 2026)

### NT OHLCExporter (MyOHLCReader.cs) — Fixed

File location: `MyOHLCReader.cs` in repo root (NinjaTrader NinjaScript indicator).

**Problem found:** Old code called `BarCloseTime(Time[0])` to compute close time. But `Time[0]` with `Calculate.OnBarClose` IS already the bar close time — calling `BarCloseTime()` added another 5 minutes, so every bar was exported 5 min late.

**Fix:** Use `Time[0]` directly. Simplified indicator:
- Removed all timezone conversion (Berlin tz code deleted entirely)
- Removed CSV output — TXT only
- Reduced to 2 properties: `OutputPath`, `AppendMode`
- Core write: `Time[0]` direct, no conversion, no helper calls

```csharp
string line = string.Format(CultureInfo.InvariantCulture,
    "{0:dd/MM/yyyy HH:mm:ss};{1:F2};{2:F2};{3:F2};{4:F2};{5}",
    Time[0], Open[0], High[0], Low[0], Close[0], (long)Volume[0]);
```

This matches the exact approach confirmed by a colleague: `Print(Time[0], Open[0], High[0], Low[0], Close[0], Volume[0])`.

**Evidence of fix:** Old file started at `15:40:00 Berlin` (one bar late). New export starts at `15:35:00 Berlin` (correct close of 08:30 bar).

**NT export files on disk:**  
`C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ohlc_export.txt`  
`C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ohlc_export.csv`  
Both ~1.7 MB, written 2026-06-10 17:07 local. These are from an intermediate build (Time[0] fixed, Berlin conversion still present). The final simplified build (no Berlin) must be recompiled in NT and a fresh export run.

### Gate 2 Root Cause — Back-Adjustment Discrepancy

After fixing the timestamp bug, Gate 2 still showed 0% match. Root cause:

- **SC** exports from `ESM26-CME [CB]` — Sierra Chart's "CB" back-adjusted continuous contract
- **NT** exports from its continuous contract — different roll dates and spreads

**Observed deltas (from price comparison):**

| Period | Back-adj delta | Mismatches/day |
|--------|---------------|----------------|
| Dec 2024 – Jun 2025 (ESZ24/H25/M25) | Hundreds of points | ~80 (all bars) |
| Jul 2025 – present (ESU25+) | ~0.50 pt (2 ticks) | 0–10 |

Even 2 ticks is unacceptable — user requires 100% exact match.

**Evidence from price check:**
```
SC  Dec 23 2024 08:30 CT: O=6269.50 H=6279.00 L=6268.00 C=6273.50
NT  Dec 23 2024 08:30 CT: O=6269.00 H=6278.50 L=6267.50 C=6273.00
Delta:                       −0.50    −0.50    −0.25      −0.00
```

### Gate 2 Fix — Individual Contracts Required

Both SC and NT must export from the **same individual (non-back-adjusted) quarterly contract charts** to get exact tick-for-tick price match.

**Contracts needed:** ESZ24, ESH25, ESM25, ESU25, ESZ25, ESH26, ESM26

**SC:** Open individual contract charts (ESZ24-CME, ESH25-CME, etc.), export 5M bars from each.  
**NT:** Run OHLCExporter indicator on each individual contract chart in NT8.

**Agreed next step:** Start with **ESM26 only** (current front month — zero back-adjustment on either platform). Verify 100% match end-to-end. Then expand to full history.

**App change needed (not yet built):** Gate 2 UI must accept multiple per-contract files and stitch them date-by-date for the full comparison. Currently only one NT 5M file slot exists.

### Code Changes — Session 7

| File | Change |
|------|--------|
| `MyOHLCReader.cs` | Completely rewritten — simplified to `Time[0]` direct, no tz conversion, 2 props |
| `data_loader.py` | `parse_ohlc_from_upload` rewritten — auto-detects CSV vs TXT; CSV=no shift; TXT=−5min |
| `validation.py` | Empty DataFrame guard at line ~247 (before `max()`/`min()` date overlap) |
| `app.py` | Empty DataFrame guard after NT 5M parse — shows error with first 200 chars, `st.stop()` |

### Bar Viewer / Bar Validation — Upload-Only Policy

Neither tab has disk fallbacks. If no data is uploaded (and no cache loaded), they show an info message. No 2026 disk data ever appears unless explicitly loaded or cached. This is enforced in `show_bar_viewer()` and `validation.py`.

---

## Data files (not in git — keep in `data/raw/`)
- `ESM6.CME_BarData.txt` (~3GB SC ticks, 2026) — old disk file, not used by bar viewer unless uploaded
- `NinjaScript Output 03_06_2026 23_08.txt` (NT 5M bars, 2026) — old disk file, not used unless uploaded
- `NinjaScript Output 2021.txt` (NT 5M bars, 2021 — needed for ESH21 contract)
- SCID files live at: `C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\`

**Run:** `.venv\Scripts\streamlit run app.py` (Windows)

---

## Commit Status

**Session 1 (June 7):** ✅ Committed + pushed  
**Session 2 (June 7):** ✅ Committed + pushed (no-auto-load, library tenets)  
**Session 3 (June 8):** ✅ Committed + pushed — 2-leg scale-in model complete  
**Session 4 (June 8):** ✅ Committed + pushed — Portfolio tab complete  
**Session 5 (June 9):** ✅ Committed + pushed (`c5c2f0f`) — SCID disk loader, Parquet cache, source selector fix, OHLC auto-detect, upload-only bar viewer/validation  
**Session 6 (June 10):** ✅ Committed + pushed (`e4e0c6c`) — optimised SCID loader (integer pre-filter, no strftime, 8× larger chunks), per-quarter Parquet cache, OOM fix (build_bars_from_cache), Unload button, Select All fix; deleted 108 GB tick SCID files; architecture decision: switch to 1-second OHLCV  
**Session 7 (June 10):** ✅ Committed + pushed — NT OHLCExporter Time[0] fix (MyOHLCReader.cs), NT parser dual-format (CSV/TXT), empty DataFrame guards (validation.py + app.py), Gate 2 root cause documented (back-adjustment); Gate 2 100% match requires individual contracts (ESM26 first)

---

## Portfolio Tab (Session 4 — June 8, 2026)

### Feature Set

- **Per-setup 2-leg simulation** — all enabled CC types run independently using `simulate_trades(multileg=True)` + `compute_summary(is_multileg=True)`
- **Equity curves** — combined portfolio + per-setup traces on one Plotly chart
- **Drawdown chart** — portfolio-level drawdown subplot
- **Per-setup breakdown table** — Trades, Win%, PF, Net PnL, Max DD, Ann Return, Starting Capital configurable
- **Global Settings** — Instrument, date range, contracts T1/T2, slippage/commission, starting capital
- **Setup Parameters** — per-CC T1/PB/T2 dropdowns in expander; Save as Defaults button persists to `pf_defaults.json`
- **Portfolio Sweep** — per-CC independent T1×PB×T2 grid sweep; ranked by PnL/DD, Net PnL, or PF; click row to apply directly to setup config
- **Saved Runs** — save named run with structured name (Scope | Period | Description) to `pf_saved_runs.json`; Compare tab shows side-by-side metrics for all saved runs
- **PDF Export** — `components.html()` with `window.parent.print()`; counter in JS comment forces re-render on every click; `matchMedia('print')` + `Plotly.relayout()` resizes equity chart from 420→680px; no expanders are auto-opened

### Key Technical Patterns

**Versioned widget keys** — programmatic config updates (e.g. "apply sweep row") cannot use `st.session_state["pf_t1_CC2"] = new_val` after widget is rendered. Solution: version counter `pf_cfg_ver` in session state; incrementing it changes the key suffix (`_v0` → `_v1`), creating uninitialized keys that accept `index=` parameter.

```python
def _apply_to_config(cc, t1_raw, pb_raw, t2_raw):
    _cfg = dict(st.session_state.get(f"pf_cfg_{cc}", {}))
    _cfg["t1_idx"] = _t_idx(t1_raw)
    _cfg["pb_idx"] = _pb_idx(pb_raw)
    _cfg["t2_idx"] = _t_idx(t2_raw)
    st.session_state[f"pf_cfg_{cc}"] = _cfg
    st.session_state["pf_cfg_ver"] = st.session_state.get("pf_cfg_ver", 0) + 1
```

**PDF equity chart resize** — CSS alone cannot resize Plotly SVGs (fixed at render time). `matchMedia('print')` fires `Plotly.relayout({height: 680})` on the open "Equity Curves" expander's chart element before print, then restores after.

**Row-level apply** — `st.dataframe(on_select="rerun", selection_mode="single-row")` + apply button renders a per-row apply flow without custom components.

### Known Gaps / Not Yet Verified

- **PDF equity chart resize** — `Plotly.relayout()` is called from an iframe (`components.html`); browser security policy may block `window.parent.Plotly` depending on browser/version. Needs testing.
- **2-leg math** — per-leg P&L math against manual calculations still unverified (carried from session 3).
- **`first_trade_only` filter** — not applied in sweep (pre-existing across all sweeps).

---

## Next Session — Priorities

1. **Configure Sierra Chart for 1-second OHLCV** — set chart type to 1-second bars for all ES quarterly contracts (ESZ09–ESM26), request historical data from SC. Expected: ~210 MB/quarter, full 15-year history in hours.
2. **Run `scripts/build_scid_cache.py`** once 1-second data is on disk.
3. **Update SCID pipeline for 1-second bars** — `load_scid_ticks_chunked` uses `records["Close"]` as tick price; for 1-second bars need to aggregate OHLC. `resample_ticks_to_bars` needs to resample 1-second OHLCV → 5-min OHLCV properly.
4. **Gate 1** — validate Python-built 5-min bars vs SC native 5-min export.
5. **Simulation engine** — new 1-second scan path for stop/target/PB detection within 5-min signal windows.
6. **Carry-over:** Verify PDF equity chart resize, verify 2-leg math (both low priority).

---

## Session 2 — June 7, 2026 — Design Decisions (still valid)

### Scale-In / 3-Leg Design

#### Naming convention

| Layer | E1 | E2 | E3 |
|-------|----|----|-----|
| Code | E1 | E2 | E3 |
| UI | Initial | PB1 | PB2 |
| Trade types | Rocket (E1 only) | E1+PB1 | E1+PB1+PB2 |

#### R reference
- **All targets and stop ratchet triggers use original R** (E1 entry → E1 stop distance).
- Blended average entry is used **only** for BE stop calculations and T2 target.
- Rationale: original R is stable and computed at signal time.

#### PB Level Parameters
- Level as R multiple: `[0.25, 0.33, 0.50, 0.66, 0.75, 1.00]` × original stop distance
- Tick offset (signed integer): fine-tune entry relative to R level
- Hard floor: 1.0R level minimum offset = 0 (negative = buying below stop)

#### Exit Modes — Per Trade Type
Each trade type (Rocket, E1+PB1, E1+PB1+PB2) has independent exit parameters.

#### Stop Ratchet — Per Trade Type
Trigger = after X R move → stop to blended BE / E1 / lock-in R.

---

### WFA Methodology — Locked

| Parameter | Decision |
|-----------|----------|
| Method | Rolling WFA (not anchored) |
| IS window | ~1 year |
| OOS window | ~3 months |
| Total length | 2010–2025 (~56 walk-forwards) |
| WFE minimum | ≥ 50% |
| OOS profitable windows | ≥ 60% |
| Min trades per OOS bucket | ≥ 30 (Pardo), ≥ 100 preferred |

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
| Sierra Charts scid (Delani) | ✅ Parser built | 12 quarterly contracts on disk (ESU23–ESZ25). Parser working: 9M+ ticks/quarter. See SCID Data System section above. |
| NT8/Rithmic tick data | Available | 1 year on disk. Used for Gate 2 bar validation. |
| ESM6 CME tick data (.txt) | Available | 56 trading days. Old disk file — not loaded by default. |
| NT 5M bar data (.txt) | Available | April 1 – June 3 2026. Upload via OHLC uploader. |
| 2022–2025 + pre-2021 data | Arriving | Expected soon. |

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
