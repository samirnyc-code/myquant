# Slippage off-tick bug — root cause, fix, validation

**Date:** 2026-06-21 (Session 24)
**Severity:** Critical — corrupted every computed fill price in all research runs that
used the affected scripts.
**Status:** Fixed + validated. **All prior research dollar figures built with these
scripts are invalid and must be regenerated.**

## Symptom (the trade that exposed it)

Tracing a stored trade (CC2 short, 2023-10-17, bar #66) showed impossible prices:
- `EntryPrice = 4969.625` — not a multiple of 0.25 (ES tick)
- `RiskPts = 12.125` — derived from the off-tick entry
- stop **exit** `= 4981.875` — off-tick (the stop *level* 4981.75 was correct)
- `E2FillPrice = 4973.50` on a **short**, while the PB trigger was `4973.75` — a short
  PB add filling *below* its trigger, with price arriving from below, is impossible.

## Root cause

The engine measures slippage in **whole ticks** and multiplies by tick size:
`actual_entry = first_tick ± entry_slip * ts`, with `ts = 0.25`.

Every research script passed `entry_slip = 0.5, exit_slip = 0.5`:
```
0.5 ticks × 0.25 pts/tick = 0.125 pts = HALF A TICK  → not a tradeable ES price
```
So every price the engine added slippage to (E1 entry, E2 entry, stop/target/EOD exits)
landed off-tick, and `RiskPts` / R-multiples / PB / target levels all inherited the
error. The intended design was always integer ticks — `validate_engine.DEFAULTS` and
`handoff.md` both document `entry_slip=1, exit_slip=1`. The `0.5` only ever lived in the
research scripts, never in the validators (which is why the validators stayed green and
the bug survived).

## Second issue found while fixing (E2 fill direction)

The PB (pullback) add is a **resting limit** at the trigger. The engine applied *adverse*
slippage to it (`pb_trigger ∓ entry_slip*ts`), modelling a fill **worse than the limit** —
which a limit order cannot do. Combined with the half-tick + banker's rounding this
produced the impossible 4973.50 short fill.

## Fix

1. **E2/PB add now fills AT `pb_trigger`** (already tick-snapped) — no adverse slip.
   Applied identically across all paths so vec==loop holds:
   - `simulation_engine.py`: vectorized ratchet-off (`~546`), vectorized ratchet-on
     (`~654`), Python loop (`~727`), bars-path multileg (`~1009`)
   - `bar_analysis.py`: fast scale-in sweep (`~1184`)
   - `scripts/validate_oracle.py`: oracle reference (`~127`) updated to the same definition
2. **Guard:** `simulate_trades` now raises `ValueError` on any non-integer slip value, so a
   fractional tick can never silently corrupt prices again.
3. **Parameters → `entry_slip=1, exit_slip=0`** (ES rarely slips; 1 tick on the market
   entry, exits fill at level on touch):
   - active scripts: `per_setup_portfolio.py`, `late_period_analysis.py`,
     `er_timing_compare.py`, `fade_analysis.py`
   - UI defaults + integer step (no more half-tick entry): `wfa.py`, `portfolio.py`

## Validation (all green after the fix)

- `validate_ratchet --mode multileg --style e2`: vec == loop, byte-identical on all 9
  ratchet settings (1107 trades, 63 cols)
- `validate_oracle` (multileg): independent reference agrees with the engine on every
  sampled trade, **including `E2FillPrice`**
- `validate_scalein_sweep`: fast == engine on all 64 combos
- Live single-trade check: every price (entry, stop, PB, E2, exit) on a valid 0.25 tick;
  the CC2 short E2 now fills at 4973.75 (the trigger), not 4973.50.

## Same trade, before vs after

| field | before (broken) | after (fixed) |
|---|---|---|
| entry | 4969.625 ✗ | 4969.50 ✓ |
| risk (pts) | 12.125 | 12.25 |
| short E2 fill | 4973.50 (below trigger) ✗ | 4973.75 (at trigger) ✓ |
| stop exit | 4981.875 ✗ | 4981.75 ✓ |

## Impact on the edge

Round-trip friction is similar in magnitude (old ≈ 0.125+0.125 = 0.25 pts; new ≈
0.25+0 = 0.25 pts), so aggregate PnL is not expected to collapse — but every individual
trade shifts (R denominators, marginal target↔stop flips, E2 fill prices), so **all prior
numbers must be regenerated**. No corrected research runs have been produced yet.

## What was invalidated

Every dollar figure / PF / PROM / MAR from runs using the affected scripts — including the
S22–S23 per-setup and portfolio numbers produced via these scripts. The *directional*
conclusions (CC5 is the only +PROM setup, deep-PB exploit, EOD-drift at high R) may still
hold qualitatively but are unconfirmed until re-run.
