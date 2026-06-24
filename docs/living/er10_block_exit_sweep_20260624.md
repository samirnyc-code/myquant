# ER10 phantom-block exit sweep (2026-06-24)

**Premise (causally valid):** the entry-bar ER10 the bug used as a *gate* (look-ahead) is legitimately *known at the entry bar's close* (~5 min after entry). Use it as an **exit** signal there instead. These are the **2,118 trades** the causal book takes but whose ER10 had decayed below 0.70 by EB close (the bug skipped them).

**Signal set:** `ba_signals_mc.parquet`  **Gate:** ER10 ≥ 0.70  **Exec:** 1.0R single-leg, 1c, entry_slip=1t, exit_slip=0, comm $4.36 RT.

- Causal book: **5,398** signals → **3,183** unflagged + **2,118** flagged (filled).
- Of the flagged, **2,082** are still OPEN at EB close (overlay can act); the other **36** already hit stop/target inside the entry bar (unaffected — kept at baseline).
- Unflagged trades' net (held fixed): **$629,597**.  Whole-book causal baseline: **$269,863**.

## Flagged-subset exit rules

| exit rule | flagged net $ | flagged exp $/trade | flagged win % | WHOLE-BOOK net $ |
|---|---|---|---|---|
| BASELINE (no overlay) | $-359,734 | $-169.85 | 37.6% | $269,863 |
| flat @ EB close | $-381,434 | $-180.09 | 3.3% | $248,163 |
| exit @ entry-8pt | $-380,834 | $-179.81 | 23.0% | $248,763 |
| exit @ entry-6pt | $-385,509 | $-182.02 | 17.1% | $244,088 |
| exit @ entry-4pt | $-388,984 | $-183.66 | 10.2% | $240,613 |
| exit @ entry-3pt | $-398,809 | $-188.30 | 6.0% | $230,788 |
| exit @ entry-2pt | $-391,009 | $-184.61 | 3.2% | $238,588 |
| exit @ entry-1pt | $-384,597 | $-181.58 | 1.3% | $245,000 |
| exit @ entry+0pt | $-383,409 | $-181.02 | 0.6% | $246,188 |
| exit @ entry+1pt | $-360,997 | $-170.44 | 68.6% | $268,600 |
| exit @ entry+2pt | $-339,897 | $-160.48 | 65.3% | $289,700 |
| exit @ entry+3pt | $-333,284 | $-157.36 | 61.4% | $296,313 |
| exit @ entry+4pt  ⭐ | $-330,222 | $-155.91 | 58.2% | $299,375 |
| exit @ entry+6pt | $-334,497 | $-157.93 | 52.6% | $295,100 |

**Best whole-book result:** `exit @ entry+4pt` → flagged net $-330,222 (exp $-155.91/trade), whole-book **$299,375** vs baseline **$269,863** (Δ **$29,512**).

_Overlay stops/targets fill at their level when price crosses them mid-path; a level already breached at the first post-EB-close tick fills at market there (no fabricated breakeven on already-underwater trades). 'flat @ EB close' exits at the first tick at/after EB close (market)._
