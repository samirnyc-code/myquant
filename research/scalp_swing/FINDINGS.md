# ES intraday scalp/swing search — FINDINGS (2026-07-27)

**Task:** find a profitable scalp + swing on ES, **min R/R 2:1**, 1 contract, no
opposing trades. **Assumptions (user-confirmed):** $30 round-trip cost, flat by
RTH close (intraday only), train 2021-23 / OOS 2024-26.

**Data:** `data/ticks_continuous/*.parquet` — 1,270 RTH tick-days (2021-06→2026-07),
resampled to 5M for signals; **every fill (entry/stop/target) resolved on the raw
tick stream in true time order** (`engine_ticks.py`) → no phantom fills.

## Result: NO net-profitable 2:1 intraday strategy found (~130 configs, 5 families)

| Family | Best train PF | Best OOS PF | Gross edge? | Verdict |
|---|---|---|---|---|
| Opening-range breakout (scalp) | 1.01 | <1.0 | ≈cost | net breakeven |
| Trend pullback (scalp/swing) | 0.87 | 0.87 | **negative** | dead |
| Gated breakout (VWAP+expand+TOD) | 0.96 | <1.0 | ≈cost | net breakeven |
| VWAP fade / mean-reversion (scalp) | 0.72 | 0.81 | **negative** | dead |
| VWAP fade / mean-reversion (swing) | 0.76 | 0.82 | **negative** | dead |

### Why (the binding constraint is the 2:1, not the search)
- **Gross decomposition:** pullback & fade lose money even at ZERO cost →
  negative expectancy at 2:1. Breakout has a faint gross edge but it is
  **~$32/trade gross vs $30/trade cost** → net ≈ 0.
- **ES intraday mean-reverts.** Reversion patterns win often at RR<1; forcing a
  2× target makes most fades reverse before reaching it (win rate 18–32%).
- **ES 2:1 momentum is too weak to clear cost.** The latent breakout edge is real
  but smaller than realistic transaction costs at any tradeable frequency.
- Consistent with our own S85 finding: **raw ungated entries ≈ dead; the edge is
  the regime/structural GATE, not the entry.**

### What DOES achieve ~2:1 (for reference, already validated — see `regime/indep`)
- **2E-HVL day-trade:** with-trend, entry above prior-day HVL, 0.30×ADR stop,
  regime/phase gate, **EOD hold** → PF ~1.5, +$15k/yr/ES, OOS-passed. It is a
  day-trade (swing-like), NOT a scalp, and it REQUIRES the regime gate + a
  structural level. No validated 2:1 SCALP exists anywhere in the book.

## Forward options (need user decision)
1. **Relax the 2:1 for the scalp.** ES scalps live at ~1:1 with a >55% win rate.
   A genuine scalp is findable there; 2:1 is not.
2. **Build a properly-gated 2:1 swing** using a real conditioner (regime phase /
   prior-day structural level), accepting lower frequency. Only path with prior
   evidence of success.
3. **Stop** — accept that a fresh naive 2:1 intraday strategy isn't in this data.

## Files
`build_5m.py` (bars) · `engine_ticks.py` (tick-accurate engine + metrics) ·
`strategies.py` (breakout/pullback/gated/fade) · `run_scan.py` (grid driver) ·
`scan_*.csv` (full ranked results).
