# BL FORMULA — V2 overlap-clustering model (full basket, 200d)  [S75V]

**Angle:** MQ says BL = "ranges from highly correlated assets with strong OVERLAPS",
BL1 = most overlap. Test whether ES/NQ `bl_1..bl_10` are the top-10 overlap CLUSTERS of the
whole basket's gamma levels mapped into ES/NQ space, and whether overlap-rank predicts bl_index.

Scripts: `scratchpad/bl_cluster_model.py` (grid+OOS+ordering), `scratchpad/bl_cluster_diag.py` (mechanism test).
Data: `scratchpad/bl_basket_gamma.json` (38 tickers, 202d), `data/menthorq/<SYM>_mq_blindspots_history.csv`.

## Method
Per day: map every basket asset's levels into target space by spot-ratio (spot=(1D Min+1D Max)/2),
pool them, greedily cluster at width TOL, score each cluster by #distinct assets, take top-10 → predicted BL.
Real = median matched dist (each actual BL → nearest predicted centroid). Null = 10 uniform-random pts in the
BL band → same centroids (50 draws/day). Config chosen on TRAIN (first 140d), reported OUT-OF-SAMPLE (last 60d).
Grid: basket {idx / +sectors / +mag7 / all} × levelset {structural / +GEX / all} × TOL {3,5,7,9,12,15,20}.

## Best config
**basket = index ETFs only (SPX/SPY/QQQ/NDX/IWM/RUT/DIA), levelset = all (struct+GEX+1DMinMax), TOL = 20pt.**
Adding sectors/mag7/macro did NOT help (idx alone won). Larger TOL monotonically won → the model is really
"the ~10 densest mapped gamma zones", not a fine-grained overlap count.

## Result 1 — distance vs null: **CONFIRMED (beats null, both instruments)**
| | n | REAL | NULL | ratio | t | win% |
|---|---|---|---|---|---|---|
| ES train (140d) | 140 | 8.78 | 21.35 | 0.41 | −7.7 | — |
| **ES OOS (60d)** | 60 | **10.05** | 19.04 | **0.53** | **−3.7** | 66.7 |
| NQ OOS (60d, same cfg) | 58 | 75.5 | 93.2 | 0.81 | −2.0 | 65.5 |
| NQ full (196d) | 196 | 64.3 | 100.6 | 0.64 | −7.6 | 76.0 |

BL sit ~2x closer to the top-density cross-asset gamma clusters than random, out-of-sample, for BOTH ES and NQ
(NQ effect weaker/noisier but same direction). Consistent with — and no stronger than — the already-established
structural-confluence result (~8pt median). **This is a statistical tendency, not reconstruction.**

## Result 2 — the "OVERLAP" mechanism adds NOTHING: **REFUTED**
Selecting clusters by **distinct-asset overlap count** vs by **raw point count** gives *identical* accuracy:
- top-10 by OVERLAP: **9.16pt**   ·   top-10 by SIZE(pts): **9.02pt**   ·   10 RANDOM clusters: 18.68pt   ·   null: 20.53pt.
- overlap vs random-cluster: −9.52pt, t=−15.6 (density selection matters hugely).
- overlap vs size: indistinguishable. So "strong overlaps from distinct correlated assets" is NOT separable from
  plain "densest gamma zones." The specific V2 distinct-asset-overlap story is unsupported by the data.

## Result 3 — ordering claim (BL1 = most overlap): **REFUTED**
Spearman(bl_index, matched-cluster overlap-count), mean over days ± 95% CI:
- **ES: −0.009  [−0.058, +0.041]  t=−0.4  (n=200)**  → zero.
- **NQ: −0.039  [−0.089, +0.010]  t=−1.6  (n=190)**  → not significant.

With n=200 now fully powered, there is **no** relationship between MQ's bl_1..bl_10 column order and how much
overlap the nearest cluster carries. The "BL1 = most overlap, BL10 = less" ordering is not recoverable.

## Result 4 — exactness: not achieved
Predicted centroids within a given tolerance of SOME actual BL: 2.0/10 @3pt, 3.1/10 @5pt, 5.2/10 @10pt.
Predicted-centroid span 252pt covers ~70% of the 386pt BL band. Order-of-magnitude same as prior mappings
(SPY-copy 8pt, structural confluence). No penny-exact reconstruction.

## VERDICT
- **Distance/clustering hypothesis: CONFIRMED** — ES & NQ BL cluster near the densest cross-asset gamma zones,
  OOS, beating null (ES ratio 0.53 t=−3.7; NQ 0.64 t=−7.6). Best = index ETFs, all levels, wide TOL.
- **The distinctive V2 claims: REFUTED** — (a) "distinct-asset OVERLAP" is statistically indistinguishable from
  plain point-density, and (b) the bl_1..bl_10 ORDERING carries no overlap-rank signal (Spearman≈0, n=200).
- **Net:** the clustering model reproduces the *known* ~8–9pt statistical tendency but adds no new mechanism and
  does not crack the formula. It bounds what BL V2 is NOT: not a distinct-asset overlap *rank* over this basket.
