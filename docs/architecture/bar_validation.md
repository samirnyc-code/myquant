# Bar Validation Architecture
**Status:** Architecture — Living  
**Last Updated:** June 12, 2026  
**Supersedes:** `BarValidation_Architecture.md` (original June 1, 2026)

---

## Purpose

Before any simulation logic is built, prove that Python-built 5M bars from Sierra Charts tick data are accurate, and that Sierra Charts bars and NT8/Rithmic bars are compatible enough to trust that strategies validated on Sierra data will behave on Rithmic in live trading.

**This is a blocking prerequisite. No Python sim is built until both gates pass.**

---

## Three-Way Comparison

```
Sierra Charts scid tick data
        |
        v
Python Bar Builder ──────────────────────────────────────────┐
        |                                                     |
        v                                                     v
Python 5M bars                                    SC Export 5M bars
(our build from scid)               (SC built-in: Analysis → Export Chart Data)
        |                                                     |
        └──────────────────┬──────────────────────────────────┘
                           |
                    Gate 1: SC vs Python
                    "Does our bar builder match Sierra's own bars?"
                           |
                           v
                      PASS or FAIL
                           |
                    (only if Gate 1 passes)
                           |
NT8/Rithmic tick data      |
(1 year on disk)           |
        |                  |
        v                  |
Python Bar Builder         |
        |                  |
        v                  |
NT8/Rithmic 5M bars ───────┘
                           |
                    Gate 2: Sierra vs NT8/Rithmic
                    "Are research and trading environments compatible?"
                           |
                           v
                      PASS or FAIL
```

---

## Gate 1 — Sierra Charts vs Python Bar Builder

**Question:** Does our Python scid parser and bar builder produce the same bars as Sierra Charts?

**SC Export method:** Analysis → Export Chart Data → 5-Minute → RTH only → same date range as tick data → CSV

**Comparison logic:** Align both DataFrames on Timestamp (inner join). Per bar:

| Field | Tolerance | Flag if |
|-------|-----------|---------|
| Open | 0 ticks | Any diff |
| High | 1 tick (0.25) | > 1 tick |
| Low | 1 tick (0.25) | > 1 tick |
| Close | 0 ticks | Any diff |
| Volume | Some variance | Low priority |

**Pass thresholds:**

| Category | Threshold | Action if failed |
|----------|-----------|-----------------|
| O/C exact match | ≥ 99% | Fix session boundary logic or parser |
| H/L within 1 tick | ≥ 99% | Acceptable — tick boundary variance |
| H/L diff > 1 tick | < 1% | Flag and inspect individually |
| Systematic pattern in diffs | None | Fix bar builder before proceeding |

---

## Gate 2 — Sierra Charts vs NT8/Rithmic

**Question:** Are bars built from Sierra scid data and bars built from NT8/Rithmic tick data compatible enough to trust that WFA results on Sierra data will hold in live NT8 trading?

**NT8 data available:** 1 year of Rithmic tick data on disk.

**Method:** Build 5M bars from NT8 tick data using the same Python bar builder and session logic. Compare against Sierra bars for the overlapping period.

**Same tolerance thresholds as Gate 1.**

**What this proves:** If agreement is ≥ 99% within 1 tick, then:
- A strategy validated on Sierra data will produce the same signals on Rithmic with >99% agreement
- 1-tick bar differences on edge cases are within the noise of any robust strategy
- No Sierra Charts trading platform is needed — NT8 remains the execution environment

**What this does not prove:** Perfect signal replication. MC signal detection depends on bar structure. A 1-tick difference on a bar high can change whether a bar qualifies as an MC bar in edge cases. This is acceptable if strategy robustness is confirmed via WFA.

---

## Signal Agreement Test (After Gate 2)

After Gate 2 passes, run the signal detector on both Sierra bars and NT8/Rithmic bars for the overlapping 1-year period. Compare:

- Signal count per day
- Signal dates and times
- MC high/low at signal

**Pass threshold:** ≥ 98% signal agreement. Any lower, investigate which bars differ and whether those bars are on rollover dates or event days.

