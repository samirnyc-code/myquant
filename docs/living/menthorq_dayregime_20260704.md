# MenthorQ day-regime study — 2026-07-04 19:10

80 days. Negative-gamma days: 33 (causal prev: 33).

## D1/D2 — gamma condition vs day character

| test (registered direction) | groups | diff | 95% CI |
|---|---|---|---|
| D1 range/EM: NEG vs pos (reg: NEG higher) | 1.130 (n=33) vs 1.008 (n=47) | +0.123 | [-0.089,+0.357] |
| D2 trend eff: NEG vs pos (reg: NEG higher) | 0.453 (n=33) vs 0.477 (n=47) | -0.024 | [-0.138,+0.094] |
| D1 CAUSAL prev-day gamma | 1.157 (n=33) vs 0.974 (n=46) | +0.183 | [-0.037,+0.411] |
| D2 CAUSAL prev-day gamma | 0.458 (n=33) vs 0.471 (n=46) | -0.013 | [-0.127,+0.104] |
| D1 by prev vol_score>=3 (context) | 0.988 (n=29) vs 1.087 (n=50) | -0.099 | [-0.294,+0.089] |

## D3 — gamma corridor geometry

| relation | Spearman r | n |
|---|---|---|
| corridor width vs range/EM (reg: +) | +0.056 | 80 |
| corridor width vs trend eff | -0.085 | 80 |
| open_pos (0=PutSup,1=CallRes) vs signed drift (reg: −) | +0.172 | 80 |
| D4 expiring-GEX share vs PM range share (reg: −) | +0.057 | 80 |
| IV30 vs range/EM (sanity) | +0.039 | 80 |

| corridor tertile | days | range/EM | trend eff | book $/day |
|---|---|---|---|---|
| narrow | 27 | 1.08 | 0.52 | $1,187 |
| mid | 26 | 1.08 | 0.43 | $157 |
| wide | 27 | 1.01 | 0.46 | $-317 |

## D5 — stacked book day-P&L by regime (n=81 days, day = unit)

| cut | groups ($/day) | diff | 95% CI |
|---|---|---|---|
| book: NEG vs pos gamma | -90.424$ (n=33) vs 650.774$ (n=47) | -741.198 | [-2157.072,+654.112] |
| book: CAUSAL prev NEG vs pos | 278.613$ (n=33) vs 436.414$ (n=46) | -157.802 | [-1543.731,+1324.109] |
| book: narrow vs wide corridor | 1187.350$ (n=27) vs -316.622$ (n=27) | +1503.973 | [-215.020,+3274.750] |
| book: hi vs lo realized/EM (diagnostic, not causal) | 1315.576$ (n=40) vs -625.515$ (n=40) | +1941.091 | [+682.813,+3289.984] **⇐** |
