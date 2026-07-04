# MenthorQ main-level S/R follow-up — 2026-07-04 19:09

80 days.

## T-A — day-range containment vs distance-matched benchmark

Benchmark = empirical CDF of the day's (high−open)/EM (resp. (open−low)/EM)
over all days, evaluated at each level's z = (level−open)/EM. 'Excess' >0 means
the level contains the extreme MORE often than any price that far away would.

| level | days usable | contained | benchmark | excess | boot 95% CI |
|---|---|---|---|---|---|
| Call Resistance | 74 | 81% | 82% | -0.9pp | [-8.0, +5.7] |
| Call Res 0DTE | 68 | 68% | 67% | +0.3pp | [-7.9, +8.6] |
| 1d_max (IV band, ref) | 76 | 83% | 78% | +4.5pp | [-3.2, +11.9] |
| Put Support | 76 | 95% | 91% | +3.8pp | [-0.8, +7.8] |
| Put Sup 0DTE | 68 | 82% | 81% | +1.2pp | [-5.4, +7.1] |
| 1d_min (IV band, ref) | 78 | 81% | 82% | -1.2pp | [-9.9, +6.2] |

## T-B — first directional touch → EOD outcome vs matched pseudo-levels

Pseudo-levels: same z-distance distribution (shuffled across days, 5x, seed 42).

| level | touched days | close-beyond% | median reject depth | ctrl beyond% | ctrl depth | depth diff CI |
|---|---|---|---|---|---|---|
| Call Resistance | 14 | 7% | 14.8 pts | 2% | 19.2 pts | [-17.5, +5.3] |
| Gamma Wall 0DTE | 22 | 5% | 20.8 pts | 1% | 20.0 pts | [-10.1, +17.1] |
| HVL from below | 8 | 12% | 47.1 pts | 3% | 23.2 pts | [-17.6, +61.4] |
| Put Support | 4 | insufficient | | | | |
| HVL from above | 12 | 8% | 40.8 pts | 2% | 29.8 pts | [-11.6, +35.0] |

## T-C — original 6-bar bounce test, per level type (diagnostic)

| level | touches | bounce% | break% | mean drift (pts, along approach) |
|---|---|---|---|---|
| Call Resistance | 41 | 24.4% | 75.6% | +1.30 |
| Call Res 0DTE | 65 | 24.6% | 75.4% | -0.35 |
| Put Support | 28 | 14.3% | 85.7% | -6.04 |
| Put Sup 0DTE | 82 | 25.6% | 74.4% | -3.08 |
| HVL | 70 | 28.6% | 71.4% | -5.36 |
| Gamma Wall 0DTE | 65 | 24.6% | 75.4% | -0.35 |
| 1d_max | 46 | 28.3% | 71.7% | -2.45 |
| 1d_min | 47 | 27.7% | 72.3% | -1.24 |
