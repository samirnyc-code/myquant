# Confirm — balance-day filter (2026-06-21)

ER>=0.30 single-leg pinned 1.0R. Filled 4439, balance-day 708 (16%). Balance = opened inside prior range AND still inside at signal.

## Check 1 — out-of-sample folds (does it persist over time?)

Each fold's OOS window; balance-day vs baseline (all ER>=0.30). 'lift' = bal exp − base exp.

| fold | OOS dates | base n | base exp | bal n | bal exp | lift | bal PF |
|---|---|---|---|---|---|---|---|
| 0 | 2022-07-21→2022-10-19 | 267 | $120 | 47 | $307 | $+187 | 1.96 |
| 1 | 2022-10-20→2023-01-23 | 260 | $75 | 40 | $32 | $-43 | 1.08 |
| 2 | 2023-01-24→2023-04-28 | 266 | $51 | 40 | $50 | $-1 | 1.19 |
| 3 | 2023-05-02→2023-08-08 | 225 | $26 | 40 | $32 | $+6 | 1.15 |
| 4 | 2023-08-09→2023-11-08 | 224 | $188 | 27 | $295 | $+107 | 2.47 |
| 5 | 2023-11-09→2024-02-21 | 224 | $-70 | 44 | $-113 | $-43 | 0.63 |
| 6 | 2024-02-22→2024-05-21 | 200 | $26 | 28 | $128 | $+102 | 1.52 |
| 7 | 2024-05-22→2024-08-28 | 206 | $101 | 38 | $91 | $-11 | 1.36 |
| 8 | 2024-08-29→2024-12-04 | 186 | $148 | 45 | $183 | $+36 | 1.71 |
| 9 | 2024-12-05→2025-03-14 | 277 | $91 | 41 | $-59 | $-150 | 0.88 |
| 10 | 2025-03-17→2025-06-20 | 252 | $223 | 39 | $406 | $+183 | 1.64 |
| 11 | 2025-06-23→2025-09-26 | 231 | $54 | 42 | $96 | $+42 | 1.43 |
| 12 | 2025-09-29→2026-01-02 | 255 | $132 | 50 | $212 | $+80 | 1.56 |
| 13 | 2026-01-06→2026-04-14 | 230 | $137 | 39 | $471 | $+333 | 2.54 |

**Balance-day beat baseline in 9/14 OOS folds.**  Pooled OOS — baseline exp $94, balance exp $149.

## Check 2 — within time-of-day band (is it the state, or just 'early'?)

If balance still beats NON-balance inside the same TOD band, the edge is the balance state.

| band | grp | n | net | exp | PF |
|---|---|---|---|---|---|
| Open 08:30–10:00 · balance | 294 | $43,118 | $147 | 1.33 |
| Open 08:30–10:00 · non-bal | 732 | $15,121 | $21 | 1.04 |
| Mid 10:00–11:30 · balance | 164 | $23,697 | $144 | 1.45 |
| Mid 10:00–11:30 · non-bal | 666 | $83,671 | $126 | 1.38 |
| Lunch 11:30–13:00 · balance | 118 | $32,161 | $273 | 2.10 |
| Lunch 11:30–13:00 · non-bal | 846 | $81,136 | $96 | 1.34 |
| PM 13:00–15:15 · balance | 132 | $6,287 | $48 | 1.21 |
| PM 13:00–15:15 · non-bal | 1487 | $100,367 | $67 | 1.31 |