---

## Visual Output (all three gates)

### 1. Match Rate Summary
```
Gate 1 — SC vs Python:
  Open   ████████████████████ 99.8% exact
  High   ███████████████████░ 99.2% within 1 tick
  Low    ███████████████████░ 99.3% within 1 tick
  Close  ████████████████████ 99.7% exact

Gate 2 — Sierra vs NT8/Rithmic:
  [same layout]
```

### 2. Diff Distribution (Histogram per OHLC field)
- X-axis: diff in ticks
- Y-axis: bar count
- Expected: spike at 0, tiny tails at ±1

### 3. Timeline Plot (Flagged Bars)
- Grey: perfect match
- Yellow: ±1 tick
- Red: > ±1 tick
- Helps identify clustering around rollovers, holidays, events

### 4. Summary Table
```
Total bars compared:     12,450
Gate 1 — SC vs Python:
  Perfect match (OHLC):  12,301  (98.8%)
  H/L diff = 1 tick:        142  ( 1.1%)
  H/L diff > 1 tick:          7  ( 0.1%)  INVESTIGATE
Gate 2 — Sierra vs Rithmic:
  [same layout for overlapping period]
```

---

## Files

| File | Description |
|------|-------------|
| `bar_builder.py` | Reads scid and NT8 tick data, builds 5M OHLCV bars |
| `scid_parser.py` | Sierra Charts binary scid format parser |
| `sc_export_guide.md` | How to export 5M bars from Sierra Charts |
| `bar_validator.py` | Three-way comparison, generates validation report |
| `validation_report.html` | Visual output |

---

## Track 2 — Massive.io Three-Way Validation (independent from Track 1)

Added 2026-06-12. Completely independent from SC Gates 1 and 2. Lives in a new Streamlit tab.

```
massive.io tick data (via Trades API)
        |
        ├── parse_massive_ticks_from_api() → resample_ticks_to_bars()
        │              → App 5M bars
        |
        ├── convert to NT import format (yyyyMMdd HHmmss;price;volume)
        │   → import into NT → NT builds 5M bars internally
        │       → NinjaScript bar exporter → NT 5M bars CSV
        │       → NinjaScript signal indicator → MCSignals CSV
        |
        └── Aggs API (resolution=5min) → massive.io reference bars
                |
        three-way comparison: App bars vs NT bars vs massive bars
                |
            all must match → trust App bars for simulation
                |
        import MCSignals CSV → run simulations in App
```

**Same tolerance thresholds as Track 1 (Gate 1/2).**

**What this proves:** App bar builder matches NT bar builder on the same underlying tick data. MCSignal simulations in the App are trustworthy.

**What this does not replace:** SC Gate 1/2. The SC path continues independently. If massive.io track succeeds first, SC track may be retired.

### Files (to be created)
| File | Description |
|------|-------------|
| `massive_tab.py` | New Streamlit tab — fetch, compare, simulate |
| Additions to `data_loader.py` | `parse_massive_ticks_from_csv()`, `parse_massive_ticks_from_api()`, `parse_massive_bars_from_api()` |

### Implementation Notes
- Reuse `resample_ticks_to_bars()` — no new bar logic
- Reuse `build_comparison()` — called twice for three-way diff
- Cache ticks locally after API fetch (parquet) — do not re-fetch on every run
- Rollover: use `last_trade_date` from Contracts API
- NinjaScript bar exporter: to be written when tick data arrives (next week)

---

## Open Questions

- [ ] scid binary struct — confirm exact format from Sierra Charts ACSIL docs before building parser
- [ ] RTH session definition — 08:30 or 09:30 CT start? Must match SC session template exactly
- [ ] NT8 tick data format on disk — confirm it can be parsed directly or needs NT8 export first
- [ ] Rollover dates in 1-year NT8 sample — flag these bars separately in Gate 2 comparison
- [ ] ES ticker format in massive.io — confirm via `GET /futures/v1/contracts?product_code=ES&type=single` once API key available (2026-06-16)
