# Balance deep-dive (2026-06-21)

Pinned 1.0R single-leg, all setups. 5444 filled signals. 'balance' = opened inside prior range AND still inside at signal.

## 1. ER30 vs Balance — is ER30 the only lever? (whole sample)

| cell | n | exp | win% | PF |
|---|---|---|---|---|
| ER≥.30 · balance | 708 | $149 | 58% | 1.43 |
| ER≥.30 · non-bal | 3731 | $75 | 54% | 1.25 |
| ER<.30 · balance | 189 | $-103 | 44% | 0.78 |
| ER<.30 · non-bal | 816 | $-132 | 39% | 0.66 |

Reading: compare balance vs non-bal WITHIN each ER row (does balance add to ER?), and ER≥ vs ER< WITHIN each balance column (does ER add to balance?).

## 2. prior day was an INSIDE day — within ER≥0.30

| bucket | n | exp | win% | PF | (balance only) n | exp |
|---|---|---|---|---|---|---|
| normal | 3833 | $82 | 55% | 1.26 | 664 | $135 |
| inside-day | 475 | $172 | 58% | 1.60 | 44 | $348 |

## 2. prior day ADR extension (range/ADR) — within ER≥0.30

| bucket | n | exp | win% | PF | (balance only) n | exp |
|---|---|---|---|---|---|---|
| compressed<0.8 | 1520 | $91 | 55% | 1.35 | 125 | $222 |
| trend>1.6 | 553 | $6 | 49% | 1.01 | 155 | $2 |
| extended1.2-1.6 | 710 | $118 | 56% | 1.37 | 163 | $157 |
| normal0.8-1.2 | 1508 | $110 | 56% | 1.38 | 260 | $198 |

## 2. prior day close location (CLV) — within ER≥0.30

| bucket | n | exp | win% | PF | (balance only) n | exp |
|---|---|---|---|---|---|---|
| closed-weak | 1256 | $93 | 54% | 1.27 | 227 | $153 |
| closed-strong | 1820 | $78 | 55% | 1.28 | 268 | $110 |
| closed-mid | 1229 | $112 | 57% | 1.35 | 210 | $197 |

## 3. Walk-forward OOS (pinned 1.0R, same is=252/oos=63 folds)

| config | trades | exp | PF | %green folds | pooled net | MAR | exp 2022 (n) |
|---|---|---|---|---|---|---|---|
| none (all signals) | 4184 | $54 | 1.17 | 73% | $227,070 | 8.5 | $33 (616) |
| ER≥0.30 | 3422 | $94 | 1.31 | 80% | $321,655 | 13.4 | $99 (515) |
| balance only | 719 | $91 | 1.26 | 80% | $65,528 | 4.9 | $89 (102) |
| ER≥0.30 + balance | 576 | $141 | 1.43 | 73% | $81,114 | 7.8 | $119 (83) |
| ER≥0.30 + bal + prior-inside | 33 | $450 | 4.05 | 77% | $14,844 | 4.8 | $189 (2) |
| ER≥0.30 + bal + prior-trend>1.6 | 119 | $20 | 1.04 | 50% | $2,381 | 0.2 | $586 (9) |
