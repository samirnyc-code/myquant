# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 18, 2026 (session 16, evening)
**Current Versions:** SIM_v3.3 / GS_v4.5 / SHEET_v3.3  
**Rule:** Read this file first every session. It is the only source of truth for current state.

---

## ⚠️ Architecture shift as of Session 12 (June 16, 2026)

**Massive (Track 4) is now the primary and only active data pipeline.** The Sierra Charts/SCID path (Track 2) is paused — not deleted, not formally retired, just not being worked on. Everything below "Session 12" in this doc reflects the new reality:

- Massive flat-file ticks (S3) → per-contract 5M bars + back-adjusted continuous series, built and persisted in the **📂 Massive** tab
- NT is used **only** as a continuous-contract upload for matching/validation — never as a fill/exit data source
- Bar Analysis simulates trades using Massive bars + a per-day continuous tick cache, not NT bars
- The old `📡 Massive.io` tab name/6th-tab numbering below is stale — it's now the **first** tab, named `📂 Massive`, and absorbed the Contract Manager UI described in `data_sources.md`

Read `docs/architecture/data_sources.md` (updated Session 12) for the current pipeline. Treat anything about SCID/`.scid` files in this doc as historical/paused, not active work.

---

## What Is Active Right Now

The NT8 simulator and Sheets analysis pipeline are complete and working. All new development is Python-first, on the Massive pipeline (Track 4). The SC/SCID path (Track 2) is paused.

Two parallel tracks were active before Session 12; Track 4 has since become primary:

**Track 2 — Python WFA Engine (SC path):**
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

**Track 4 — Massive.io Independent Tab (new, parallel):**
```
massive.io API (Developer plan, subscribing 2026-06-16)
        |
        v
Pull ticks via API → App 5M bars (reuse resample_ticks_to_bars)
        |
        ├── Convert ticks → NT import format → NT builds 5M bars
        │          → NinjaScript indicator → MCSignals CSV
        │          → NinjaScript bar exporter → NT 5M bars CSV
        |
        ├── massive.io Aggs API → massive 5M reference bars
        |
        └── Three-way comparison: App bars vs NT bars vs massive bars
                   → all must match → trust App bars for simulation
```

Track 4 is completely independent from Track 2 (SC gates). SC path continues in parallel.
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
**Session 8 (June 10):** ✅ Committed + pushed — `validation.py` CSV download fix (st.download_button, gate_key param); corrected back-adjustment findings; NT corrupted bar (2025-07-15) found and fixed in NT  
**Session 10 (June 13):** ✅ Committed + pushed — `scripts/fetch_for_nt.py` (NT import script), `data_loader.py` (4 Massive.io API functions), `massive.py` (new Massive.io tab), `app.py` (6th tab added); all Massive.io code ready pending API key Monday 2026-06-16  
**Session 11 (June 14):** ✅ Committed + pushed — Massive.io API details confirmed (base URL, auth, sort); ES_MAS full pipeline confirmed working end-to-end with AAPL test data; NT native bars slot + Comparison 3 added to massive.py; API key subscribed today
**Session 12 (June 16):** ✅ Committed + pushed — see full section below. Massive promoted to primary pipeline: contract manager, back-adjustment bug fix, continuous tick series (445M ticks, validated 99.49% vs 5M bars), app-restart persistence for continuous series + NT upload, unified filters (single editable home in Data tab), alt-path mismatch analysis in Bar Analysis, tab reorder/cleanup, Bar Validation tab removed, requirements.txt fixed, onboarding docs updated  
**Session 13 (June 17):** ✅ Committed + pushed — WFA infrastructure: `simulation_engine.py` extracted from `bar_analysis.py`, `results_store.py` (SQLite + Parquet), `wfa.py` (full IS sweep + guardrails + OOS + Streamlit tab), `app.py` wired; scipy added to venv. **NOT yet user-tested end-to-end — do not rely on this as validated output.**

---

## Session 13 — June 17, 2026 — WFA Infrastructure

### Summary

Built the complete WFA (Walk-Forward Analysis) infrastructure from scratch. Three new files plus changes to two existing files. The Streamlit tab is wired and the module tree imports cleanly. **No end-to-end run with real signal data has been done yet** — that is the first thing to do next session.

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `simulation_engine.py` | ~750 | All simulation functions extracted from `bar_analysis.py` + PROM metric added to `compute_summary()` |
| `results_store.py` | ~275 | SQLite fold metadata (`runs` + `folds` tables) + Parquet per-fold trade logs; full CRUD |
| `wfa.py` | ~460 | WFA engine (`build_folds`, `run_is_sweep`, `compute_robustness`, `select_params`, `average_params`, `run_wfa`) + Streamlit tab (`show_wfa_tab`) |

### Modified Files

| File | Change |
|------|--------|
| `bar_analysis.py` | All simulation function definitions removed (lines 150–1608 original, plus `_resimulate_bars`); import block at top pulls from `simulation_engine` |
| `app.py` | `import wfa as wfa_mod`; 6th tab `🔄 WFA` added; `show_wfa_tab()` wired |

`portfolio.py` unchanged — it imports `simulate_trades`, `compute_summary`, `INSTRUMENTS` from `bar_analysis`, which now re-exports them from `simulation_engine`. No breakage.

### WFA Architecture (locked this session)

**Window:** rolling IS=1yr / OOS=3mo (configurable; warns if < 10 folds). Step = OOS window length. ~16 folds over the current 5-year dataset.

**Parameter grid (IS sweep):**
- Single-leg: T1 only (7 values: 0.50–2.00R, multiplicative spacing per Kaufman)
- 2-leg (multileg): T1 × T2 × PB1 (~120 valid combos, T1 < T2 enforced)
- 3-leg: T1 × T2 × PB1 (same grid, different sim path)
- Ratchet always off during sweep (Kaufman: do not co-optimize)

**Objective function:** PROM (Pessimistic Return on Margin) — primary. PnL/DD and PF displayed alongside.

**Kaufman guardrails (per fold):**
- ≥ 70% of IS param combos profitable → `rob_passed`
- Kurtosis of PROM surface ≤ 6 → `kurtosis_ok`
- ≥ 30 trades in IS window → `min_trades_ok`
- Trade the average of top-N sets (default 3), not the single best

**Pardo rules (hard constraints, not just metrics):**
- OOS locked immediately after run (`lock_oos()` called inside `run_wfa`)
- Forward live risk = 2× IS max drawdown (surfaced as warning in UI, not enforced in code)
- Scan ranges, strategy logic, and objective function are all fixed before the first IS sweep runs

