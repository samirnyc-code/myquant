# MyReversals (RevFT) — Python port + full sweep (2026-07-28)

Convert the NT8 `MyReversals.cs` indicator to Python, run in sim on 5yr ES 5M RTH
ticks, and sweep the individual setup settings. 1 ES, no opposing, $30 RT, flat by
close, train 2021-23 / OOS 2024-26. All fills tick-accurate (no phantom fills).

## Port + validation
- `revdetect.py` — faithful port of Trap/BO/OB/IB detection + Follow-Through, EVERY
  detection parameter exposed. Runs the continuous RTH 5M series (cross-day lookbacks
  like NT). Signal = FT[i] AND rev[i-1]; entry = Close[i] (BTC), stop = 2-bar extreme.
- **Validated vs the indicator's own signal export:** on the common session window
  (08:35–13:30) the port reproduces **97.4% of exported signals, 97.0% symmetric,
  99.0% type agreement.** (The export used a Nymex-Energy 08:10–13:30 session; the
  port uses standard equity RTH — the only deltas are the non-overlapping window.)
- Raw signals, EOD hold = **PF 0.98** (breakeven), matching the prior RevFT baseline.

## What was swept
1. **Filters/combos** (type, direction, SMA20-D regime, time-of-day, entry model, exit).
2. **Trade LOCATION** (loc_pct in day range, dist-to-extreme, fresh N-bar extreme,
   prior-day H/L). **Result: fading INTO the day extreme HURTS** — these are
   momentum-CONFIRMED reversals (buy the follow-through), so requiring a fresh
   extreme = catching a knife. Location did not produce a robust edge.
3. **Detection parameters** (the actual NT knobs): ABR multiples, IBS thresholds,
   FT strength, OB_Strict, Prior_OppClose, body/tail minimums. **Result: stricter =
   better, consistently.** The single most impactful knob is **FT_ABR (follow-through
   bar strength)** — requiring the FT bar ≥ 1.0×ABR turns breakeven into an edge.

## Best config found
**detection FT_ABR ≥ 1.0 + OB_Strict · filter below prior-day SMA20-D · EOD hold**

| | PF | net $ | win% | maxDD | net/DD | Sharpe |
|---|---|---|---|---|---|---|
| ALL 2021-26 | **1.19** | **+$96,330** | 37.1 | −$33,288 | 2.9 | 1.28 |
| TRAIN 2021-23 | 1.09 | +$24,362 | 36.2 | −$28,840 | 0.8 | 0.68 |
| OOS 2024-26 | **1.31** | +$71,968 | 38.4 | −$26,610 | 2.7 | 1.88 |

The winning gate is **below-SMA20-D** — reversals work in the negative-gamma /
below-mean regime and die above it (matches S85 `s85-2e-book-metrics` exactly).

## Honest caveats (this is a satellite, not a steady core)
- **Type-concentrated:** BO (breakout-reversal) = +$80.5k of the $96k; IB +$17.7k,
  Trap +$12.4k, **OB −$14.2k (loses even strict → should be dropped).**
- **Regime/year-concentrated:** 2021 +$10.8k, 2022 +$28.7k, **2023 −$15.1k, 2024
  −$6.4k**, 2025 +$66.5k, 2026 +$11.9k. NOT green every year — a ~2-year flat/losing
  stretch (2023-24), 2025 dominates. Train net/DD only 0.8.
- Reproduces & refines the prior RevFT verdict ("marginal modern-regime satellite")
  — now with the SPECIFIC detection knobs that lift it: strong-FT + drop-OB + below-SMA20.

## Files
`revdetect.py` (port) · `revsim.py` (tick sim) · `location.py` · `run_sweep.py`,
`run_location_sweep.py`, `run_detect_sweep.py`, `run_refine.py`, `finalize_revft.py`
· `sweep_*.csv` · `TRADES_revft_final.csv` · `EQUITY_revft_final.png` ·
`AUDIT_revft_trades.png`.
