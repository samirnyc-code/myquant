# Data Sources
**Status:** Architecture — Living  
**Last Updated:** June 9, 2026  
**Rule:** This is the only file that defines data sources. All other docs reference this file, never duplicate it.

---

## Primary Tick Data — Sierra Charts (Delani)

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
| Plan | Futures Developer (subscribing 2026-06-16) |
| Instrument | ES quarterly contracts: ESH, ESM, ESU, ESZ |
| Ticker format | `ESH6`, `ESM6`, `ESU6`, `ESZ6` (product code + month + 2-digit year) |
| Delivery | REST API — `GET /futures/v1/trades/{ticker}` |
| Timestamp | Nanosecond Unix in API response; millisecond float in flat file CSV |
| Fields | timestamp, ticker, price, size, sequence_number, correction, exchange, session_end_date |
| Coverage | 5 years (Developer plan); full history to 2017-04-03 (Advanced/Business) |
| Status | Subscribing 2026-06-16 |
| Purpose | Independent parallel validation track (Track 4) — completely separate from SC gates |

**Plan limits:** Developer = 10-min delay, 5-year history. Sufficient for bar validation. Advanced needed for full WFA history back to 2010.

**API docs:** `docs/reference/massive_io/` — full endpoint reference for Contracts, Schedules, Trades, Aggs, and supporting endpoints.

**Key fields for bar building:**
- `correction != 0` → exclude (cancelled/corrected trades)
- `conditions` → ignore for ES (equities only)
- `session_end_date` → shared key across all massive.io APIs; CME day ends 17:00 CT
- Rollover boundaries → from `last_trade_date` in Contracts API (no hardcoded dates)

**Three-way validation (Track 4):**
1. Ticks → App bar builder (`resample_ticks_to_bars`) → App 5M bars
2. Ticks → NT import format → NT builds 5M bars + MCSignals CSV
3. Aggs API (`resolution=5min`) → massive.io reference bars
All three must match.

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
