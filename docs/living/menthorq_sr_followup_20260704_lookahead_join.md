# MenthorQ main-level S/R follow-up — 2026-07-04 18:19

**Trigger:** user challenge to the S54 null — "the MAIN levels have to have some merit."
Pre-registered second look at the specific claim (containment + first-touch, day horizon),
run by `scripts/menthorq_sr_followup.py`. 81 days.

## Verdict

**The user's observation is real, but the explanation isn't gamma.** Call Resistance
caps the day 95% of the time and Put Support holds it 94% — the levels DO mark the
day's boundaries, which is exactly what the eye sees on the chart. But the pure
IV expected-move band (`1d_max/min` — prior close ± implied move, NO strike
information) contains just as well or better (+15.5pp/+14.0pp excess vs +9.4pp for
Call Res, +3.4pp n.s. for Put Support). The containment comes from *distance +
implied vol*, not from where the gamma sits. And on the rare days price actually
reaches a main level (Call Res 4 days, Put Sup 5 of 81 — too rare to trade), it does
NOT bounce more than random: Put Support broke 89% of its 6-bar touches. First-touch
rejection depths at Gamma Wall / HVL are larger than matched controls in point
estimate but CIs all span zero.

**Trading implication:** "day likely ends inside prior-close ± expected move" is a
real, causal, daily-scalar fact — and it's available from IV alone (we already carry
`exp_move_1d_pct`). The strike-based levels add nothing measurable on 81 days. If
anything is worth a pre-registered re-test with more data, it's target-feasibility
scaling off the IV band (does a 3R target that pokes outside the band underperform?),
not gamma-level S/R.

## T-A — day-range containment vs distance-matched benchmark

Benchmark = empirical CDF of the day's (high−open)/EM (resp. (open−low)/EM)
over all days, evaluated at each level's z = (level−open)/EM. 'Excess' >0 means
the level contains the extreme MORE often than any price that far away would.

| level | days usable | contained | benchmark | excess | boot 95% CI |
|---|---|---|---|---|---|
| Call Resistance | 80 | 95% | 86% | +9.4pp | [+4.6, +13.9] **⇐** |
| Call Res 0DTE | 74 | 82% | 72% | +10.1pp | [+2.6, +17.0] **⇐** |
| 1d_max (IV band, ref) | 79 | 94% | 78% | +15.5pp | [+9.9, +21.5] **⇐** |
| Put Support | 77 | 94% | 90% | +3.4pp | [-2.5, +9.2] |
| Put Sup 0DTE | 71 | 79% | 77% | +2.3pp | [-7.7, +11.2] |
| 1d_min (IV band, ref) | 75 | 92% | 78% | +14.0pp | [+7.6, +19.6] **⇐** |

## T-B — first directional touch → EOD outcome vs matched pseudo-levels

Pseudo-levels: same z-distance distribution (shuffled across days, 5x, seed 42).

| level | touched days | close-beyond% | median reject depth | ctrl beyond% | ctrl depth | depth diff CI |
|---|---|---|---|---|---|---|
| Call Resistance | 4 | insufficient | | | | |
| Gamma Wall 0DTE | 13 | 8% | 48.0 pts | 1% | 18.5 pts | [-3.3, +34.9] |
| HVL from below | 14 | 7% | 32.1 pts | 2% | 26.5 pts | [-13.4, +42.0] |
| Put Support | 5 | insufficient | | | | |
| HVL from above | 24 | 4% | 32.5 pts | 1% | 27.5 pts | [-7.1, +18.3] |

## T-C — original 6-bar bounce test, per level type (diagnostic)

| level | touches | bounce% | break% | mean drift (pts, along approach) |
|---|---|---|---|---|
| Call Resistance | 8 | 25.0% | 75.0% | +0.31 |
| Call Res 0DTE | 58 | 22.4% | 77.6% | +1.18 |
| Put Support | 36 | 11.1% | 88.9% | +5.49 |
| Put Sup 0DTE | 98 | 18.4% | 80.6% | +1.45 |
| HVL | 149 | 21.5% | 78.5% | -3.63 |
| Gamma Wall 0DTE | 58 | 22.4% | 77.6% | +1.18 |
| 1d_max | 20 | 25.0% | 75.0% | -1.74 |
| 1d_min | 39 | 10.3% | 89.7% | +2.97 |
