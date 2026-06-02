# Data Sources
**Status:** Architecture — Living  
**Last Updated:** June 2, 2026  
**Rule:** This is the only file that defines data sources. All other docs reference this file, never duplicate it.

---

## Primary Tick Data — Sierra Charts (Delani)

| Item | Detail |
|------|--------|
| Provider | Sierra Charts via Delani |
| Instrument | ES (E-mini S&P 500 futures) |
| Format | `.scid` binary files (Sierra Charts native tick format) |
| Coverage | Multi-year — exact range TBD once files confirmed |
| Session | RTH only: 08:30–15:15 CT (confirm exact session template with SC settings) |
| Rollover | Quarterly ES contracts — SC rollover handling TBD |
| Status | Available |

**Parser needed:** Python `.scid` binary parser. Format is documented in Sierra Charts ACSIL reference. Each record: 4-byte date, 4-byte time (seconds since midnight), 4-byte float open, high, low, close, 4-byte volume. Confirm exact struct before building.

---

## Secondary Tick Data — Massive.io (Optional)

| Item | Detail |
|------|--------|
| Provider | Massive.io |
| Plan needed | Futures Advanced or Futures Business CME |
| Instrument | ES quarterly contracts: ESH, ESM, ESU, ESZ |
| Format | Daily flat files, one tick per line, Last price only |
| Timestamp | Milliseconds since epoch |
| Fields | timestamp, ticker, price, volume |
| Coverage | Back to 2017 |
| Status | Not purchased |
| Purpose | Cross-provider analysis validation only — not primary research data |

**Decision:** Purchase only after Sierra Charts data is validated and Python sim is producing results. Massive data will be used to verify that WFA conclusions from Sierra data hold up on an independent data source. It is not required to build the sim.

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

- [ ] Exact Sierra Charts scid struct — confirm with ACSIL docs before building parser
- [ ] SC rollover handling — continuous contract or quarterly? How are gaps handled?
- [ ] RTH session exact boundaries — 08:30 or 09:30 CT start? Confirm with SC session template
- [ ] Massive.io — purchase decision deferred until Sierra sim is producing results
