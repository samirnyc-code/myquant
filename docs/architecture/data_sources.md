# Data Sources
**Status:** Architecture — Living  
**Last Updated:** June 16, 2026 (Session 12)  
**Rule:** This is the only file that defines data sources. All other docs reference this file, never duplicate it.

---

## ⚠️ Session 12 update: Massive is now primary

As of June 16, 2026, **Massive is the primary and only active data source** feeding Bar Analysis. The Sierra Charts/SCID section below is paused (not deleted — kept for reference in case the path is revisited).

**Current pipeline, in order:**

1. **Flat-file ticks** (S3, `us_futures_cme/trades_v1/`) → downloaded per contract via the **📂 Massive** tab's Contract Manager, cached at `data/flatfiles_cache/{date}.csv.gz` (raw, all CME symbols, gzip CSV)
2. **Per-contract 5M bars** → built from the flat files, cached at `data/bars/{ticker}.parquet`
3. **Back-adjusted continuous 5M series** → `contracts.py: apply_back_adjustment()`, stitches all downloaded contracts using roll dates/offsets from `rolls.json` (committed to git — same schedule for every collaborator). Persisted to `data/bars/_continuous.parquet`, auto-loaded into `st.session_state["mas_continuous"]` on every app restart.
4. **Back-adjusted continuous tick series** → `massive.py: build_continuous_ticks_for_date()`, one small Parquet per trading day (front-month ticker only, RTH-filtered, offset baked into price), built from the same flat-file cache (no new downloads). Cached at `data/ticks_continuous/{date}.parquet`. As of Session 12: 1,220 days, ~445M ticks, validated 99.49% OHLC-exact match against the 5M bars (98.6–100% coverage depending on validation method — see handoff.md Known Gaps).
5. **NT `@ES` continuous upload** (Massive tab) → used **only** for matching/validation (the signal-bar-Close gate in Bar Analysis's alt-path mismatch check, and the Massive-vs-NT comparison panel). Never used for fills/exits. Persisted via the generic CSV-cache mechanism, prefix `"nt_cont"`.

**Key files:**

| File | Role |
|------|------|
| `contracts.py` | Contract catalog (`CATALOG`), roll schedule I/O (`rolls.json`), `apply_back_adjustment()`, `get_contract_windows()`, `get_active_contract()` |
| `massive.py` | Contract Manager UI, S3 download, bar building, continuous tick cache, NT @ES upload, the Massive-vs-NT comparison panel |
| `data_loader.py` | `filter_excluded_dates()` / manual exclusion registry (`excluded_dates.json`), `apply_data_slot()` (shared session-state funnel) |
| `bar_analysis.py` | Sources `bars` from `mas_continuous`, ticks lazily per-day from the continuous tick cache (only for dates with signals) |

**Manual exclusions:** `excluded_dates.json` (committed) — dates known to have bad data (feed gaps, capture artifacts) are dropped everywhere via `filter_excluded_dates()`. Currently seeded with `2026-04-06` (NT OHLCExporter captured only 1 stray tick all session — likely `IsSuspendedWhileInactive` suppressing updates while the chart tab was inactive).

**Filters:** a single shared filter panel (holidays, day-of-week, session boundaries, economic events) lives in the 🗂️ Data tab (`validation.render_filters("shared")`). The Massive comparison panel reads it read-only via `validation.get_filters("shared")`. Bar Analysis's own filter panel is **not yet migrated** to this shared instance — top priority for the next session.

See `docs/living/handoff.md` Session 12 section for the full list of bugs found/fixed this session (back-adjustment roll-date semantics, 5-min timestamp misalignment, OOM crash in tick validation, 403-vs-404 download handling, NT bars accidentally being the de-facto simulation source via dead `bar_source` code).

---

## Primary Tick Data — Sierra Charts (Delani) — PAUSED, not active

| Item | Detail |
|------|--------|
| Provider | Sierra Charts via Delani |
| Instrument | ES (E-mini S&P 500 futures) |
| Format | `.scid` binary files (Sierra Charts native tick format) |
| Data directory | `C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\` |
| Coverage | ESU23–ESZ25 — 12 quarterly contracts confirmed on disk |
| Session | RTH: 08:30–15:15 CT (confirmed from ESM6 tick data; applied as filter in loader) |
| Rollover | One `.scid` file per quarterly contract. Python loads multiple quarters and concatenates. No stitching needed — just select quarter range. |
| Status | ✅ Parser built and working |

### Confirmed Binary Format (`s_IntradayRecord`)

| Field | Offset | Type | Detail |
|-------|--------|------|--------|
| Header | 0 | 56 bytes | Fixed file header |
| `DateTime` | 0 | int64 | Microseconds since 1899-12-30 00:00:00 UTC |
| `Open` | 8 | float32 | |
| `High` | 12 | float32 | |
| `Low` | 16 | float32 | |
| `Close` | 20 | float32 | Last trade price |
| `NumTrades` | 24 | int32 | |
| `TotalVolume` | 28 | int32 | |
| `BidVolume` | 32 | int32 | |
| `AskVolume` | 36 | int32 | |
| Record size | — | 40 bytes | |

**Timestamp conversion:**
```python
SC_EPOCH = pd.Timestamp("1899-12-30")
dt_utc = SC_EPOCH + pd.to_timedelta(raw_microseconds, unit="us")
dt_ct  = dt_utc.tz_localize("UTC").tz_convert("America/Chicago").tz_localize(None)
```

**Parser location:** `data_loader.py` — `build_scid_quarter_map()`, `load_scid_ticks_chunked()`, `parse_scid_ticks_from_upload()`

**Parquet cache:** `SCID_DATA_DIR/_scid_cache/ticks.parquet` (snappy) + `meta.json`. Auto-loaded on app startup. Functions: `save_scid_cache()`, `load_scid_cache()`, `clear_scid_cache()`.

**Open question — bar timestamp direction:** It is not yet confirmed whether the SCID `DateTime` field represents bar **open** or bar **close** time. NT TXT exports use bar close time (bar 1 = 08:35 row). If SCID also uses close time, bar 1 ticks resample into the [08:35, 08:40) bin → displayed as bar 2. Fix would be to subtract 5 min before resampling. **Do not apply until verified.** See `open_questions.md`.

---

## Secondary Tick Data — Massive.io

| Item | Detail |
|------|--------|
| Provider | Massive.io |
| Plan | Futures Developer (subscribed 2026-06-14) |
| Instrument | ES quarterly contracts: ESH, ESM, ESU, ESZ |
| Ticker format | `ESH6`, `ESM6`, `ESU6`, `ESZ6` (single-digit year) |
| Delivery | REST API — `GET /futures/v1/trades/{ticker}` (path TBC — see below) |
| Coverage | 5 years (Developer plan); full history to 2017-04-03 (Advanced/Business) |
| Status | ✅ Pipeline coded + NT import confirmed working. Futures API endpoint paths pending first live call. |
| Purpose | Independent parallel validation track (Track 4) — completely separate from SC gates |

**Plan limits:** Developer = 10-min delay, 5-year history. Sufficient for bar validation. Advanced needed for full WFA history back to 2010.

**API docs:** `docs/reference/massive_io/` — full endpoint reference for Contracts, Schedules, Trades, Aggs, and supporting endpoints.

### Confirmed API Details (Session 11 — from AAPL test)

| Item | Value |
|------|-------|
| Base URL | `https://api.massive.com` |
| Auth | `?apiKey=KEY` query parameter — NOT a header |
| Sort | `sort=asc` |
| Pagination | `next_url` cursor; must re-add `apiKey` on each subsequent page |
| Agg timestamps | Unix **milliseconds** (`t` field) |
| Agg fields (equities) | `t`, `o`, `h`, `l`, `c`, `v`, `vw`, `n` |

**Still unconfirmed for futures (confirm on first live call):**
- Endpoint path: `/futures/v1/trades/{ticker}` vs `/v2/trades/ticker/{ticker}/...`
- Date filter param names for trades (`session_end_date.gte` vs `timestamp.gte`)
- Agg response field names for futures (may differ from equities `o/h/l/c/v/t`)

All confirmed fixes in `data_loader.py`. Remaining futures-specific unknowns marked `# TODO`.

**Key fields for bar building:**

- `correction != 0` → exclude (cancelled/corrected trades)
- `conditions` → ignore for ES (equities only)
- `session_end_date` → shared key across all massive.io APIs; CME day ends 17:00 CT
- Rollover boundaries → from `last_trade_date` in Contracts API (no hardcoded dates)

### NT Import Isolation — ES_MAS Custom Instrument (Confirmed Session 11)

Importing Massive ticks directly into NT's native ES instrument is not viable — Rithmic overwrites on reconnect. Solution: custom Future instrument `ES_MAS` in NT Instrument Manager. **Fully confirmed working** with AAPL test data (Session 11):

| Fact | Status |
|------|--------|
| `ES_MAS 06-26.Last.txt` → NT HDM import | ✅ Confirmed |
| File naming convention routes to correct contract month | ✅ Confirmed |
| NT builds minute bars from imported tick data | ✅ Confirmed |
| Tick size rounding (0.25) applied correctly | ✅ Confirmed |
| EMA indicator runs on ES_MAS | ✅ Confirmed |
| OHLCExporter runs on ES_MAS | ✅ Confirmed |
| OHLCExporter writes bar close timestamps | ✅ Confirmed (08:30 open → 08:35 in output) |
| "Unknown instrument" error on chart open | ⚠️ Appears but does NOT block indicators |
| Exchange TZ in OHLCExporter log | Eastern Time (CME session template) |
| NT back-adjustment on continuous chart | Unknown — test individual contract months, not continuous |

**Import settings (NT HDM):** Format = NinjaTrader (beginning of bar timestamp), Data Type = Last, Timezone = Central Time.

### Pipeline (Track 4)

- `scripts/fetch_for_nt.py` — fetch ticks → write `ES_MAS MM-YY.Last.txt` → import into NT
- `data_loader.py` — `fetch_massive_trades()`, `fetch_massive_aggs()`, `fetch_massive_contract_info()`, `massive_ticker_to_nt_name()`
- `massive.py` — `📡 Massive.io` tab in app (6th tab)
- Cache: `data/massive_cache/{ticker}_{start}_{end}_ticks.parquet` and `..._aggs_5min.parquet`

### Four-Way Validation (massive.py tab)

1. **Tick-built bars** — Massive ticks → `resample_ticks_to_bars()` → App 5M bars
2. **Massive agg bars** — Aggs API (`resolution=5min`) → reference bars
3. **NT ES_MAS bars** — ticks → `fetch_for_nt.py` → NT import → OHLCExporter
4. **NT native bars** — OHLCExporter on standard ESM6 (Rithmic) chart

Comparison 1 (Tick vs Agg) validates bar builder. Comparison 2 (Tick vs NT_MAS) validates full import round-trip. Comparison 3 (Tick vs NT_Native) cross-checks Massive data against Rithmic. All in `📡 Massive.io` tab.

---

## Live Trading Data — NT8 / Rithmic

| Item | Detail |
|------|--------|
| Platform | NinjaTrader 8 |
| Feed | Rithmic |
| Instrument | ES / MES |
| Available | 1 year of tick data on disk |
| Purpose | Cross-provider bar validation — compare NT8/Rithmic bars against Sierra bars |
| Status | Available now |

---

## Data Architecture

```
Sierra Charts scid files (primary research)
        |
        v
Python scid parser → 5M OHLCV bars (session-aware)
        |
        ├── Validate against SC bar export (bar_validation.md — Gate 1)
        |
        ├── Validate against NT8/Rithmic 5M bars (bar_validation.md — Gate 2)
        |
        v
Validated bars → Python Signal Detector → Python WFA Engine
        
        
Massive.io flat files (optional secondary)
        |
        v
Python parser → 5M OHLCV bars
        |
        v
Cross-provider analysis validation
(do WFA conclusions on Sierra data hold on Massive data?)
```

---

## Why Tick Data Differs Between Providers

Same underlying CME feed, different results. Sources of divergence:

1. **Timestamp granularity** — Sierra: microseconds. Massive: milliseconds. Same tick, potentially different bar boundary.
2. **Tick filtering** — each provider applies their own bad tick filter. A tick Sierra accepts, Massive or Rithmic may reject.
3. **Packet bundling** — CME sends ticks in UDP packets. Providers unbundle and timestamp differently.
4. **Rollover handling** — quarterly contract stitching logic differs per provider. Biggest source of multi-year divergence.
5. **Connection latency** — sub-millisecond differences in tick receipt change bar boundary assignment.

**Consequence:** OHLCV bars will be close but never identical across providers. 1-tick differences on boundary bars are expected and acceptable. Systematic bias is not. See `bar_validation.md` for tolerance thresholds.

**Solution:** Strategy robustness is the primary defense against feed variance. A strategy with strong WFE across 10+ years of Sierra data absorbs 1-tick bar differences on Rithmic. The bar validation gates confirm the feeds are compatible. They do not need to be identical.

---

## Open Questions

- [ ] **SCID bar timestamp direction** — does `DateTime` represent bar open or bar close? NT TXT uses close. If SCID uses close, bar numbering is off by 1 in the Streamlit app. Verify by comparing SCID tick first bar timestamp against a known NT bar. See `open_questions.md` Q14.
- [ ] SC session exact template — confirmed 08:30–15:15 CT from data, but not verified against SC session settings directly
- [ ] Massive.io — purchase decision deferred until Sierra sim is producing results

~~Exact Sierra Charts scid struct~~ ✅ Resolved June 9, 2026 (see format table above)  
~~SC rollover handling~~ ✅ Resolved June 9, 2026 — quarterly files, one per contract, loaded and concatenated by Python  
~~RTH session exact boundaries~~ ✅ Resolved June 3, 2026 — 08:30–15:15 CT confirmed from ESM6 tick data
