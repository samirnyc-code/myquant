# ER10 scaled take-profit sweep — flagged trades (2026-06-24)

Take-profit applied at EB close (when the entry-bar ER10 is legitimately known) to the ER10-DECAYED 'flagged' trades, target SCALED per trade by risk (R) or volatility (prior_ATR). Control column = same target on UNFLAGGED trades (must not help). In-sample MC.

**Set:** `ba_signals_mc.parquet`  **Gate:** 0.70  **flagged n:** 2,118  **unflagged n:** 3,183  **flagged baseline:** $-359,734 (exp $-169.85/trade).

## Scaled-target results (ranked by flagged mean Δ/trade)

| target | flagged net $ | flagged exp $ | flagged Δ/trade $ | flagged total Δ $ | UNFLAGGED Δ/trade $ (control) |
|---|---|---|---|---|---|
| BASELINE (1R only) | $-359,734 | $-169.85 | — | — | — |
| 0.05xABR  ⭐ | $-326,767 | $-154.28 | $15.57 | $32,968 | $-73.59 |
| +4pt(fix) | $-330,222 | $-155.91 | $13.93 | $29,512 | $-73.86 |
| 0.075xABR | $-332,892 | $-157.17 | $12.67 | $26,843 | $-66.37 |
| 0.25R | $-333,781 | $-157.59 | $12.25 | $25,953 | $-66.66 |
| 0.1xABR | $-337,877 | $-159.53 | $10.32 | $21,858 | $-58.20 |
| 0.5R | $-356,041 | $-168.10 | $1.74 | $3,694 | $-56.82 |
| 0.15xABR | $-357,588 | $-168.83 | $1.01 | $2,146 | $-49.73 |
| 0.75R | $-358,628 | $-169.32 | $0.52 | $1,106 | $-22.15 |
| 1R | $-359,734 | $-169.85 | $0.00 | $0 | $0.00 |

## By-year stability — best target `0.05xABR` (flagged only)

| year | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ | Δ/trade $ |
|---|---|---|---|---|---|---|
| 2021 | 236 | $-28,191 | $-119.46 | $-20,932 | $-88.70 | $30.76 |
| 2022 | 465 | $-93,215 | $-200.46 | $-71,174 | $-153.06 | $47.40 |
| 2023 | 415 | $-72,959 | $-175.81 | $-70,173 | $-169.09 | $6.71 |
| 2024 | 374 | $-60,418 | $-161.55 | $-64,323 | $-171.99 | $-10.44 |
| 2025 | 418 | $-76,710 | $-183.52 | $-76,675 | $-183.43 | $0.08 |
| 2026 | 210 | $-28,241 | $-134.48 | $-23,491 | $-111.86 | $22.62 |

**Best:** `0.05xABR` → flagged exp $-154.28/trade (Δ $15.57, total $32,968); control UNFLAGGED Δ $-73.59/trade (should be ≤ 0). Positive flagged Δ with negative control Δ every year = robust; a year that flips = fragile.
