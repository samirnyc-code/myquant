# ER10 +Npt take-profit — control test (2026-06-24)

Applies the EB-close take-profit overlay to the WHOLE causal book and splits the per-trade delta (overlay − baseline) by group. If FLAGGED ≈ UNFLAGGED ≈ RANDOM, the TP is a generic exit tweak, not an ER10 effect.

**Set:** `ba_signals_mc.parquet`  **Gate:** 0.70  **n:** flagged 2,118, unflagged 3,183, all 5,301.

## Take-profit @ entry+2pt — per-trade delta by group

| group | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ | mean Δ $/trade | total Δ $ |
|---|---|---|---|---|---|---|---|
| FLAGGED (ER10 decayed) | 2,118 | $-359,734 | $-169.85 | $-339,897 | $-160.48 | $9.37 | $19,838 |
| UNFLAGGED (ER10 held) | 3,183 | $629,597 | $197.80 | $367,872 | $115.57 | $-82.23 | $-261,725 |
| RANDOM (size-matched) | 2,118 | $88,728 | $41.89 | $5,353 | $2.53 | $-39.36 | $-83,375 |
| ALL causal trades | 5,301 | $269,863 | $50.91 | $27,975 | $5.28 | $-45.63 | $-241,887 |

## Take-profit @ entry+4pt — per-trade delta by group

| group | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ | mean Δ $/trade | total Δ $ |
|---|---|---|---|---|---|---|---|
| FLAGGED (ER10 decayed) | 2,118 | $-359,734 | $-169.85 | $-330,222 | $-155.91 | $13.93 | $29,512 |
| UNFLAGGED (ER10 held) | 3,183 | $629,597 | $197.80 | $394,497 | $123.94 | $-73.86 | $-235,100 |
| RANDOM (size-matched) | 2,118 | $88,728 | $41.89 | $6,878 | $3.25 | $-38.64 | $-81,850 |
| ALL causal trades | 5,301 | $269,863 | $50.91 | $64,275 | $12.13 | $-38.78 | $-205,588 |

## Take-profit @ entry+6pt — per-trade delta by group

| group | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ | mean Δ $/trade | total Δ $ |
|---|---|---|---|---|---|---|---|
| FLAGGED (ER10 decayed) | 2,118 | $-359,734 | $-169.85 | $-334,497 | $-157.93 | $11.92 | $25,238 |
| UNFLAGGED (ER10 held) | 3,183 | $629,597 | $197.80 | $442,797 | $139.11 | $-58.69 | $-186,800 |
| RANDOM (size-matched) | 2,118 | $88,728 | $41.89 | $26,753 | $12.63 | $-29.26 | $-61,975 |
| ALL causal trades | 5,301 | $269,863 | $50.91 | $108,300 | $20.43 | $-30.48 | $-161,563 |

## Verdict (+4pt)

- mean Δ/trade: FLAGGED **$13.93**, UNFLAGGED **$-73.86**, RANDOM **$-38.64**.
- If FLAGGED Δ ≫ UNFLAGGED/RANDOM Δ → the ER10 decay flag genuinely selects trades the take-profit rescues. If they're comparable → the +4pt TP is generic (helps any trade), and ER10 adds nothing.
