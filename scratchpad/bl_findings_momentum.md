# BL reverse-engineering — MOMENTUM angle findings

**Verdict: REFUTED.** BL residuals are NOT a simple momentum function. Both the
*direction* test and the *magnitude* test fail, and they fail in ways that
contradict each other across the two instruments — the signature of curve-fit
noise, not signal.

## Setup
- Residual = BL − nearest structural gamma level, structural pool = {Call
  Resistance, Put Support, HVL, Gamma Wall 0DTE} across all 12 correlated
  instruments, mapped into target by spot-ratio `level*(target_spot/asset_spot)`,
  `asset_spot=(1D Min+1D Max)/2`. (Established finding #2 mapping.)
- Momentum measured two independent ways for 2026-07-17:
  1. **Free EOD proxy** from the JSONL midpoint series (deduped by date — the
     files have 11 duplicate dates; naive read corrupts returns).
     ES: 5d −1.72%, 10d −0.82%, 20d −0.81%, RSI14≈50. **DOWN/neutral.**
     NQ: 5d −4.32%, 10d −3.79%, 20d −6.13%, RSI14≈38. **DOWN, strongly.**
  2. **MenthorQ's OWN momentum QScore** (`mq.metrics`, 1 API call):
     ES momentum = **2.0** on 7/17 (was 5.0 on 7/16 and 7/15 — falling).
     NQ momentum = **2.0** on 7/17 (steady low). Scale is a coarse 0–10 integer
     rank; 2.0 = low / bearish. Both agree: momentum is DOWN on 7/17.

## Directional test — FAILS (this is the clean kill)
Hypothesis: up-momentum pushes BL up, so BL should cluster in the momentum
direction. On 7/17 **both instruments have DOWN momentum** (proxy AND MQ's own
field = 2.0). Yet BL are **upside-skewed**:
- ES: 5 above / 5 below, but max extension **+341 above vs −249 below**, mean BL
  position **+16** relative to spot.
- NQ: **7 above / 3 below**, max **+721 above vs −832 below**, mean position
  **+160 above spot** — a heavy UP skew under the strongest DOWN momentum.

Down momentum + upside-skewed blind spots = the **opposite** of the directional
hypothesis. The "is the upside skew explained by up-momentum?" question in the
brief is answered: **no — momentum was down, so the upside skew is not a
momentum effect.**

## Magnitude test — FAILS (inconsistent, outlier-driven)
Fit residual = a + b·(signed dist-from-spot) and residual = a + b·|dist-from-spot|
(a proportional "levels farther out are shifted more" shape):

| target | resid~dist_spot | resid~\|dist_spot\| |
|--------|-----------------|---------------------|
| ES1!   | slope −0.021, R²=0.21 | slope **+0.036**, R²=0.24 |
| NQ1!   | slope −0.025, R²=0.13 | slope **−0.023**, R²=0.02 |

- The |dist| slope **flips sign** between ES (+) and NQ (−). A real shared
  mechanism must reproduce BOTH with the same sign; it doesn't.
- The nonzero R² are driven by a **single bad-match outlier each** (ES bl_7
  residual +24.2 = a poor META-HVL match; NQ bl_6 residual +110.1 = a poor
  AMZN-HVL match). Drop those and R² collapses toward 0. These outliers are
  nearest-match failures, not momentum.
- A constant (mean shift) does about as well: ES mean signed resid +3.2 with
  median|res| 2.15; NQ mean +13.5 with median|res| 6.85 — no structure beyond a
  small positive offset that is itself within the dense-pool match noise.

## Overfitting / degrees of freedom — why no fit here is credible
- Effective independent momentum observations = **2** (ES, NQ) on **1 day**. The
  "20 residuals" are 10+10 within-instrument points, not independent draws of the
  momentum→BL relationship.
- Momentum candidate menu is large (5d/10d/20d return, RSI, dist-from-MA, signed
  vs |dist|, MQ's own QScore). With 2 real observations and ~6 candidates, a
  spurious "fit" is guaranteed if you go looking.
- The residuals themselves are **dense-pool nearest-match residuals**, which the
  brief already established score like random points (~1.5pt). Regressing momentum
  onto noise cannot produce a real law.

## Conclusion
**REFUTED.** BL ≠ structural_gamma_level + f(momentum) in any simple form:
- Directional momentum is contradicted outright (down momentum, up-skewed BL, on
  both instruments, by both the proxy and MenthorQ's own momentum=2.0 field).
- The magnitude relationship is weak, outlier-driven, and **sign-inconsistent
  across ES vs NQ**, i.e. curve-fit noise.
The upside skew (esp. NQ 7/3) is a real property of BL to explain, but momentum
is not the explanation. Momentum can be dropped as a candidate BL input for the
purposes of a reconstructable formula.

Data/scripts: scratchpad/bl_resid.py, bl_mom2.py, bl_fit.py
