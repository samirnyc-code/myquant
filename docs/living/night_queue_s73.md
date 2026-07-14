# S73 Night Work Queue — user directives 2026-07-15 (~01:00)

Durable so nothing is lost. Check off as done; carry unfinished into handoff.

## Directives (verbatim intent)
1. **[EDGE] ES gamma-level backtest** — 1yr ES daily levels (`levels_history.csv`) ×
   ES 5M bars. Any indicators allowed. Find a tradeable edge on the levels
   (do price bars respect CR/PS/HVL? bounce/reject/break stats, conditioned).
2. **[VERIFY] Reproduce MenthorQ's own backtest tile stats** — their claimed
   hold-rates per level; check against our own bar data.
3. **[EDGE] Fold aggregate GEX (365d) into the edge search** — regime-condition
   the level tests on GEX sign/percentile.
4. **[GOAL] The edge can live in EITHER ES futures OR SPX options.** Keep both open.
5. **[DATA] Historical OI — user does NOT believe it's unavailable.** Dig harder.
   Tied to #6.
6. **[DATA] date param is probably wrong** — find the correct param name/format
   for the snapshot endpoints (gamma-levels / matrix / net-gex-by-expiration).
   If it works → historical per-strike + OI unlocked → redo #5.
7. Remember everything → THIS FILE.

## Dependency order
6 (unlock history) → 5 (OI) → 1 + 3 (edge, richer if 6 works) → 2 (verify) 

## Status
- [x] 6 date param probe — NO param works (11 names x3 fmts x2 paths); snapshots today-only
- [~] 5 historical OI — not via snapshot API; still open (QUIN? admin-ajax?) per user disbelief
- [x] 1 ES level backtest v1 — see findings
- [ ] 3 GEX regime conditioning — need to pull 365d gamma-insights, merge
- [ ] 2 backtest-tile verification
- [ ] KB: ingest guides + financial wiki (running, bk8xzcczg)

## Notes / findings
**ES level study v1 (228 sessions, MOVE=4pt/40min/TOL=1pt):**
- CR touched 159x, hold-rate **54.7%** — weak; fade E +0.38pt (costs kill it)
- PS touched only 3x/yr (price rarely falls to it — confirms S66 "levels rarely reached")
- **TIME-OF-DAY is the real signal:** 08:00 CT hold 67.9%, 09:00 61.9%, 10:00 60.7%,
  midday 12:00 CT **35.3%** (levels BREAK), 14:00 back to 61%. Morning-hold/midday-break.
- HVL: open-below-HVL (n=7) → +48pt, 100% up (tiny n, watch)
- NEXT: bigger MOVE grid, GEX-regime conditioning, split by trend/range day, verify PS scarcity

**★ CANDIDATE EDGE FOUND — CR fade on negative-GEX mornings (directive #3 payoff):**
GEX conditioning (causal, prior-EOD GEX sign) flips the textbook:
- pos-GEX days hold 49.5% (coin flip); NEG-GEX days hold 64.2%; neg-GEX MORNINGS 80%+
- Real trade sim (5pt stop / 10pt tgt / 1.25pt friction, ES $50/pt):
  - **neg-GEX morning CR fade: n18, win 55.6%, +$104/trade, +$1,875/yr**
  - pos-GEX morning fade: -$72/trade (LOSES) -> mirror = trade CR BREAKOUT long
  - unfiltered: ~$0. The GEX sign filter IS the edge (~$180/trade spread).
- CAVEATS: n18 (small), 1yr only, stop/tgt not swept (overfit risk), ES-only.
  LEAD not validated. Next: sweep stop/tgt, add NQ/YM, test pos-GEX breakout,
  out-of-sample split, SPX-options expression (buy puts / put spread same signal).
- Historical OI: QUIN serves AGGREGATE call/put OI history (proved); per-strike
  today-only via API. Parked as marginal for current strategies.
