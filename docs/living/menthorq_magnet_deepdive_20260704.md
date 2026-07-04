# Deep dive — AM trades toward a prior-EOD main gamma level (<=1R)

Definition: stacked signal, entry-bar close before 11:00 CT, nearest main MQ level ahead within 1R. Baseline battery on n=37.

- magnet: n=37 ExpR +0.664 ±0.415 PF 3.28 WR 65% $+29,901
- rest of stack: n=166 ExpR +0.051 ±0.177 PF 0.97 WR 31% $-2,299

## 1. The actual trades

| date | time | dir | CC | toward | dist(R) | R done | exit |
|---|---|---|---|---|---|---|---|
| 2026-03-20 | 09:00 | Short | CC3 | PS0 | 0.20 | +0.84 | EOD |
| 2026-03-20 | 09:05 | Short | CC4 | PS0 | 0.16 | +0.80 | EOD |
| 2026-03-23 | 09:25 | Long | CC4 | CR0 | 0.71 | -1.01 | Stop |
| 2026-03-30 | 08:50 | Short | CC4 | PS0 | 0.66 | +1.13 | EOD |
| 2026-03-30 | 08:55 | Short | CC5 | PS0 | 0.52 | +0.97 | EOD |
| 2026-04-02 | 09:00 | Long | CC4 | HVL | 0.90 | +1.40 | EOD |
| 2026-04-07 | 08:45 | Short | CC3 | HVL | 0.28 | -0.01 | Stop |
| 2026-04-07 | 08:50 | Short | CC4 | HVL | 0.10 | -0.01 | Stop |
| 2026-04-21 | 08:55 | Long | CC4 | CR0 | 0.19 | -1.02 | Stop |
| 2026-04-21 | 09:00 | Long | CC5 | CR0 | 0.11 | -1.02 | Stop |
| 2026-04-24 | 10:50 | Long | CC2 | CR | 0.64 | +0.18 | EOD |
| 2026-04-28 | 08:40 | Long | CC2 | HVL | 0.82 | -1.03 | Stop |
| 2026-04-30 | 09:55 | Long | CC4 | CR | 0.37 | +2.08 | EOD |
| 2026-04-30 | 10:00 | Long | CC5 | CR | 0.29 | +1.89 | EOD |
| 2026-05-12 | 10:25 | Short | CC3 | PS0 | 0.82 | -1.02 | Stop |
| 2026-05-13 | 10:05 | Long | CC5 | CR0 | 0.96 | +2.98 | Target |
| 2026-05-13 | 10:40 | Long | CC3 | CR0 | 0.91 | +2.96 | Target |
| 2026-05-13 | 10:45 | Long | CC4 | CR0 | 0.35 | +2.97 | Target |
| 2026-05-14 | 08:45 | Long | CC2 | CR | 0.09 | +1.48 | EOD |
| 2026-05-20 | 09:20 | Long | CC2 | CR0 | 0.10 | +1.00 | EOD |
| 2026-05-22 | 09:45 | Long | CC5 | CR | 0.10 | -0.02 | Stop |
| 2026-05-28 | 10:30 | Long | CC3 | CR | 0.76 | +1.71 | EOD |
| 2026-06-04 | 10:10 | Long | CC3 | CR | 0.91 | +0.57 | EOD |
| 2026-06-04 | 10:15 | Long | CC5 | CR | 0.76 | +0.44 | EOD |
| 2026-06-05 | 08:50 | Short | CC4 | PS | 0.54 | +2.99 | Target |
| 2026-06-09 | 09:10 | Short | CC5 | HVL | 0.38 | +2.99 | Target |
| 2026-06-17 | 09:40 | Short | CC3 | PS0 | 0.59 | -0.02 | Stop |
| 2026-06-22 | 09:25 | Short | CC3 | CR0 | 0.41 | +0.90 | EOD |
| 2026-06-22 | 09:30 | Short | CC4 | CR0 | 0.03 | +0.39 | EOD |
| 2026-06-22 | 09:35 | Short | CC5 | HVL | 0.12 | +0.10 | EOD |
| 2026-06-25 | 08:55 | Short | CC4 | PS0 | 0.58 | -0.42 | EOD |
| 2026-06-29 | 09:10 | Short | CC4 | PS | 0.78 | -1.01 | Stop |
| 2026-06-29 | 09:35 | Long | CC4 | HVL | 0.50 | +0.63 | EOD |
| 2026-06-30 | 10:15 | Long | CC4 | CR | 0.75 | +0.48 | EOD |
| 2026-07-02 | 08:45 | Long | CC3 | CR | 0.80 | -1.01 | Stop |
| 2026-07-02 | 08:50 | Long | CC4 | CR | 0.44 | -1.01 | Stop |
| 2026-07-02 | 09:35 | Short | CC2 | CR0 | 0.45 | +1.25 | EOD |

## 2. Concentration

- 24 distinct days carry the 37 trades; top day $+5,424, top-3 days $+15,986 of $+29,901 total
- drop best single trade: n=36 ExpR +0.599 ±0.406 PF 2.88 WR 64% $+24,668
- drop best 3 trades: n=34 ExpR +0.505 ±0.403 PF 2.30 WR 62% $+17,027
- drop best day: n=34 ExpR +0.460 ±0.381 PF 2.87 WR 62% $+24,477
- longs n=21 ExpR +0.699 ±0.602 PF 2.81 WR 67% $+13,683
- shorts n=16 ExpR +0.618 ±0.567 PF 3.94 WR 62% $+16,218
- by CC type: CC2: n=5 ExpR +0.579 ±0.896 PF 7.92 WR 80% $+4,616; CC3: n=9 ExpR +0.548 ±0.830 PF 2.26 WR 56% $+3,086; CC4: n=15 ExpR +0.561 ±0.694 PF 2.23 WR 60% $+10,935; CC5: n=8 ExpR +1.041 ±1.010 PF 11.28 WR 75% $+11,265

## 3. Definition robustness (ExpR / n) — smooth or cliff?

| dist ≤ | AM<10:00 | AM<11:00 | AM<12:00 | all day |
|---|---|---|---|---|
| 0.5R | +0.55/17 | +0.75/19 | +0.62/22 | +0.57/23 |
| 0.75R | +0.57/23 | +0.69/27 | +0.60/30 | +0.56/31 |
| 1.0R | +0.42/27 | +0.66/37 | +0.60/40 | +0.52/43 |
| 1.5R | +0.49/37 | +0.58/50 | +0.57/55 | +0.45/63 |
| 2.0R | +0.26/52 | +0.38/66 | +0.38/72 | +0.28/85 |

## 5. Does price actually reach the level? (magnet confirmation)

- level reached before EOD: 81% of magnet trades
- winners reaching level: 100%; losers reaching: 46%
- (non-magnet stacked trades reach their nearest level 16% — mostly farther away)

## 6. Exit interaction — same trades at 1R flat (fresh sim)

- @1R flat magnet: n=37 ExpR +0.443 ±0.269 PF 2.69 WR 76% $+21,951
- @1R flat rest of stack: n=166 ExpR +0.056 ±0.138 PF 1.04 WR 52% $+2,989

## 7. Monthly P&L (3R/BE exec)

| month | n | net$ |
|---|---|---|
| 2026-03 | 5 | $+6,103 |
| 2026-04 | 9 | $+5,836 |
| 2026-05 | 8 | $+8,340 |
| 2026-06 | 12 | $+10,823 |
| 2026-07 | 3 | $-1,201 |