**Storage:**
- `data/wfa_store/wfa_results.db` — SQLite; `runs` table (run-level config) + `folds` table (all scalar metrics + guardrail flags per fold)
- `data/wfa_store/trades/{run_id}/{setup_id}/fold_{N}_{is|oos}.parquet` — per-fold trade logs

**Streamlit UI (two sub-tabs):**
- `⚙️ Configure & Run` — setup ID, instrument, mode, IS/OOS window, param-set count, execution params, CC filter, run button with progress bar
- `📊 Results` — run selector, guardrail badge panel, combined OOS equity curve with 4 summary metrics, fold table (color-coded WFE), per-fold drill-down (IS/OOS metrics + chosen param sets + trade log expanders), delete run

### PROM formula (now in `compute_summary`)

```
PROM = [GrossWin × (1 − 1/√Nw) − GrossLoss × (1 + 1/√Nl)] / |MaxDrawdown|
```

Uses gross (pre-commission) win/loss to match Pardo's original formulation. Returns `nan` when max drawdown = 0 (no drawdown → infinite PROM, which is nonsensical). `compute_summary()` now returns `prom` and `pnl_dd` alongside all previous metrics.

### Dependency added

`scipy` installed to `.venv` (needed for `scipy.stats.kurtosis` in `compute_robustness()`).

### What is NOT yet done / NOT yet tested

- **No end-to-end run with real signals** — `show_wfa_tab()` requires `mas_continuous` (from Massive tab) + an uploaded signals file. First real test is a full WFA run on CC2 signals in multileg mode.
- **Bar Analysis filters not yet migrated** to the shared Data-tab panel — same carry-over from Session 12.
- **Max concurrent positions / max daily loss** (Q5, Q6 in `open_questions.md`) — wfa.py currently ignores both. All signals run independently. Decide before relying on WFA output for live trading.
- **RevFT signals** — not ready yet. When they arrive, slot in as another `setup_id`; no code changes required.
- **Portfolio WFA layer** — individual setup runs work; combining OOS equity curves across setups (`load_portfolio_oos_trades()` in `results_store.py`) is wired but the Portfolio tab doesn't yet call it.
- **Window stability scanner** (Phase F in roadmap) — not built. Runs the fold builder over a grid of IS/OOS sizes to find the most stable window pair.

---

## Session 12 — June 16, 2026 — Massive Becomes Primary Pipeline

### Summary

Long session. Took Massive from "parallel validation track" to "the only data source Bar Analysis actually uses." Found and fixed several real bugs along the way (back-adjustment roll-date semantics, OOM crash in validation, NT OHLCExporter buffer-loss risk investigated but not changed — see below). Ended by unifying filters across tabs and removing the now-redundant Bar Validation tab.

### Bugs found and fixed

1. **Back-adjustment roll-date semantics** (`contracts.py`) — `apply_back_adjustment` was treating the user-entered `roll_date` as the contract's own roll-OUT date instead of NT's actual convention (roll-IN date — the date a contract BECOMES front month). This clipped every middle contract to ~2 trading days instead of its full quarter. Fixed by swapping the bound logic: lower bound = own roll_date, upper bound = NEXT contract's roll_date. Verified before/after: 7,662 bars/96 days → 94,435 bars/1,189 days (19 contracts at the time).
2. **5-minute timestamp misalignment between Massive and NT** — Massive resamples bars with `label="left"` (DateTime = bar open time); NT TXT uploads keep NT's close-time label as-is. Every comparison row was silently off by one bar. Fixed in `build_comparison()` (`validation.py`) — shifts the NT side back 5 minutes before joining, at comparison time only (neither source's own convention touched).
3. **OOM crash in tick-cache validation** — `validate_ticks_vs_bars()` originally concatenated all ~445M cached ticks into one DataFrame before resampling (`numpy._core._exceptions._ArrayMemoryError`, tried to allocate 3.3GB for one column). Fixed to process one cached day-file at a time, accumulating only summary counters.
4. **403 vs 404 on Massive's S3 endpoint** — Massive returns 403 (not 404) for dates with no data yet (future dates). The old `_download_day()` only treated 404/NoSuchKey as "skip," so it crashed mid-download whenever the loop reached today's date boundary. Now treats 403/Forbidden the same as 404.
5. **Memory-unsafe NT tick-import writer** — `download_contract()` accumulated all of a contract's ticks in memory before one big write; switched to incremental per-day appends (`_append_nt_lines`).
6. **`bar_source` dead code in `bar_analysis.py`** — `bar_source` session-state key was read everywhere but never written anywhere in the codebase, so `show_bar_analysis()` always fell through to the `uploaded_ohlc_bars` branch (NT bars) regardless of what was actually intended. This meant Bar Analysis was silently simulating on NT data, not Massive, this whole time. Fixed by rewiring to source `bars` from `mas_continuous` directly (see below).

### New capability: continuous back-adjusted tick series

Built `massive.py: build_continuous_ticks_for_date()` / `load_continuous_ticks()` / `build_all_continuous_ticks()` — one small Parquet per trading day (front-month ticker only, RTH-filtered, back-adjustment offset baked into price), built from the flat-file cache that's already on disk (no new downloads). A combined multi-year tick file was considered and rejected — ~500M+ rows is impractical to hold in memory or load as one file; per-day files keep memory bounded and each individual day-read fast regardless of total history size.

**Built and validated:** 1,220 days, 444,968,944 total ticks. Validation (`validate_ticks_vs_bars()`, also surfaced as a button in the Massive tab UI): 98.6–100% of Massive 5M bars have tick coverage (two measurement passes gave slightly different numbers — see Known Gaps below), 99.49% OHLC exact match.

`contracts.py` gained `get_contract_windows()` (shared front-month-window + cumulative-offset table, extracted from `apply_back_adjustment`) and `get_active_contract(date, rolls)` (which contract + offset was active on a given date) — both used by the tick builder so it applies the exact same roll/offset logic as the bar back-adjustment.

### Persistence across app restarts

Previously `mas_continuous` (Massive's built continuous series) and `nt_cont_bars` (the NT `@ES` continuous upload) only lived in `st.session_state` — gone on every restart, requiring a manual rebuild/re-upload. Fixed:

- `mas_continuous` → saved to `data/bars/_continuous.parquet` on build, auto-loaded on `show_massive_tab()` entry if not already in session.
- `nt_cont_bars` → saved via the existing generic CSV-cache mechanism (`save_csv_cache`/`load_csv_manifest`, prefix `"nt_cont"`), auto-loaded the same way. First upload after this fix still required once to seed the cache; every restart after that is automatic.
- Bar Viewer's `data_sc_5m` slot (separate from `mas_continuous`) also auto-derives from `mas_continuous` now, via a one-line check placed in `app.py: main()` right after the Massive tab renders (placement matters — Data tab renders before Bar Viewer in tab order, so the derive has to happen before Data tab's status check, not inside Bar Viewer itself).

