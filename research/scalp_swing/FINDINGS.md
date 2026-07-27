# ES intraday scalp/swing search — FINAL FINDINGS (2026-07-27)

**Task:** find a profitable scalp + swing on ES, min R/R 2:1, 1 contract, no opposing
trades. **Assumptions (user-confirmed):** $30 round-trip cost, flat by RTH close,
train 2021-23 / OOS 2024-26 holdout.

**Data:** `data/ticks_continuous/*.parquet` — 1,270 RTH tick-days (2021-06→2026-07),
resampled to 5M for signals; **every fill (entry/stop/target) resolved on the raw
tick stream in chronological order** (`engine_ticks.py`) → no phantom fills. Trades
audited on charts before reporting (`AUDIT_swing_trades.png`).

---

## HEADLINE

- **SWING — FOUND (real, modest).** Long-only, **SMA20-D-gated 60-min opening-range
  breakout**, 10pt stop / 20pt target (2:1), held to RTH close.
  **PF 1.28 · +$36,975 (~$7.4k/yr/ES) · win 44.8% · maxDD −$6,665 · net/DD 5.5 ·
  Sharpe 1.81** over 2021-26. **OOS 2024-26: PF 1.14, +$11,210, Sharpe 0.96.**
  Green every year (2021 1.87 → 2026 1.08; edge decaying but still positive OOS).
- **SCALP — NOT FOUND.** No configuration survives OOS at realistic cost. A tradeable
  ES scalp does not exist in 5-minute bar patterns; the intraday edge only appears
  when held to close with a wide stop (i.e. it is structurally a swing).

## The core discovery (holds across ~150 tick-accurate OOS configs)

**The edge is SELECTION (which trades to take), not entry/exit/RR mechanics.**
1. **Ungated directional entries have ZERO edge at ANY R/R.** Breakout, pullback,
   gated-breakout(VWAP), and mean-reversion fade — all net-negative OOS. Relaxing
   to 1:1 / 0.75:1 did not help (an entry with no predictive value can't be fixed
   by moving the target). Gross decomposition: pullback/fade negative even at $0
   cost; breakout's latent edge ≈ $32/trade ≈ the $30 cost.
2. **A structural-level gate flips it.** Price vs prior-day **SMA20-D** (self-computed
   20-day SMA of RTH daily closes; ≈ HVL, 93%/κ0.85 per S85) turns the losing IB
   breakout into a winner: ungated OOS PF 1.03 → gated OOS PF 1.14, and maxDD halves.
3. **It is not just beta.** Buy-IB-hold-close (pure drift) = Sharpe 0.10, maxDD −$31k.
   The gate lifts that to Sharpe ~1 OOS with −$6.7k DD. The SMA20-D selection adds
   real value beyond the 2021-26 uptrend.
4. **Wide stop + hold-to-close is essential.** Tight stops lose even gated; a 30-min
   scalp version of the exact same signal fails OOS (PF 0.92). The winner needs room
   for the 2:1 target to become a genuine trend leg.

## Honest caveats on the swing
- Modest edge (OOS PF 1.14) and **decaying** (yearly PF 1.87→1.08).
- **Long-only**, validated in a **5-year bull market** — no bear-only holdout. The
  gate keeps it flat in downtrends (price < SMA20-D → no long), which is the correct
  protective behaviour, but bear performance is unproven. (Same limitation as the 2E book.)
- Shorts (price < SMA20-D → short breakout below IB) were net −$6,050 → dropped.

## Stronger sibling (already validated — SWING "B")
The 2E-HVL book (branch `regime/indep`) is the same SMA20-D-gate family, better entry:
**with-trend 2E, gate = entry > prior-day SMA20-D, 0.30×ADR stop, 09-13, EOD flat →
2021+ PF 1.54, +$14,959/yr/ES, maxDD −$10,155, Sharpe 2.47.** Realized payoff ~1.42:1
(NOT a fixed 2:1 — it uses EOD exit). Recall metrics from memory `s85-2e-book-metrics`.

## Why no scalp (and where one would live)
5-minute OHLC patterns carry no cost-surviving intraday edge. A real ES scalp edge
would require order-flow / microstructure (the L2 mbp-10 + L3 mbo Databento data on
disk), not 5M bars — book imbalance, absorption, sweeps. Out of scope for this data set.

## Files
`build_5m.py` · `engine_ticks.py` (tick engine + metrics) · `strategies.py`
(breakout/pullback/gated/fade) · `swing_level_gated.py` (SMA20-D/HVL gate, THE winner)
· `run_scan.py` `run_gated.py` (grids) · `finalize_swing.py` (final + audit) ·
`scan_*.csv` (all results) · `TRADES_swing_final.csv` (475 trades) ·
`AUDIT_swing_trades.png` · `EQUITY_swing_final.png`.
