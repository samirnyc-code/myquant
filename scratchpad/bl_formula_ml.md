# BL FORMULA hunt — ML mapping + driver attribution  [S75V]

**Angle:** Let a model learn the map from the 38-ticker basket gamma surface to the sorted
ES/NQ Blind-Spot vector, and read off the drivers. Strict time-based split: fit on the first
140 sessions, report on the held-out last 60. sklearn RF/GBM/Ridge. No leakage (train-median
imputation, train-mean climatology).

## Method
- **Features (740):** per basket asset × per level-type (CR, PS, HVL, the 4 0DTE levels, 1D
  Min/Max, GEX 1..10), offset = `(level − ES_spot)/ES_spot` (scale-free), plus each asset's
  `spot/ES_spot` ratio. ES_spot = (1D Min+1D Max)/2 from the ES1! gamma cache.
- **Target:** the **sorted** 10 BL as %-offsets from spot (the index order is separately hard;
  I predict the sorted vector, one regressor per rank).
- **Baselines:** (i) climatology = train-mean %-offset per rank; (ii) Ridge on SPX/SPY/QQQ
  levels only. **Model:** RandomForest & GBM on the full 740-feature basket.
- MAE reported in **ES/NQ points** (offset error × test-day spot). n=200 ES / 196 NQ days.

## Headline result — the full basket does NOT beat baselines out of sample

**ES — aggregate OOS MAE (points), last 60 sessions:**

| model | OOS MAE | train MAE |
|---|---|---|
| climatology (fixed %-offset) | **44.7** | — |
| SPX/SPY/QQQ Ridge | 43.6 | 41 |
| **full-basket RandomForest** | 49.2 | **17.7** |
| full-basket GBM | 51.6 | — |

**NQ — aggregate OOS MAE (points):** climatology 196.4 · SPX/SPY/QQQ 194.4 · RF 206.4 · GBM 224.9
(RF train 71.7).

Reading:
- The full basket (RF/GBM) is **worse than climatology out of sample** for both ES and NQ,
  while its train MAE is ~3× lower (ES 17.7 train vs 49.2 test). That gap is textbook
  **overfitting** — the 740 wide features fit noise on 140 days and generalize negatively.
- The SPX/SPY/QQQ Ridge edges climatology by ~1 pt on 44 (ES) / ~2 on 196 (NQ) — inside the
  noise, not a real edge.
- **Climatology MAE ≈ 0.8 × the intrinsic per-rank offset std** (e.g. ES bl_1 std 81 pts →
  clim MAE 72; bl_10 std 98 → 77). So the baseline error is just each rank's natural
  dispersion, and **no model reduces it** — the day-to-day variation of the sorted BL offsets
  is not a learnable function of the basket gamma offsets.

Per-BL: models only ever match climatology on the mid ranks (bl_6–8) and blow up on the tails
(ES bl_1: clim 72 vs RF 93; bl_2: 48 vs 76) where they most need to extrapolate. No rank shows
a robust OOS win.

## Do sector ETFs matter beyond SPY/QQQ? — NO
Apples-to-apples: SPX/SPY/QQQ-only Ridge (43.6) **beats** the full-basket RF that includes all
11 sector ETFs (49.2). Adding the sectors *raises* OOS error → they contribute noise, not
signal, once the index proxies are present. RF impurity importance does rank a few sector
levels high in-sample (XLF::Put Support 0DTE, XLC::Gamma Wall 0DTE) but this does not convert
to any out-of-sample gain — it is in-sample overfit attribution.

## Top drivers (in-sample impurity importance — directional only)
- **ES** — assets: SPX, SPY, VIX, TLT, ES1!, XLF. Level types: **HVL 0DTE, Call Resistance
  0DTE, Gamma Wall 0DTE, HVL** dominate (0DTE/daily structural levels >> the GEX ladder).
  Top single: `SPX::HVL 0DTE`.
- **NQ** — assets: QQQ, NDX, NQ1! (own complex, as expected). Levels: HVL, HVL 0DTE, Gamma
  Wall 0DTE. Top single: `QQQ::HVL 0DTE`, `NQ1!::HVL`.
- Consistent with the established confluence finding (BL sit near cross-asset CR/PS/HVL/Gamma
  Wall zones) — but importance ≠ predictability: these features are *near* the BL yet don't
  *predict* the exact sorted values better than a constant.

## Stable per-BL attribution? — NO
Nearest-feature attribution (for each sorted BL each day, which of 740 offsets is closest, and
is that feature stable across days):

| | modal-feature share | interpretation |
|---|---|---|
| ES ranks | 0.09–0.26 | no stable 1-BL→1-level map |
| NQ ranks | 0.08–0.16 | no stable 1-BL→1-level map |

A genuine "BL_k = asset X's level Y" formula would show share ≈ 0.8+. Observed shares are ~0.1
— the nearest feature reshuffles day to day. The small median errors on mid ranks (ES ~2 pts)
are a **curse-of-dimensionality artifact**: nearest-of-740 offsets is trivially close to any
target, and is not evidence of a mapping (the 0.1 share proves it isn't one). Ends (bl_1, bl_10)
even the nearest feature misses by 12–31 pts (ES) / 33–117 pts (NQ).

## Verdict — **REFUTED (not learnable from these inputs)**
The sorted ES/NQ Blind-Spot offset vector is **not a learnable function of the 38-ticker basket
gamma-level offsets** at 200 days: RF/GBM on the full basket underperform a fixed-%-offset
climatology out of sample, the SPX/SPY/QQQ subset gives no meaningful edge, sector ETFs add
noise not signal, and no rank maps stably to any single asset/level. This does **not** contradict
the established confluence result (BL sit *near* cross-asset gamma zones, z=+8.9) — proximity
holds, but the specific set MQ emits each day is not recoverable from the published level grid
by a smooth model. Consistent with the established lead that the true input is the **per-strike
surface** (or another asset's odd-decimal BL), which is not present in this feature set.

**What would change the verdict:** feeding the per-strike GEX surface (strike, gamma, OI) rather
than the 10 pre-summarized GEX levels, or a larger panel (500+ days) to let a constrained model
separate signal from the 740-wide noise. On the current inputs, the mapping is not there.

Files: `scratchpad/bl_formula_ml.py` (pipeline), `scratchpad/bl_formula_ml_results.json` (full
per-BL numbers, importances, attribution).
