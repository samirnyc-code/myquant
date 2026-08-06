# 0DTE SPXW premium-selling — autonomous research log

Running log of hypotheses tested, results, and next ideas. Newest cycle at top.
Data: OPRA.PILLAR cbbo-1m, 841 sessions 2023-03-28 → 2026-08-04, ±200pt 0DTE grid.
Engine: `options_0dte_backtest.py` (hold-to-expiry) + `options_0dte_exits.py` (intraday).
All P&L per 1 contract, mid + cross fills, $1.30/leg commission.

---

## Established before cycles (Cycle 0)

- **Anchor:** open-anchored EM band beats close-anchored on every directional structure
  (+$6–31/trade). The gap carries information. Open anchor used everywhere below.
- **Structures:** open IC and BPS are the survivors; BCS is a 2024 artifact; iron fly loses.
- **Gap filter (skip up>+0.2%):** lifts IC $13→$43/trade, Sharpe 0.41→1.47, positive every
  year AND at cross fills. Passes true OOS (IC OOS Sharpe 2.83). **BUT** the acceleration is
  a *filter* property, not the base strategy (unfiltered IC/yr: 6.9/16.7/9.7/21.1 — flat).
- **Driver diagnosis:** recent P&L bump is mostly a VIX regime tailwind (VIX 15→19 → credit
  $133→$180) + filter overfit to recent up-gap tails. Durable piece = VRP (realized ≈ 0.5×
  implied EM, stable every year, modest). **No pre-2023 history; never crisis-tested.**
- **Sizing:** ~$20k/contract (maxDD $8.7k + margin $2.3k). Mid ~33%/yr, cross ~20%/yr,
  ~29% of months red, worst month −$3.2k. Minis (XSP) DON'T work — fixed fee eats 1/10 premium.
- **Baseline exits:** hold-to-expiry only, NO intraday management modeled.

### Standing skepticism (keep_in_check)
1. Filter is in-sample; base strategy is modest. 2. VIX tailwind inflates recent $.
3. Zero crisis data. 4. Treat any Sharpe > ~1.5 as regime-flattered until proven otherwise.

---

## Cycle 1 (intraday exits) — `options_0dte_exits.py`

Swept profit targets {25,33,50,66,75,90%} × stops {1.5,2,3× credit} × time-stop {none,15:45}
on IC & BPS (open anchor, mid fills). Baseline = hold-to-expiry.

**Findings:**
- **STOPS >> profit targets.** BPS + stop@2× credit (no PT): Sharpe **0.25→1.25**, maxDD
  **$13,237→$1,713 (−87%)**, mean $6.9→$10.1. The hard stop caps the fat left tail.
- **Profit targets alone don't help.** Tight PTs (25/33%) go NEGATIVE (commission churn +
  capped winners). Loose PTs (75/90%) ≈ baseline. Premium already mostly decays by expiry.
- **IC benefits less** — best Sharpe 0.51 (PT90+stop3+15:45). Two-sided = already balanced;
  the stop helps DD ($12.9k→$9.9k) but not mean.
- Win rate falls with stops (BPS 95.6%→61.8%) — you stop out more, but avoid the disasters.

**Caveats to verify (Cycle 1 analysis):**
- Mid fills OVERSTATE stops — a stop fires on a fast adverse move, exactly when the spread
  is widest; real fill is worse than mid. Need cross-fill check.
- Path-dependency / whipsaw: stop out then market reverts. Year-by-year needed.
- Per-trade P&L for all configs saved to `exit_trades.parquet` for fast slicing.

### Cycle 2 ideas (queued)
1. Verify BPS-stop year-by-year + cross fills (is Sharpe 1.25 real or 2024-ish + mid-flattered?)
2. Finer stop grid (1.25/1.75/2.5) + pure-stop on IC
3. Stop × gap-filter interaction (do they stack or overlap?)
4. Delta-based strikes (Δ0.16 short) vs fixed-EM — adapts to smile/skew
5. Width by % of spot (not fixed 25pt) — fixes the drift found in the regime diag
6. Size by VIX/gap instead of filtering (keep all days, weight the good ones)
7. Entry-time sweep (09:30 vs 10:00 vs 11:00) — is the open the best entry?

---
