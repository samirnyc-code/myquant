# BL-from-BL algebra — the index-complex identity

**Verdict: CONFIRMED (exact).** ES Blind Spots are an EXACT copy of SPX Blind Spots
(equivalently SPY BL), element-wise in MenthorQ's native `bl_1..bl_10` order, rescaled
by a single per-day scalar. Residual ~0.003 pt = rounding noise. Not a statistical
tendency — a literal identity.

## Headline formula
```
ES1!.bl_i(day)  =  SPX.bl_i(day) * k(day)          for every i, exactly
                =  SPY.bl_i(day) * k'(day)
k(day)  = ES_price/SPX_price  (the futures basis; drifts 1.0003 .. 1.0100 over the panel)
k'(day) = ES_price/SPY_price  ~ 10.075
```
Same for the other index complexes:
```
NQ1!.bl_i = NDX.bl_i * k = QQQ.bl_i * ~41
RTY1!.bl_i = RUT.bl_i * k = IWM.bl_i * ~10.9
```

## Three exact families (the whole 19-instrument panel collapses to these)
| Family | Members (identical BL set, one ratio, same order) | element-wise CV |
|---|---|---|
| S&P complex | **ES1! = SPX = SPY** | 5e-7 |
| Nasdaq complex | **NQ1! = NDX = QQQ** | 1e-7 |
| Russell complex | **RTY1! = RUT = IWM** | 1e-6 |
| Dow | YM1! (no Dow index/ETF in panel) | — |
| GC1!, CL1! | each standalone | — |
| Mag7 (AAPL…TSLA) | each standalone | — |

CV = median over 200 days of stdev(ratio_i)/mean(ratio_i) where ratio_i = ES.bl_i/S.bl_i in
NATIVE order. ~1e-6 means all ten ratios agree to 6 sig figs => same set, same order, one scalar.

## Evidence (REAL vs NULL, in/out-of-sample)

**Element-wise same-order ratio consistency (Test A), ES target, 196 days:**
- SPX CV = 5.3e-7, SPY CV = 4.0e-6  (identity)
- next best (QQQ/NDX/NQ/mag7) CV ~ 2.3e-2 — i.e. 4-5 orders of magnitude worse. Clean gap.

**Order preservation (Test D):** using ONLY the bl_1 ratio to predict all ten, ES matches
SPX within 0.5 pt on **196/196 days** and SPY on **196/196 days**. The `bl_1..bl_10` overlap-rank
ordering is byte-identical across the family (so bl_k always maps to the same source bl_k — answer
to your ordering question: yes, perfectly stable, it IS the same list).

**Element-wise native-order residual (Test C), median abs pt:**
| pair | per-day ratio | fixed ratio (OOS, train 137/test 59) |
|---|---|---|
| ES vs SPX | **0.003** | 14.7 (this is basis drift, not error) |
| ES vs SPY | **0.024** | 19.0 |
| ES vs NDX/QQQ/NQ | 114 | 486 |
| ES vs RUT/IWM | 236 | 349 |
| ES vs GC/CL/YM | 155–190 | 258–1130 |

Only the S&P complex has ~0 residual. Everything else is a different underlying — no accidental
overlap. NULL (source taken from a random different day) on the sorted-set matched distance:
SPX real/null = 0.142, SPY = 0.117; every non-family source real/null ~ 0.9–1.1 (indistinguishable
from noise). So the S&P complex beats null by ~7x; nothing else beats null at all.

## Answers to the specific asks
1. **Pairwise exact copy?** YES — SPX (and SPY) is an exact copy of ES BL. Residual 0.003 pt.
2. **Union of several instruments?** REFUTED. ES BL is a pure single-source copy of the S&P set,
   not a sub-selected union of {SPY, QQQ, RUT, mag7, …}. QQQ/RUT/mag7 contribute nothing beyond
   noise (real/null ~ 1.0). No union needed or supported.
3. **Ordering:** ES bl_k ↔ SPX bl_k ↔ SPY bl_k, identical rank, all 200 days. Stable.
4. **Reverse / primary:** SPY↔SPX ratio ≈ 10.038 is essentially constant (the index-divisor
   relationship). ES/SPX ≈ 1.005 DRIFTS with time-to-expiry (min 1.0003, max 1.0100) — the classic
   futures basis. So the BL are computed on the **cash index / ETF** (SPX or SPY — indistinguishable,
   ratio near-constant between them) and **futures BL are just the cash set × the live futures/cash
   price ratio.** The future is the derived one, not primary. Same story for NQ (NDX/QQQ primary)
   and RTY (RUT/IWM primary).
5. Done throughout above.

## Why the prior "8 pt / 0.12%" result understated this
The established note compared **sorted** sets at a **fixed** ratio 10.08. Two errors compounded:
(a) sorting was unnecessary — the native order already aligns, and (b) a fixed ratio bakes in the
basis drift (~15 pt on ES). Using the native order + the observable per-day price ratio, the mapping
is EXACT (0.003 pt), not 8 pt. The relationship isn't "related-not-exact"; it's an identity.

## What this does and does NOT crack
- It fully explains cross-instrument BL WITHIN a complex: given SPX BL you get ES/SPY BL to the penny.
- It does NOT by itself explain how the **seed set** (the SPX/NDX/RUT BL numbers, with their odd
  2-decimals like 7579.32) is generated — that still traces to SPX's own per-strike surface /
  cross-asset overlap computation (the other work streams). But it collapses the target from 19
  instruments to ~5 independent underlyings (S&P, Nasdaq, Russell, Dow, gold, crude, + each mag7
  name), which should sharpen the seed-formula hunt: solve SPX and you've solved ES/SPY for free.

## Reproduce
`scratchpad/bl_algebra.py` (Tests A–F). Data: `data/menthorq/<SYM>_mq_blindspots_history.csv`.