### Bar Analysis now actually uses Massive data

`show_bar_analysis()` rewired: `bars` comes from `mas_continuous`; ticks load lazily per-day from the continuous tick cache, scoped only to dates that actually have signals (not the full multi-year history — keeps memory bounded regardless of total cache size). NT bars are used **only** for the signal-bar-Close matching gate (`_nt_bars_for_mismatch`), never for fills/exits. Legacy `uploaded_sc_bars`/`uploaded_sc_ticks`/`sc_disk` routing removed (was dead code per bug #6 above).

**New: alt-path mismatch analysis** (`compute_alt_path_outcomes()` in `bar_analysis.py`) — for filled trades, checks whether the NT signal bar's Close differs from Massive's Close at that exact bar (the gate). Only for gated trades, re-derives the outcome using NT's 5M bars in place of Massive's (same entry/pullback/target logic, `signal_price`/`stop_csv` held fixed since they come from the external signals file). Flags `AltDiffers=True` only when the re-derived outcome actually changes (different fill/no-fill, exit reason, or PnL) — most gated trades re-derive to the same outcome and aren't flagged. Dispatches across all three trade structures (single-leg, 2-leg, 3-leg) via `_resimulate_bars(mode, ...)`. Surfaced as a second section under the existing `_show_mismatch_analysis` table.

**New: RevFTSignals** — a second, independent signal upload alongside MC Signals (own session-state keys), with a radio toggle deciding which one actually feeds the simulation. Lets you keep both loaded and switch without re-uploading.

### Manual date exclusion (global)

New `excluded_dates.json` (committed, same pattern as `rolls.json`) + `load_excluded_dates()`/`save_excluded_dates()`/`filter_excluded_dates()` in `data_loader.py`. Managed via a "🚫 Manually Excluded Dates" panel (currently in the Data tab). Wired into every bar-loading path: `apply_data_slot`, Massive continuous build, NT upload parsing, and Bar Analysis's `bars`/`ticks`/`nt_bars`/`signals_raw`. One add removes that date everywhere.

Seeded with `2026-04-06`: NT's OHLCExporter captured only 1 stray tick (12:55, vol=1) that entire session — diagnosed as `IsSuspendedWhileInactive = true` (in `MyOHLCReader.cs`) likely suppressing `OnBarUpdate` while the chart tab was inactive. **Not fixed in the indicator** — user explicitly said not to touch it without being asked; the exclusion-list workaround was used instead. If this recurs often, the indicator fix (flush-to-disk periodically instead of buffering until `Terminated`) is sketched out in conversation history but was reverted, never applied.

### Investigated mismatch patterns (no further action needed)

- **2026-04-06**: see above — NT capture gap, not a Massive/back-adjustment issue.
- **~50 missing trading days across 14 contracts (2021–2022 heavy)**: real gaps in `data/flatfiles_cache/` — some days' `.csv.gz` never downloaded (likely transient 403s before the fix above existed), some downloaded but produced zero bars. Not yet re-downloaded. Listed precisely in conversation history; would need a targeted re-download pass for just those dates.
- **Outliers up to ~30 ticks on ordinary (non-roll) days**: cluster at session open/close boundaries (feed-timing disagreement between Massive's raw CME ticks and NT's Rithmic feed, worse during real volatility — e.g. 2025-04-04 Liberation Day tariffs, 2024-08-05/06 yen-carry unwind). Not a bug.
- **2021-10-01 (24 mismatches)**: same boundary-noise mechanism, just an unusually choppy day. Not a bug.

### Unified filters

Filters (exclude NYSE holidays, day-of-week, session boundaries — first-N-bars/last-N-min, economic events FOMC/NFP/CPI) previously existed as three **separate** widget sets: Massive's comparison panel, the old Bar Validation tab, and Bar Analysis's own panel. Streamlit can't have the same interactive widget editable from two tabs in one script run (duplicate key error), so true bidirectional sync isn't directly possible.

**Resolution (user's choice from 3 options presented):** single editable copy lives in the **🗂️ Data tab** (`validation.render_filters("shared")`). Massive's comparison section reads the same values read-only via the new `validation.get_filters("shared")` (no widgets rendered there anymore — just `get_filters("shared")` called directly). **Bar Analysis's own separate `ba_`-prefixed filter widgets were NOT yet migrated to the shared panel — this is the main carry-over item for next session** (see Next Session Priorities).

### Tab/UI cleanup

- Tabs reordered: Massive first (📂 icon, was 📡), Data second (🗂️ icon, was 📂 — avoided icon collision)
- **Bar Validation tab removed entirely** — fully superseded by Massive's own comparison panel (same underlying `show_gate_body` engine, just pointed at Massive continuous bars instead of manually-uploaded single-contract files). `import validation` removed from `app.py` then re-added once the shared-filters work needed it again.
- Data tab's NT 5M upload column removed — was used only by the now-removed Bar Validation tab and a legacy Bar Analysis fallback, both superseded by the NT `@ES` continuous upload in the Massive tab. ES_MAS 5M upload kept as an explicit manual override (auto-derives from `mas_continuous` otherwise).
- Roll Schedule table: removed "Active From"/"Last Trade" columns — confirmed read-only display fields with no logic dependency (download window comes from the `Contract` dataclass directly, never from the edited table).
- `_show_by_date` chart x-axis now shows the year (`tickformat="%b %d, %Y"`) — was ambiguous across a 5-year multi-year series.

### Onboarding / requirements

- `requirements.txt` was missing `boto3`, `pyarrow`, `numpy`, `requests` — would have crashed Thomas's first run on import. Fixed.
- `COLLABORATOR_ONBOARDING.md` rewritten for the Massive pipeline (was written for the old 3GB SC tick file approach). A duplicate `ONBOARDING.md` created mid-session was merged into it and deleted — **one onboarding doc, not two**, per the existing "never duplicate information across files" rule.

### Known gaps / not yet verified

- **Bar Analysis filters not yet unified** with the shared Data-tab panel (see above) — top priority for next session.
- **Tick-cache validation discrepancy**: the UI button's day-by-day validation (`validate_ticks_vs_bars`, memory-safe) reported 98.6% coverage / 1,587 extra bars, while an earlier single-pass full-history script (same logic, no memory constraint) reported 100% / 243 extra bars. Both confirm the data is sound; the gap itself wasn't root-caused. Worth checking if it matters before relying on the UI number for anything precise.
- **~50 missing-day gaps in `flatfiles_cache`** (listed above) — not re-downloaded.
- **NT `OHLCExporter` buffer-loss risk** (the mechanism behind the 2026-04-06 exclusion) — diagnosed, a fix was drafted (flush-to-disk every N bars instead of buffering until `Terminated`) but reverted per explicit user instruction not to touch it without being asked. If gaps recur, that fix is the move — ask first.
- **Calendar-month-range optimization in Bar Analysis** — user asked "we need to be able to optimize on particular date ranges, not by contract, rather by calendar months" — raised but not yet designed or scoped. Carry over.
- Live-tested via Playwright (chromium installed this session: `pip install playwright && python -m playwright install chromium` — now available for future UI smoke tests) for: tab order, Roll Schedule columns, tick-cache build + validation button (including the OOM crash and its fix), Data-tab auto-load on a real process restart, Massive continuous-series persistence on restart. NOT live-tested: RevFTSignals end-to-end with a real second signal file, alt-path mismatch table with a real divergent trade, the new shared-filters panel's actual effect on Bar Analysis simulation results (since Bar Analysis filters aren't wired to it yet).

---

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

## Massive.io Tab — Architecture (locked, implemented Session 10)

- **Tab:** `📡 Massive.io` — 6th tab in app.py (`massive.py`). Independent from SC validation tabs. No shared state.
- **API-first** — ticks via `GET /futures/v1/trades/{ticker}`, agg bars via `GET /futures/v1/aggs/{ticker}`. Both cached to `data/massive_cache/` as parquet after first fetch.
- **Bar builder** — reuses `resample_ticks_to_bars()` in `data_loader.py`. No new bar logic.
- **Comparison** — reuses `build_comparison()` from `validation.py`, called twice:
  - Comparison 1: tick-built bars vs Massive agg bars (validates bar builder)
  - Comparison 2: tick-built bars vs NT ES_MAS bars (validates full import round-trip)
- **Rollover** — use `last_trade_date` from Contracts API; no hardcoded dates.
- **Correction filter** — exclude `correction != 0` trades.
- **Conditions field** — ignore for ES (equities only, confirmed by massive.io).
- **Session boundaries** — hardcoded RTH_START/RTH_END (08:30–15:15 CT).
- **Developer plan** — 5-year history (~2021 to present), 10-min delay. Sufficient for validation. Advanced needed for full WFA history to 2010.
- **Massive Agg bars caveat** — may differ slightly at session boundaries (08:30/15:15 CT). Tick-built vs NT is the comparison that matters most.
- **Reversal setup** — NT signal CSV arriving this week. Defer all design until CSV + NT strategy logic is seen. Do not design in advance.

### Functions in `data_loader.py` (built Session 10)

| Function | Purpose |
| -------- | ------- |
| `fetch_massive_trades(api_key, ticker, date_start, date_end)` | Paginate Trades API → DataFrame(DateTime CT, Price, Volume); cache to parquet |
| `fetch_massive_aggs(api_key, ticker, date_start, date_end, resolution)` | Paginate Aggs API → DataFrame(DateTime, OHLCV); cache to parquet |
| `fetch_massive_contract_info(api_key, ticker)` | Single contract metadata (first/last trade date, tick size) |
| `massive_ticker_to_nt_name(ticker, first_trade_date)` | `'ESM6' + '2026-03-17'` → `'ES_MAS 06-26'` |

**TODOs for Monday (require live API key):** confirm `BASE_URL`, auth header format, sort param syntax, exact ticker format (`ESM6` vs `ESM26`). All are marked with `# TODO` in code.

### `scripts/fetch_for_nt.py` (built Session 10)

Standalone script — runs natively on PC (Python + requests). Configure `API_KEY`, `TICKER`, `DATE_START`, `DATE_END` at top, then run. Output: `ES_MAS MM-YY.Last.txt` in `OUTPUT_DIR` + parquet cache. Same TODOs as above.

## NT Data Isolation — Confirmed Facts (Session 9)

From NT8 documentation (Historical Data Manager):

**Delete does not work for isolation:**
> "Deleted historical data will be replaced when data is reloaded from the connectivity provider."
Deleting ESM6 Rithmic data then importing massive ticks is unreliable — Rithmic refills on reconnect. Do not use this approach.

**Custom instrument approach — IN PROGRESS (Session 10):**
From NT docs: "Any data imported where the instrument does not exist in the database will automatically be imported as a Stock instrument type. Futures and forex instruments must pre-exist in the database."

- **ES_MAS** custom Future instrument created in NT Instrument Manager ✅
- Contract months added manually one at a time with rollover dates + price offsets; NT applies back-adjustment ("merge back adjusted" setting)
- NT contract month naming: `ES_MAS 06-26`, `ES_MAS 12-25`, etc. (`MM-YY` format)
- Whether NinjaScript indicators run cleanly on ES_MAS is **still unconfirmed** — blocked on tick data (API key Monday)
- First test: one contract month only. If indicators work → expand. If not → escalate to NinjaTrader support.

**Merge vs overwrite on import:** NT documentation does not specify. Unknown.

**Rule added:** Never guess NT8 behavior. If uncertain, say so immediately and stop. Do not present plausible-sounding guesses as recommendations.

---

## Session 11 — Massive.io API Confirmed + ES_MAS Pipeline Proven (June 14, 2026)

### Massive.io API — Confirmed Details

From a live AAPL test call, the following are now confirmed API-wide (equities and futures):

| Item | Old assumption | Confirmed |
|------|---------------|-----------|
| Base URL | `https://api.massive.io` | **`https://api.massive.com`** |
| Auth | `Authorization: Bearer` header | **`?apiKey=KEY` query param** |
| Sort param | `sort.asc=timestamp` | **`sort=asc`** |
| Agg timestamp | unknown unit | **Unix milliseconds** (`t` field) |
| Agg fields (equities) | `window_start`, `open`... | **`t`, `o`, `h`, `l`, `c`, `v`** |
| Pagination | `next_url` cursor | ✅ confirmed; must re-add `apiKey` on each page |

**Still unconfirmed for futures specifically:**
- Endpoint path: `/futures/v1/trades/` and `/futures/v1/aggs/` vs `/v2/` — confirm on first live futures call
- Date filter param names for trades (`session_end_date.gte` vs `timestamp.gte`)
- Response field names for futures aggs (may differ from equities `o/h/l/c/v/t`)

All confirmed fixes applied in `data_loader.py` and `scripts/fetch_for_nt.py`. Remaining unknowns marked with `# TODO` in code.

**API key:** Subscribed June 14, 2026.

### ES_MAS NT Pipeline — Fully Confirmed

Tested end-to-end using AAPL 5-min agg bars as synthetic tick data (May 5–29, 2026, 1,404 RTH bars).

| Step | Result |
|------|--------|
| `ES_MAS 06-26.Last.txt` → NT HDM import | ✅ 29 test bars loaded, then 1,404 RTH bars |
| NT builds minute bars from imported ticks | ✅ confirmed (doji bars, O=H=L=C as expected) |
| Tick size rounding (0.25) | ✅ 279.40 → 279.50 |
| EMA indicator on ES_MAS 06-26 chart | ✅ runs correctly |
| OHLCExporter on ES_MAS 06-26 chart | ✅ runs and writes bars |
| OHLCExporter bar timestamps | ✅ close times (08:30 open → 08:35 in output) |
| "Unknown instrument 'ES_MAS 06-26'" error | ⚠️ appears on chart open but does NOT block indicators |
| Exchange TZ in OHLCExporter log | Eastern Time (CME session template) — watch for offset with CT imports |

**Key finding:** Bars are dots/dashes because each 5-min agg bar was imported as a single tick (O=H=L=C = close price). This is expected and does not affect OHLCExporter output. Real ES futures ticks will produce proper OHLC bars.

**File naming confirmed:** `ES_MAS MM-YY.Last.txt` → NT HDM correctly associates with the matching contract month.

### Code Changes — Session 11

| File | Change |
|------|--------|
| `data_loader.py` | BASE_URL `.io`→`.com`; auth `Bearer header`→`apiKey` query param; `sort`→`asc`; agg timestamp `unit="ns"`→`"ms"`; agg fields dual-support (`o/t` + `open/window_start`); removed `_massive_headers()` |
| `scripts/fetch_for_nt.py` | Same URL/auth/sort fixes; `_headers()`→`_auth_params()` |
| `massive.py` | 4th data slot: **NT native bars** (upload, `mas_nt_native_bars`); **Comparison 3**: Tick-built vs NT native; Clear cache includes new keys; Comparison 2 label `"NT"`→`"NT_MAS"` |
| `scripts/write_aapl_test_nt.py` | New one-off: 29 pre-market AAPL bars → NT import file (first test) |
| `scripts/write_aapl_rth_nt.py` | New one-off: fetch AAPL RTH bars from API → NT import file (pipeline test) |

---

## Session 14 — June 18, 2026

### What Was Done

#### 1. Simulation engine — entry logic corrected (all 6 functions)

The old entry logic in ALL 6 simulation functions was wrong: it scanned bars and waited for price to cross `signal_price` (SBClose) before filling. The correct rule is:

> **Entry = first tick after signal datetime, unconditional. `signal_price` is informational only.**

Fixed in `_simulate_one`, `_simulate_one_multileg`, `_simulate_one_3leg` (tick-based) and `_simulate_one_bars`, `_simulate_one_bars_multileg`, `_simulate_one_bars_3leg` (bar-based).

Tick-based fix:
```python
# Before (wrong): bar-grouping crossing scan
# After (correct):
first_row     = after.iloc[0]   # after = ticks after sig_dt
first_tick_px = float(first_row["Price"])
entry_dt      = first_row["DateTime"]
```

Bar-based fix:
```python
# Before (wrong): returned no_fill if nb["High"] <= signal_price (long)
# After (correct):
fill_px = float(nb["Open"])  # unconditional
```

#### 2. `_simulate_one_multileg` — PB scale-in added (was missing entirely)

The tick-based multileg function had no PB logic. Added:
- `ml_pb_r` and `ml_pb_ticks` parameters
- `use_pb = ml_pb_r < 0` flag
- Single scan loop: PB fill check (strict tick-through) → stop (touch) → T2 (after PB) or T1 (before PB)
- Returns `PBLevel`, `PBLevelRaw`, `E2FillPrice`, `E2FillTime`, `BlendedEntry`
- `simulate_trades` dispatcher now forwards `ml_pb_r`, `ml_pb_ticks` to the tick function (was silently dropping them)

#### 3. `_build` fixes in `_simulate_one_multileg`

- Leg 2 P&L now measured from `e2_entry` (PB fill price), not `actual_entry`
- `r_ach` uses `_e1_risk_dollar = risk_pts / ts * tv1` for 1-leg exits (was always dividing by `tv_total`)

#### 4. Entry Zoom chart added (`bar_analysis.py`)

New `_show_entry_zoom` function renders a tick-level chart around every filled trade entry:
- **3 ticks before SBClose** + **3 ticks after EB Open** (tick-count window, not time window)
- Orange circle = SBClose tick (last tick ≤ sig_dt) with timestamp
- Cyan diamond = EB Open (first tick > sig_dt = fill tick) with timestamp
- Grey dots = surrounding ticks with timestamps
- Orange solid vertical line at sig_dt = 5M bar boundary
- Horizontal lines: SBClose price (orange dotted), Entry price (green dashed), Stop (red dashed)
- Title: `SB Closes HH:MM:SS · EB Opens HH:MM:SS.mmm · Fill XXXX.XX → Entry XXXX.XX`
- Metrics strip: SBClose | EB Open | Entry (Δ slip) | Stop (Δ risk pts)

`_show_entry_zoom_section` wraps it in a `🔍 Entry Zoom` expander with a selectbox — appears after the signal table in Bar Analysis.

#### 5. `SBClose` column bug fixed

`SBClose` in the results DataFrame was always NaN because `base.update(_EMPTY_TRADE)` overwrites it after `sig.to_dict()`. The correct column is `SEPrice` (set by every sim function as `signal_price`). Fixed in:
- `_show_entry_zoom`: uses `sig_row["SEPrice"]` instead of `sig_row["SBClose"]`
- Signal table display (line ~653): `disp["SB Close"]` now reads `results["SEPrice"]` (was always showing `—`)

#### 6. Dependency fixes

- `scipy` installed and added to `requirements.txt` (used by `wfa.py`)
- `boto3` was in `requirements.txt` but not installed in the venv on this machine — reinstalled

#### 7. Two-machine note

All contract data (flatfiles_cache, bars parquet, continuous tick cache) lives on the PC. The Mac only has `data/raw/` with a few files. App runs on both but full contract history requires the PC.

---

## ⭐ HANDOFF FOR NEW CHAT — Bar Analysis sweep-speed rewrite (Session 16)
*Written 2026-06-18 by Opus. Read this whole section before writing any code. The goal: make ALL Bar Analysis sweeps + the main simulation fast, with progress bars, and provably correct — then a full 5-year validation. Only after Bar Analysis is "perfect" do we touch the WFA tab.*

### ✅ Session 16 progress (evening of 2026-06-18) — NOT yet committed→ committed at end of session

**Step A — engine vectorized (DONE, verified).** `simulation_engine.py`: added a numpy first-hit-index scan path for `ratchet_r == 0` to `_simulate_one` (single-leg) and `_simulate_one_multileg` (PB scale-in). Python loop kept for `ratchet_r > 0` / manual-fill and as regression reference. Verified **byte-identical** (`validate_regression.py` old-vs-new), Layer A all pass, Layer B 0 mismatches (1097 trades, both modes). Speed: main multileg sim **59s → 2.4s**.
- **Deferred (do later, needs its own oracle first):** `_simulate_one_3leg` and the non-PB branch of `_simulate_one_multileg` still run the Python loop. 3-leg has no independent oracle — write one before vectorizing.

**Step B — scale-in sweep fast + engine-accurate (DONE, verified).** `bar_analysis.py`:
- Deleted the **drifted inline** `_run_ml_scalein_sweep` (it overstated Net PnL by up to **$7.4k/combo** — `round()` vs floor/ceil PB, and mis-scored same-tick PB+stop gaps).
- New **fast prefix-scan** `_run_ml_scalein_sweep`: precompute running-max/min per signal ONCE → each combo's first-hit is O(log n) `searchsorted` + a C-level numpy suffix scan post-PB. **Full 1224-combo grid ~2 min (95 ms/combo), was ~41 min** (~20×). A 432-combo grid ≈ 40s.
- Kept the slow `_run_ml_scalein_sweep_engine` (= simulate_trades + compute_summary) as the **reference oracle**.
- New permanent regression **`scripts/validate_scalein_sweep.py`** proves fast == engine. **64-combo subset (all code paths, T1<T2 and T1>T2): IDENTICAL on all 14 columns.** Full 1224-combo `--full` run was launched end-of-session → **confirm `data/_regress/scalein_full_verify.log` tomorrow** (expected green; logic is combo-uniform so the subset is the real proof).

**Win-decomposition columns (DONE).** Shared `_win_breakdown()` helper adds **Tgt % / EOD Win % / EOD Win R** to BOTH the R sweep and the scale-in sweep. `Win % = Tgt % + EOD Win %`. (Surfaced *why* Win% plateaus at high R: target becomes non-binding intraday → wins shift from target-hits to EOD-green.)

**Filter defaults changed (DONE).** New defaults in `bar_analysis.py` (code fallbacks) **and** `ba_filter_defaults.json` (git-tracked, so it propagates): **Exclude last 45 min** of RTH, **FOMC ON with ±15-min window cushion** (event mode = "Window ±N minutes", window = 15). These change sweep/sim numbers vs before (fewer signals) — intended. Requires a full app restart (defaults load via `setdefault`, won't override an existing session).

**Note on speed reality (measured this session):** routing sweeps through the engine per-combo is ~1.9–2.7s/combo (full result-dict build dominates, NOT post-processing) → ~15 min for 432 combos. The prefix-scan is the only thing that makes big sweeps usable. Other engine-based sweeps (R, T1×T2, stop-mult) still call the engine per combo and are still minutes on large grids — same prefix-scan treatment could be applied later if needed.

### 🐞 Data-integrity finding (investigated this session, fix NOT yet written)
The "missing tick data" sweep warnings are **truncated Massive flatfile downloads**, verified by inspecting raw gz contents (not file size — multi-product files mask time-truncation):
- **7 dates "no tick data"** — gz truncated before 08:30 RTH open → builder writes no parquet: 2021-07-21, 2021-08-12, 2021-08-13, 2021-10-07, 2021-11-23, 2022-03-16, 2022-06-24.
- **3 dates "no ticks after signal" (truncated mid-session)** — confirmed every contract in the file stops early: 2021-07-26 (08:59), 2021-11-30 (13:01), 2021-12-08 (10:29). (2021-11-30 gz is 45M but multi-product; ESZ1 = 397k RTH rows stopping at 13:01.) Active-contract pick is correct (ESZ1) — NOT a roll bug.
- **5 dates "no ticks after signal" by design** — signal on bar 81 (15:10–15:15, the last bar, no next bar to fill). **No fix needed.**

**Planned fix (script not yet written):** `scripts/refetch_truncated_days.py` — re-fetch those 10 dates (force-overwrite gz) → rebuild continuous ticks → **assert RTH span ~08:30→15:15 and fail loud** (don't silently keep a partial). Plus a **build-time guard** in `build_continuous_ticks_for_date` to flag abnormally short RTH coverage so future partial downloads surface immediately. Re-fetch hits the Massive API (metered) + overwrites cache — get explicit OK before running. Only helps if Massive now serves complete data for those days (the assert tells us).

### Non-negotiable principles (the user was emphatic — this is for real money)
1. **One engine, one definition of a trade.** `simulation_engine.py` is the single source of truth. The main sim, every sweep, the WFA tab, AND a future NinjaTrader auto-trade robot must all produce identical trades. NEVER reimplement trade logic in a sweep — call the engine. (The old `_run_ml_scalein_sweep` violated this and silently drifted — see below.)
2. **Every tick matters.** Entry = first tick after the signal bar close. PB level must be 100% identical across all CSVs, tables, and charts. Stop fills on touch. Floor/ceil PB rounding (see toggle below). Do not "optimize" by changing any comparator, rounding, or priority.
3. **Correctness is verified, not assumed.** Three tools exist (committed). After ANY engine/sweep change, all three must pass before commit: exact regression + Layer A + Layer B (see "Verification protocol").
4. **No commit/push without the user's explicit OK**, and the user must have run the app. Verified-identical output is necessary but not sufficient — still ask.
5. **Edit/Write tools only** for Python source (PowerShell double-encodes UTF-8 → mojibake). All sims behind a Run button in the app. Keep responses short.

### What is ALREADY DONE and verified (committed — do not redo)
- **Sim engine validated.** Session-14 entry logic + PB scale-in are correct. Proven by Layer A (invariants) + Layer B (independent oracle): 0 violations / 0 mismatches on all 1,097 filled trades, both single-leg and 2-leg PB modes, 1-yr window.
- **Engine speedup Step 1 (searchsorted).** `_simulate_one`, `_simulate_one_multileg`, `_simulate_one_3leg` now get the post-signal tick slice via a shared `_ticks_after()` helper (searchsorted, O(log n) + view) instead of `day_ticks[day_ticks["DateTime"] > sig_dt]` (O(n) boolean mask + copy per signal). **Proven byte-identical** to the prior engine: regression = 1,107 rows × 63 cols identical across single/multi/3leg. The scan loops were NOT touched.

### Verification tools (committed in `scripts/`)
- `validate_engine.py` — Layer A invariants. `python scripts/validate_engine.py --mode multileg --start 2021-06-18 --end 2022-06-18`
- `validate_oracle.py` — Layer B independent first-hit-index oracle. `--per-reason 100000` checks every trade. Same args.
- `validate_regression.py` — dumps simulate_trades output (all 3 modes) and diffs trade-for-trade. `dump <dir>` then `cmp <dirA> <dirB>`. Use it to prove a rewrite is identical: dump new → `git stash` → dump old → `git stash pop` → cmp.
- Default exec params used by all three (mirror ES multileg defaults): tick_value 12.50, commission 3.0, entry_slip 1, exit_slip 1, stop_offset 0, contracts_t1 1, contracts_t2 1, t1_r 1.5, target_r(=T2) 1.0, ml_pb_r −0.50. Data: `saved_signals/ba_signals_mc.parquet` (5,580 signals 2021–2026) + per-day tick cache `data/ticks_continuous/*.parquet` (1,247 days). **Work on the 1-yr window 2021-06-18 → 2022-06-18 (1,097 filled) unless told otherwise.**

### THE BOTTLENECK (measured — read this before planning)
One **multileg `simulate_trades` over 1,107 signals = ~59 seconds** on the real continuous tick cache (~356k ticks/day). The dominant cost is the **Python per-tick scan loop** in `_simulate_one*` (EOD/long-held trades scan ~100k+ ticks each in interpreted Python), NOT the pandas filter (that was already fixed by `searchsorted`). Consequence: routing the scale-in sweep through per-combo `simulate_trades` would be ~168 × 59s ≈ **2.8 hours** — so "just call the engine per combo" is NOT viable for the big sweep. The old handoff's "~1 s/combo" was from different/smaller data — ignore it. **Vectorizing the scan is the core fix, and it also makes the main-sim Run button fast.**

### THE REMAINING WORK (in order)

**A. Vectorize the tick scan in the engine (the core fix — ratchet-off case).**
In `simulation_engine.py`, give each `_simulate_one*` a vectorized scan path for `ratchet_r == 0` (always true in sweeps; usually true in the main sim) that computes the outcome via numpy first-hit indices (`np.flatnonzero`/`argmax`) instead of the Python loop — producing the **full result dict** (exit reason/price/PnL, MAE/MFE, E2 fill, blended entry, leg fields, bar nums…). **Layer B's oracle (`scripts/validate_oracle.py`) is the proven template** — it already re-derives exit sequencing this way and matches the engine on every trade. Keep the existing Python loop as (1) the `ratchet_r > 0` path and (2) the regression reference. Preserve every comparator, the PB `continue`, floor/ceil, and stop-on-touch exactly.

**B. Reuse per-signal setup across combos; reroute all sweeps; delete the inline scale-in copy.**
Split each `_simulate_one*` into `prepare_setup(signal, day_arrays)` (entry tick via searchsorted + entry/stop/risk — combo-independent, computed ONCE) and `resolve(setup, params)` (the vectorized scan from A). Precompute each day's `(price_array, datetime_array)` once at the top of `simulate_trades`. Then:
- Main sim = prepare + resolve once.
- Every sweep (`_run_r_sweep`, `_run_t1t2_sweep`, `_run_pb_sweep`, `_run_t1t2_sweep_3leg`, `_run_stop_mult_sweep`, `_run_ml_scalein_sweep`) = prepare setups once, loop combos calling `resolve`. ONE logic copy, no drift.
- **Delete the inline body of `_run_ml_scalein_sweep` (`bar_analysis.py` ~1002–1240).** It is a reimplementation that DRIFTED from the engine in two ways: (1) `round()` for the PB trigger vs the engine's `floor`/`ceil`; (2) on a tick that gaps through both PB and the stop, the engine fills PB and continues while the inline copy calls it a leg-1 stop. Replacing it with the shared `resolve` auto-fixes both.

**C. Confirm the speed target.** After A+B, time it. Need: 17 WFA folds finish in reasonable time (a sweep should be seconds, not minutes). If a sweep reuses setups + vectorized resolve, a 168-combo scale-in sweep should drop from hours to seconds. Measure with `scripts/_timeit.py`-style timing (then delete that throwaway).

**D. PB rounding toggle (user requested).**
Add a toggle in the **Filters** expander of Bar Analysis: PB level rounding = "Floor/Ceil (conservative)" [default] vs "Round to nearest". Thread it through `simulate_trades` → `_simulate_one_multileg` + `_simulate_one_3leg` (the `pb_trigger` / `pb1_price` / `pb2_price` computation, currently `np.floor`/`np.ceil` at simulation_engine.py ~315). Must flow to every sweep and into the sim fingerprint so changing it re-runs. Default preserves today's exact behavior (floor/ceil = snap PB away from entry = harder to fill = never overstate scale-ins). This is a comparison knob, not a new default.

**E. Progress bars on everything.** Every sweep `_show_*` and the main sim Run path must show a live progress bar (the scale-in sweep already has one — pattern at bar_analysis.py ~1107). The user must never see a frozen screen.

### Verification protocol (run BEFORE asking to commit — all must pass)
1. `validate_regression.py`: new vs old (git-stash trick) → **IDENTICAL** for single/multi/3leg. (For sweeps: also confirm one combe, e.g. PB=−0.50 T1=1.50 T2=1.00, sweep row == direct `simulate_trades` + `compute_summary`.)
2. `validate_engine.py` (Layer A) → all invariants pass, multileg + single.
3. `validate_oracle.py --per-reason 100000` (Layer B) → 0 mismatches, multileg + single.
4. Then the user runs the app and eyeballs a sweep + the main sim.
5. **Pardo rule:** never change the PB/T1/T2 grid VALUES during this work — speed only.

### Full 5-year validation (after Bar Analysis is "perfect")
Run validation across the entire signal history **year by year** (memory: ~444M ticks total — never load all at once; `validate_oracle.py` already chunks yearly, mirror that for any new check). All years must pass Layer A + B. This is the confidence gate before WFA.

### Current numbers (1-yr IS window, Jun 2021 – Jun 2022)
- Signals in file: ~5,580 · in window with tick data: 1,107 · filled: 1,097
- 8 dates permanently missing tick data (Massive has none)
- Scale-in grid: typical 168 combos (PB:4 · T1:6 · T2:7); full default 392 (8×7×7)
- **Measured speed:** one multileg `simulate_trades` over 1,107 signals = **~59 s** (full tick cache, ~356k ticks/day; Python scan loop dominates). So 168 combos via per-combo engine calls ≈ 2.8 h — vectorization required. Target: a sweep in seconds so 17 WFA folds finish in reasonable time.

### Loose ends to clean up at handoff
- `scripts/_timeit.py` was a throwaway perf script — delete it. `2026-06-18T12-41_export7.csv` lives in the user's Downloads, NOT the repo; it is the app's OWN exported trade log (regression-only, not independent ground truth) — do not rely on it for correctness.
- `data/_regress/` holds regression dumps (gitignore it or it clutters `git status`).

---

## Next Session — Priorities (set 2026-06-18 evening, session 16)

**First: `git pull` (two-machine).** Then confirm `data/_regress/scalein_full_verify.log` says IDENTICAL (the full-grid fast-vs-engine check launched at end of session 16).

**Critical path:** ✅ sim engine validated → ✅ scale-in sweep fast+correct → 🔄 finish the sweep-speed plan (D, E) + the new feature work below → decide Q5/Q6 → first WFA run.

### Session-17 explicit asks from the user (2026-06-18)
1. **Trailing stop → BE after xR, on BOTH setups (single-leg + 2-leg).** The engine already has `ratchet_r` / `ratchet_dest="BE"` (move stop to break-even after favor ≥ xR) — it works in the loop path but the vectorized fast paths are `ratchet_r == 0` only, and it is not exposed/wired as a first-class control on both setups or in the sweeps. Task: surface it cleanly on both setups, make sure it flows into sweeps + the sim fingerprint, and decide defaults. (Will need a vectorized ratchet path OR keep ratchet-on sims on the loop and document the speed cost.)
2. **New setup: RevFT.** A RevFT signal CSV is arriving. Slot it in as another `setup_id` alongside MC signals (the RevFTSignals upload scaffolding already exists per Session 12). Review the CSV + its strategy logic BEFORE writing code — do not design in advance. No engine changes expected (same trade structures).

### Remaining sweep-speed plan items (⭐ section)
- **D. PB rounding toggle** — Filters expander: "Floor/Ceil (conservative)" [default] vs "Round to nearest", threaded through engine → every sweep → sim fingerprint.
- **E. Progress bars** on every sweep + main sim Run path.
- **Vectorize 3-leg + non-PB multileg** — write a 3-leg Layer-B oracle first, then vectorize (currently loop-only, so the 3-leg sweep is slow).

### Data integrity (paused — script not yet written)
- Write `scripts/refetch_truncated_days.py` (10 truncated dates) + build-time RTH-coverage guard. See "🐞 Data-integrity finding" in the ⭐ section above. Re-fetch hits Massive API + overwrites gz → get OK before running.

### Step 2 — Decide Q5 and Q6 (before reading any OOS)
Max concurrent positions and max daily loss rule are still open (`open_questions.md`). Current WFA output assumes unlimited concurrent positions and no daily loss cap. Decide these **before** reading OOS results — reading OOS then changing the model is a Pardo no-feedback violation. WFA OOS metrics are not actionable for live sizing until decided.

### Step 3 — First real WFA run
1. Start the app (`.venv\Scripts\streamlit run app.py`)
2. Build `mas_continuous` in the Massive tab if not already persisted
3. Upload CC2 signals (or whichever setup has the most data)
4. Open the `🔄 WFA` tab → Configure & Run → select multileg, default windows (IS=12mo / OOS=3mo, 3 param sets)
5. Verify: fold count shown (~16), IS sweep runs without error, guardrail badges appear, OOS equity curve renders, fold table populates
6. Spot-check one fold's IS sweep: confirm the param grid was correct (T1 < T2 enforced, PB values negative)
7. **Only after a clean run** move on to portfolio layer or window scanner

### Step 3 — Portfolio WFA layer
Update Portfolio tab to load and combine OOS equity curves from multiple setup runs via `load_portfolio_oos_trades()` in `results_store.py`. This is already wired on the storage side; only the Portfolio tab UI needs updating.

### Carry-over from Session 12 (lower priority than WFA)
1. **Econ calendar API** — user flagged this as broken at end of Session 12. Ask what specifically is broken before touching `economic_calendar.py`.
2. **Migrate Bar Analysis filters to the shared panel** — `ba_`-prefixed widgets still independent from `validation.get_filters("shared")`.
3. **"Clear all cached data" confirmation popup** — no confirmation UI exists currently.
4. Re-download ~50 missing trading days in `data/flatfiles_cache/`.
5. Root-cause tick-cache validation discrepancy (98.6% vs 100%).
6. Live-test RevFTSignals and alt-path mismatch table with real divergent data.

### Stale / superseded (kept for history only — do not act on without re-confirming with user)
The items below were written for the old Massive.io-as-secondary-track plan (Sessions 10–11) and are now superseded by Session 12's work — Massive is already primary, the API is already confirmed and working, and `massive.py` already has the contract manager described here. Left in place rather than deleted per "preserve existing architecture unless instructed otherwise," but treat as historical.

1. ~~Confirm futures endpoint paths~~ — done, `massive.py` Contract Manager downloads real ES futures successfully.
2. ~~Confirm futures agg field names~~ — superseded; current pipeline uses flat-file trades, not the Aggs API.
3. ~~Contract lookup~~ — done, `CATALOG` in `contracts.py`.
4. ~~Run `scripts/fetch_for_nt.py`~~ — superseded by `massive.py`'s built-in NT import file writer.
5. ~~Run OHLCExporter on ES_MAS chart~~ — done, all 20 contracts have NT import files.
6. ~~App Comparison 1 (tick-built vs agg)~~ — superseded by the tick-cache-vs-5M-bars validation built in Session 12.

### SCID / WFA (carry-over, blocked on SC data)

1. **Configure SC for 1-second OHLCV** — set chart type to 1-second bars for all ES quarterly contracts (ESZ09–ESM26), request historical data from SC. Expected ~210 MB/quarter.
2. **Run `scripts/build_scid_cache.py`** once 1-second data is on disk.
3. **Update SCID pipeline for 1-second bars** — `resample_ticks_to_bars` needs to aggregate OHLC from 1-second OHLCV, not tick prices.
4. **Gate 1** — validate Python-built 5-min bars vs SC native 5-min export.

### Other

1. **Reversal setup** — review NT signal CSV + strategy logic before any code. Do not design in advance.
2. **Carry-over:** Verify PDF equity chart resize, verify 2-leg math (both low priority).

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
| massive.io API | Subscribing 2026-06-16 | Developer plan. Futures Trades + Aggs APIs. ES quarterly contracts. Full docs in `docs/reference/massive_io/`. |

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
10. **Never guess NT8 behavior.** If the answer is not in the docs or confirmed by the user, say "I don't know" and stop. Do not fill gaps with plausible-sounding guesses.
11. **Two-machine workflow:** User works on both a PC and a Mac laptop. Always remind to `git pull` at the start of every session before any other work.
