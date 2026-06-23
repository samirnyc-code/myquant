# Fade test — RevFT (MyReversals) signal set — 2026-06-24

**Question:** the RevFT 1:1 equity curve bleeds steadily to ~−$300k. Does fading
(reverse direction, mirror stop across entry → stop↔target at 1:1) recover it?

**Method:** `scripts/fade_revft_test.py`. Full set `ba_signals_revft.parquet`
(6,328 signals, 2021-06 → 2026-06), single-leg 1R, day-by-day on real ticks
(`_continuous.parquet`), one tick-load pass for all four scenarios. Trades scored
independently (unlimited-positions sim assumption).

- **gross** = frictionless (commission 0, entry_slip 0, exit_slip 0, stop_offset 1) → directional edge only
- **net** = realistic (commission $5 RT, entry_slip 1 tick, exit_slip 0, stop_offset 1)
- **costs** = gross − net (commission + entry slippage + the path-perturbation slippage induces)

## Result (6,133 filled trades)

| Variant  | Trades | Win%  | Gross      | Costs    | Net         | PF   | expR    | MaxDD     | P/DD |
|----------|-------:|------:|-----------:|---------:|------------:|-----:|--------:|----------:|-----:|
| ORIGINAL | 6,133  | 46.1% | −$79,150   | $108,315 | −$187,465   | 0.90 | −0.0727 | −$196,888 | −1.0 |
| FADE     | 6,133  | 48.7% | +$18,638   | $89,428  | −$70,790    | 0.97 | −0.0202 | −$90,938  | −0.8 |

### FADE net — by year (masked from the single full run)
| Year | Trades | Win%  | Net      | PF   | expR    | MaxDD    | P/DD |
|------|-------:|------:|---------:|-----:|--------:|---------:|-----:|
| 2021 | 640    | 50.9% | +$5,300  | 1.09 | +0.0300 | −$8,822  | +0.6 |
| 2022 | 1,327  | 47.2% | −$30,735 | 0.94 | −0.0503 | −$45,965 | −0.7 |
| 2023 | 1,195  | 49.7% | +$2,675  | 1.04 | −0.0004 | −$10,588 | +0.3 |
| 2024 | 1,198  | 48.3% | −$14,590 | 0.96 | −0.0263 | −$31,900 | −0.5 |
| 2025 | 1,217  | 48.5% | −$13,210 | 0.98 | −0.0274 | −$25,040 | −0.5 |
| 2026 | 556    | 49.1% | −$20,230 | 0.90 | −0.0197 | −$23,488 | −0.9 |

## Findings

1. **Real (small) negative directional edge** — original loses even GROSS (−$79k
   frictionless), so this is not pure cost bleed. Fading flips gross positive (+$18.6k).
2. **Fade still loses net (−$70.8k).** The +$18.6k gross edge is swamped by ~$89k of
   execution cost. Fade is "less bad" (½ the drawdown, PF 0.90→0.97) but a firm loser.
3. **1:1 whipsaw tax is large.** A clean mirror of −$79k gross would be +$79k; the fade
   realized only +$18.6k — ~$60k lost to intrabar "which-touched-first" on bars that tag
   both stop and target. Confirms the at-1:1 fade is NOT a clean sign-flip.
4. **By year even faded:** only 2021/2023 green; 2022/24/25/26 red. No stable fadeable edge.

## Verdict
Core problem is not direction — it's **~6,000 trades/run at 1:1 with a sub-cost edge**:
~$15–18/trade of friction swamps everything. Can't fade or flip out of that. Levers that
matter: **trade far less** (a selectivity gate lifting gross/trade well above ~$15) or
**widen R** so cost is a smaller fraction per trade. Open follow-ups: (a) selectivity-gate
sweep on RevFT, (b) re-run fade at 2:1 / 3:1.
