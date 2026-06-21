# Regime Ladder — base rates (2026-06-21)

Sessions: **1249** (2021-06-18 → 2026-06-15).  ETH coverage: 97%.  ADR=14d, accept N=12 bars.

Open location: inside 61%, above 23%, below 16%.

## Rung 1 — ETH edge (overnight balance break)

First RTH break of the overnight high/low → accept (closes beyond) vs reject.

| side | break rate | accept\|break | held EOD\|break | n |
|---|---|---|---|---|
| ETH High (up) | 65% | 54% | 56% | 786 |
| ETH Low (down) | 57% | 48% | 49% | 695 |

## Rung 2 — Brooks magnet (open INSIDE prior range)

Sessions opening inside prior range: **763** of 1249 (61%).

| metric | value |
|---|---|
| touch prior High before close | 52% |
| touch prior Low before close  | 42% |
| touch BOTH extremes           | 9% |
| touch NEITHER (pure inside)   | 16% |
| of touchers, High touched first | 57% |

**Acceptance at the prior extreme (discovery vs failed break):**

| level | accept\|touch | n |
|---|---|---|
| prior High | 57% | 393 |
| prior Low  | 48% | 320 |

## Rung 3 — ADR exhaustion (continuation survival curve)

final RTH range / ADR — median **0.93×**, mean 1.04×.  No assumed threshold; curve below.

| reached k×ADR | P(reach this) | P(reach next 0.25 \| here) | n |
|---|---|---|---|
| 0.50× | 91% | 76% | 1126 |
| 0.75× | 69% | 65% | 854 |
| 1.00× | 45% | 58% | 557 |
| 1.25× | 26% | 57% | 322 |
| 1.50× | 15% | 56% | 183 |
| 1.75× | 8% | 56% | 103 |
| 2.00× | 5% | — | 58 |

## Per-year (2022 = chop/bear holdout)

| year | n | open-inside% | ETH-H break% | ETH-H accept\|brk | inside→touch-an-extreme% |
|---|---|---|---|---|---|
| 2021 | 113 | 57% | 66% | 64% | 84% |
| 2022 | 251 | 62% | 61% | 49% | 86% |
| 2023 | 254 | 59% | 64% | 55% | 82% |
| 2024 | 259 | 66% | 70% | 50% | 82% |
| 2025 | 257 | 60% | 64% | 56% | 85% |
| 2026 | 115 | 59% | 63% | 58% | 88% |
