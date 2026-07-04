# MenthorQ day-regime study — 2026-07-04 18:31

**Shift of unit: day, not trade (n=81).** Script: `scripts/menthorq_dayregime.py`.

## Verdicts

- **D1 CONFIRMED (as-published): negative-gamma days overshoot implied vol** —
  realized range / expected move 1.18 vs 0.96, CI [+0.03, +0.41], registered
  direction. FIRST MenthorQ claim to pass a test on our data. **Caveat:** the
  archive `gamma_condition` is EOD-stamped and the label partly derives from where
  spot sits vs HVL — a big down day can label ITSELF negative (circularity). The
  clean causal version (prev-day gamma) is +0.13 same direction, CI spans 0.
  **Pre-market capture going forward removes the contamination — top re-test once
  ~6 months of clean same-morning labels exist.**
- **D2 refuted: negative-gamma days are NOT more directional** (trend efficiency
  0.47 vs 0.46). The amplification is in AMPLITUDE, not direction — gamma is a
  volatility phenomenon, not a directional one.
- **D3/D4 null:** corridor width, open-position drift, expiring-GEX pinning — ~zero.
- **D5:** no regime cut causally predicts the stacked book's day-P&L. The one
  significant split is diagnostic: the book earns on days that realize MORE than
  implied (+$1,006 vs −$386/day, CI>0) — the book is long realized vol. A causal
  vol forecast is what would monetize this; prev-day vol_score didn't (n.s.).

81 days. Negative-gamma days: 33 (causal prev: 33).

## D1/D2 — gamma condition vs day character

| test (registered direction) | groups | diff | 95% CI |
|---|---|---|---|
| D1 range/EM: NEG vs pos (reg: NEG higher) | 1.177 (n=33) vs 0.960 (n=48) | +0.217 | [+0.032,+0.412] **⇐** |
| D2 trend eff: NEG vs pos (reg: NEG higher) | 0.472 (n=33) vs 0.458 (n=48) | +0.014 | [-0.105,+0.131] |
| D1 CAUSAL prev-day gamma | 1.131 (n=33) vs 0.999 (n=47) | +0.132 | [-0.062,+0.342] |
| D2 CAUSAL prev-day gamma | 0.453 (n=33) vs 0.477 (n=47) | -0.024 | [-0.142,+0.089] |
| D1 by prev vol_score>=3 (context) | 1.096 (n=29) vs 1.029 (n=51) | +0.067 | [-0.114,+0.263] |

## D3 — gamma corridor geometry

| relation | Spearman r | n |
|---|---|---|
| corridor width vs range/EM (reg: +) | -0.044 | 81 |
| corridor width vs trend eff | -0.027 | 81 |
| open_pos (0=PutSup,1=CallRes) vs signed drift (reg: −) | -0.122 | 81 |
| D4 expiring-GEX share vs PM range share (reg: −) | +0.040 | 81 |
| IV30 vs range/EM (sanity) | +0.121 | 81 |

| corridor tertile | days | range/EM | trend eff | book $/day |
|---|---|---|---|---|
| narrow | 27 | 1.12 | 0.50 | $468 |
| mid | 27 | 1.09 | 0.45 | $981 |
| wide | 27 | 0.94 | 0.44 | $-492 |

## D5 — stacked book day-P&L by regime (n=81 days, day = unit)

| cut | groups ($/day) | diff | 95% CI |
|---|---|---|---|
| book: NEG vs pos gamma | 381.396$ (n=33) vs 276.031$ (n=48) | +105.366 | [-1349.451,+1722.861] |
| book: CAUSAL prev NEG vs pos | -90.424$ (n=33) vs 650.774$ (n=47) | -741.198 | [-2148.505,+747.513] |
| book: narrow vs wide corridor | 467.949$ (n=27) vs -491.988$ (n=27) | +959.937 | [-565.778,+2703.747] |
| book: hi vs lo realized/EM (diagnostic, not causal) | 1006.446$ (n=41) vs -385.718$ (n=40) | +1392.165 | [+46.029,+2806.302] **⇐** |
