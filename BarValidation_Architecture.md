# Bar Validation Module — Architecture
**Project:** MyQuant Python Sim  
**Status:** Planning  
**Last Updated:** June 1, 2026

---

## Purpose

Validate that Python-built 5-minute OHLCV bars from Sierra Charts tick data match Sierra Charts' own bar calculations. This is the foundation check before any simulation logic is built on top.

---

## Data Flow

```
Sierra Charts Tick Data (.scid / .csv)
        │
        ▼
Python Bar Builder (Module 1)
        │
        ▼
Python 5-min OHLCV DataFrame
        │
        ├──────────────────────────────┐
        ▼                              ▼
Sierra Charts Export             Python Bars
(built-in "Export Bars           (our build)
 to File" study → CSV)
        │                              │
        └──────────────┬───────────────┘
                       ▼
              Comparison Script
                       │
                       ▼
              Validation Report
```

---

## Sierra Charts Export

No custom study needed. Use built-in:  
**Analysis → Export Chart Data**  
- Bar type: 5-Minute  
- Session: RTH only  
- Date range: same as tick data  
- Output: CSV with Timestamp, Open, High, Low, Close, Volume

---

## Comparison Logic

Align both DataFrames on **Timestamp** (inner join).  
Per bar, compute:

| Field | Diff | Flag if |
|-------|------|---------|
| Open | abs(SC - PY) | > 0 ticks |
| High | abs(SC - PY) | > 1 tick |
| Low | abs(SC - PY) | > 1 tick |
| Close | abs(SC - PY) | > 0 ticks |
| Volume | abs(SC - PY) | > 0 |

**1 tick for ES/MES = 0.25**

---

## Expected Results

| Category | Expected | Action if not met |
|----------|----------|-------------------|
| Bars with zero diff on O/C | >99% | Investigate bar alignment / session logic |
| Bars with H/L diff ≤ 1 tick | >99% | Acceptable — data provider variance |
| Bars with H/L diff > 1 tick | <1% | Flag and inspect individually |
| Volume diff | Some variance | Low priority — tick bunching |

---

## Visual Output

### 1. Match Rate Summary (Bar Chart)
```
Open   ████████████████████ 99.8% exact
High   ███████████████████░ 99.2% within 1 tick
Low    ███████████████████░ 99.3% within 1 tick  
Close  ████████████████████ 99.7% exact
```

### 2. Diff Distribution (Histogram per OHLC field)
- X-axis: diff in ticks (-3 to +3)
- Y-axis: number of bars
- Expect: spike at 0, tiny tails at ±1

### 3. Timeline Plot (Flagged Bars)
- X-axis: date
- Y-axis: H or L diff in ticks
- Dots at 0 = perfect match (grey)
- Dots at ±1 = acceptable (yellow)
- Dots at >±1 = investigate (red)
- Helps identify if diffs cluster around specific dates/events (e.g. rollovers, holidays)

### 4. Summary Table (top of report)
```
Total bars compared:     12,450
Perfect match (OHLC):    12,301  (98.8%)
H/L diff = 1 tick:          142  ( 1.1%)
H/L diff > 1 tick:            7  ( 0.1%)  ← INVESTIGATE
Volume diff:              1,203  ( 9.7%)  ← expected, low priority
```

---

## Decision Gate

**Pass:** ≥99% of bars match within 1 tick on H/L, 100% on O/C  
**Fail:** Any systematic diff pattern → fix bar builder before proceeding

Only after **Pass** do we build simulation logic on top.

---

## Files

| File | Description |
|------|-------------|
| `bar_builder.py` | Reads tick data, builds 5-min OHLCV bars |
| `sc_exporter_guide.md` | How to export from Sierra Charts |
| `bar_validator.py` | Comparison script, generates report |
| `validation_report.html` | Visual output |

---

## Open Questions

- [ ] Sierra Charts tick export format: `.scid` (binary) or ASCII CSV? Determines parser needed.
- [ ] RTH session definition for ES/MES: 09:30–16:00 ET? Confirm with SC settings.
- [ ] Continuous contract roll handling — how does SC handle it vs our tick data?

---

*Next: Build `bar_builder.py` once tick data format is confirmed.*
